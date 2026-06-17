"""
AgriTrue — True Cost Accounting dashboard for TEEBAgriFood / SOFA 2024
=====================================================================
Run locally:   streamlit run app.py
Deploy free :  push to GitHub -> share.streamlit.io -> point at app.py (gives a public URL)

Six views:
  1. Global & National Dashboard   — hidden costs by country / capital / system type
  2. True Price Calculator         — hidden cost per kg for ~30 commodities
  3. Diet True-Cost Comparator     — national diets vs the EAT-Lancet reference
  4. Farm-Practice Comparator      — conventional vs organic / agroforestry (Phase-3)
  5. Localized TCA Studies         — reproduce a country study (TEEBAgriFood framework) + live sensitivity
  6. Methodology & Sources         — every coefficient, citation, and caveat

Usage analytics are recorded silently to the server logs / a local file (no UI surface) —
read them with `python view_logs.py`, or in Streamlit Cloud's log viewer.

The whole app reads from the `tca` package, so the numbers on screen are produced by the
same audited engine that the unit tests cover.
"""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from tca import (
    true_price, rank_commodities, compare_practices,
    COMMODITY_FACTORS, DEFAULT_COEFFICIENTS, AGRIFOOD_SYSTEM_TYPES, SOFA_2024_GLOBAL,
    PRACTICE_DELTAS, DIET_PATTERNS, compare_diets,
)
from tca.data_pipeline import load_national_dataset
from tca.teeb_studies import (
    TEEB_STUDIES, compare_scenarios, adjustable_items, materialize_study,
    CAPITALS, CAPITAL_LABELS,
)
from tca import report
from tca import analytics

st.set_page_config(page_title="AgriTrue · TEEBAgriFood TCA", page_icon="🌍", layout="wide")

# First-party analytics: register the session and capture visitor context once.
_SESSION_ID, _CLIENT = analytics.ensure_session(st)

# Brand palette (UNEP-ish greens/blues) ------------------------------------
CAP_COLORS = {"health": "#d1495b", "environmental": "#2a9d8f", "social": "#e9c46a",
              "climate": "#264653", "eutrophication": "#2a9d8f", "water": "#48cae4",
              "land": "#8ab17d"}

# --------------------------------------------------------------------------
# Sidebar — the shared, transparent valuation controls
# --------------------------------------------------------------------------
st.sidebar.title("🌍 AgriTrue")
st.sidebar.caption("True Cost Accounting for agrifood systems · FAO SOFA 2024 global layer "
                   "+ localized TEEBAgriFood country studies")

st.sidebar.markdown("### Valuation coefficients")
st.sidebar.caption("Drag to test assumptions — the whole app re-prices live. "
                   "This *is* the TCA transparency principle.")

coeffs = {}
for key, meta in DEFAULT_COEFFICIENTS.items():
    coeffs[key] = st.sidebar.slider(
        f"{key.replace('_', ' ').title()}  ({meta['unit']})",
        float(meta["low"]), float(meta["high"]), float(meta["value"]),
        help=meta["source"],
    )

view = st.sidebar.radio(
    "View",
    ["Global & National Dashboard", "True Price Calculator",
     "Diet True-Cost Comparator", "Farm-Practice Comparator",
     "Localized TCA Studies", "Methodology & Sources"],
)
st.sidebar.markdown("---")
st.sidebar.caption("Built as a working demo for the TEEBAgriFood programme. "
                   "Global figures match SOFA 2024; per-country values are modelled "
                   "estimates calibrated to those aggregates.")

# Usage events are recorded to the server logs / local log file only (no UI surface).
analytics.track_view(st, view)


# ==========================================================================
# VIEW 1 — GLOBAL & NATIONAL DASHBOARD
# ==========================================================================
def view_dashboard():
    st.title("Hidden costs of agrifood systems")
    g = SOFA_2024_GLOBAL
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Global hidden costs", f"${g['total_hidden_cost_trillion_usd']:.0f}T / yr")
    c2.metric("Share of global GDP", f"{g['share_of_global_gdp']*100:.0f}%")
    c3.metric("Health-driven", f"{g['health_share']*100:.0f}%")
    c4.metric("Countries covered", f"{g['countries_covered']}")
    st.caption(f"Source: {g['source']} · basis: {g['currency_basis']}")

    df = pd.DataFrame(load_national_dataset())

    # --- Filters -----------------------------------------------------------
    fc1, fc2 = st.columns([2, 2])
    regions = ["All"] + sorted(df["region"].unique())
    systems = ["All"] + list(AGRIFOOD_SYSTEM_TYPES.keys())
    region = fc1.selectbox("Region", regions)
    system = fc2.selectbox("Agrifood-system type", systems)
    fdf = df.copy()
    if region != "All":
        fdf = fdf[fdf["region"] == region]
    if system != "All":
        fdf = fdf[fdf["system"] == system]

    st.markdown("### Where the hidden costs fall")
    left, right = st.columns([3, 2])

    with left:
        top = fdf.sort_values("hidden_total_busd", ascending=False).head(20)
        melt = top.melt(
            id_vars=["name"], value_vars=["health_busd", "env_busd", "social_busd"],
            var_name="capital", value_name="busd")
        melt["capital"] = melt["capital"].map(
            {"health_busd": "health", "env_busd": "environmental", "social_busd": "social"})
        fig = px.bar(
            melt, x="busd", y="name", color="capital", orientation="h",
            color_discrete_map=CAP_COLORS,
            labels={"busd": "Hidden cost (USD bn / yr)", "name": ""},
            title="Top countries by total hidden cost (stacked by capital)")
        fig.update_layout(height=620, yaxis={"categoryorder": "total ascending"},
                          legend_title_text="Capital")
        st.plotly_chart(fig, width='stretch')

    with right:
        agg = fdf[["health_busd", "env_busd", "social_busd"]].sum()
        pie = go.Figure(go.Pie(
            labels=["Health", "Environmental", "Social"],
            values=[agg["health_busd"], agg["env_busd"], agg["social_busd"]],
            marker_colors=[CAP_COLORS["health"], CAP_COLORS["environmental"], CAP_COLORS["social"]],
            hole=0.45))
        pie.update_layout(title="Capital composition (selection)", height=320)
        st.plotly_chart(pie, width='stretch')

        sysdf = (fdf.groupby("system")["hidden_total_busd"].sum()
                 .reindex(list(AGRIFOOD_SYSTEM_TYPES.keys())).dropna())
        sfig = px.bar(sysdf, labels={"value": "USD bn", "system": ""},
                      title="By agrifood-system type")
        sfig.update_layout(height=280, showlegend=False)
        st.plotly_chart(sfig, width='stretch')

    st.markdown("### Hidden cost as a share of GDP")
    st.caption("The equity lens: traditional & protracted-crisis systems carry the "
               "heaviest *relative* burden, dominated by social costs.")
    scatter = px.scatter(
        fdf, x="gdp_ppp_busd", y="hc_pct_gdp", size="hidden_total_busd",
        color="system", hover_name="name", log_x=True,
        labels={"gdp_ppp_busd": "GDP (PPP, USD bn, log)", "hc_pct_gdp": "Hidden cost / GDP"},
        category_orders={"system": list(AGRIFOOD_SYSTEM_TYPES.keys())})
    scatter.update_layout(height=460)
    scatter.update_yaxes(tickformat=".0%")
    st.plotly_chart(scatter, width='stretch')

    st.markdown("### Country brief")
    bc1, bc2 = st.columns([2, 3])
    pick = bc1.selectbox("Generate a one-page PDF for:", fdf["name"].tolist())
    row = next(r for r in load_national_dataset() if r["name"] == pick)
    bc2.download_button(
        f"📄 Download {pick} hidden-cost brief (PDF)",
        report.national_pdf(row, SOFA_2024_GLOBAL),
        file_name=f"agritrue_{pick.replace(' ', '_')}_brief.pdf", mime="application/pdf",
        on_click=lambda: analytics.track_action(st, "pdf_download", kind="national", country=pick))

    with st.expander("📋 Underlying country table"):
        show = fdf[["name", "region", "system", "gdp_ppp_busd", "hc_pct_gdp",
                    "hidden_total_busd", "health_busd", "env_busd", "social_busd"]].copy()
        show["hc_pct_gdp"] = (show["hc_pct_gdp"] * 100).round(1)
        show = show.rename(columns={
            "name": "Country", "region": "Region", "system": "System",
            "gdp_ppp_busd": "GDP PPP $bn", "hc_pct_gdp": "Hidden % GDP",
            "hidden_total_busd": "Hidden $bn", "health_busd": "Health $bn",
            "env_busd": "Env $bn", "social_busd": "Social $bn"})
        st.dataframe(show.sort_values("Hidden $bn", ascending=False),
                     width='stretch', hide_index=True)
        st.download_button("Download CSV", show.to_csv(index=False),
                           "agritrue_national_hidden_costs.csv", "text/csv")


# ==========================================================================
# VIEW 2 — TRUE PRICE CALCULATOR
# ==========================================================================
def view_calculator():
    st.title("True Price Calculator")
    st.caption("What a kilogram of food *really* costs once environmental externalities "
               "are priced in. Powered by Poore & Nemecek (2018) LCA medians.")

    c1, c2, c3 = st.columns([2, 1, 1])
    commodity = c1.selectbox("Commodity", list(COMMODITY_FACTORS.keys()))
    mass = c2.number_input("Quantity (kg)", 0.1, 10000.0, 1.0, 0.5)
    water_stress = c3.slider("Local water-stress multiplier", 0.2, 3.0, 1.0, 0.1,
                             help="1.0 = global average; raise for arid regions")
    include_health = st.checkbox(
        "Include illustrative dietary-health surcharge (red/processed meat, sugar)",
        value=False,
        help="OFF by default — SOFA attributes health costs to whole dietary patterns, "
             "not single foods, so this is clearly flagged as approximate.")

    r = true_price(commodity, mass, coeffs, water_stress, include_health)

    analytics.track_action(st, "calc", commodity=commodity, mass_kg=mass)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Market price", f"${r['market_price']:.2f}")
    m2.metric("Hidden cost", f"${r['hidden_cost']['central']:.2f}",
              help=f"range ${r['hidden_cost']['low']:.2f}–${r['hidden_cost']['high']:.2f}")
    m3.metric("True price", f"${r['true_price']:.2f}")
    m4.metric("Hidden : market", f"{r['hidden_to_market_ratio']:.2f}×")

    st.download_button(
        "📄 Download one-page PDF brief", report.true_price_pdf(r),
        file_name=f"agritrue_{commodity.split('(')[0].strip().replace(' ', '_')}.pdf",
        mime="application/pdf",
        on_click=lambda: analytics.track_action(st, "pdf_download", kind="true_price",
                                                commodity=commodity))

    left, right = st.columns([3, 2])
    with left:
        comp = r["components"]
        cdf = pd.DataFrame([
            {"component": k.title(), "cost": v["central"], "low": v["low"], "high": v["high"]}
            for k, v in comp.items()])
        fig = px.bar(cdf, x="cost", y="component", orientation="h",
                     error_x=cdf["high"] - cdf["cost"],
                     color="component", color_discrete_map={k.title(): v for k, v in CAP_COLORS.items()},
                     labels={"cost": f"USD (per {mass:g} kg)", "component": ""},
                     title="Hidden cost by externality (with uncertainty band)")
        fig.update_layout(height=380, showlegend=False)
        st.plotly_chart(fig, width='stretch')

    with right:
        st.markdown("#### True price composition")
        waterfall = go.Figure(go.Waterfall(
            orientation="v",
            measure=["absolute"] + ["relative"] * len(r["components"]) + ["total"],
            x=["Market"] + [k.title() for k in r["components"]] + ["True price"],
            y=[r["market_price"]] + [v["central"] for v in r["components"].values()]
              + [r["true_price"]],
            connector={"line": {"color": "#bbb"}}))
        waterfall.update_layout(height=380, showlegend=False)
        st.plotly_chart(waterfall, width='stretch')

    st.markdown("### Compare across all commodities")
    rows = rank_commodities(coeffs, include_health)
    rank_df = pd.DataFrame(rows)
    fig2 = px.bar(rank_df, x="hidden_cost_per_kg", y="commodity", color="category",
                  orientation="h", labels={"hidden_cost_per_kg": "Hidden cost (USD/kg)",
                                           "commodity": ""},
                  title="Hidden environmental cost per kg — ranked")
    fig2.update_layout(height=760, yaxis={"categoryorder": "total ascending"})
    st.plotly_chart(fig2, width='stretch')
    st.caption("Animal products cluster at the top; pulses, grains and vegetables at the "
               "bottom — the central, policy-relevant finding of food-systems TCA.")


# ==========================================================================
# VIEW 3 — FARM-PRACTICE COMPARATOR  (Phase-3 relevant)
# ==========================================================================
def view_comparator():
    st.title("Farm-Practice Scenario Comparator")
    st.caption("Conventional vs agroecological practice across the four capitals — the "
               "exact question TEEBAgriFood Phase 3 asks for organic/agroforestry (India) "
               "and watershed management (Kenya).")

    c1, c2, c3 = st.columns(3)
    practice = c1.selectbox("Alternative practice", list(PRACTICE_DELTAS.keys()))
    area = c2.number_input("Area (ha)", 1.0, 1_000_000.0, 100.0, 10.0)
    crop_price = c3.number_input("Crop price (USD/t)", 10.0, 5000.0, 300.0, 10.0)

    c4, c5 = st.columns(2)
    yield_t_ha = c4.number_input("Baseline yield (t/ha)", 0.1, 30.0, 3.0, 0.1)
    n_cost = c5.number_input("Baseline synthetic-N input cost (USD/ha)", 0.0, 1000.0, 120.0, 5.0)

    with st.expander("⚙️ Localise the meta-analysis coefficients (optional)"):
        d = PRACTICE_DELTAS[practice]
        st.caption(f"Defaults from: {d['source']}")
        oc1, oc2, oc3 = st.columns(3)
        yc = oc1.slider("Yield change", -0.5, 0.5, float(d["yield_change"]), 0.01)
        sc = oc2.slider("Soil C sequestration (tCO₂/ha/yr)", 0.0, 6.0,
                        float(d["soil_carbon_tco2_ha_yr"]), 0.05)
        nr = oc3.slider("Synthetic-N reduction", 0.0, 1.0,
                        float(d["synthetic_n_reduction"]), 0.05)
        deltas = {"yield_change": yc, "soil_carbon_tco2_ha_yr": sc, "synthetic_n_reduction": nr}

    r = compare_practices(practice, area, yield_t_ha, crop_price, n_cost, coeffs, deltas)
    analytics.track_action(st, "practice_compare", practice=practice, area_ha=area)

    p, n = r["produced_capital"], r["natural_capital"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Net farm income Δ", f"${p['net_income_change_usd']:,.0f}/yr",
              help="Yield effect + input savings")
    m2.metric("CO₂ sequestered", f"{n['co2_sequestered_t']:,.0f} t/yr")
    m3.metric("Natural-capital value", f"${n['net_natural_value_usd']:,.0f}/yr")
    m4.metric("Headline societal value", f"${r['headline_societal_value_usd']:,.0f}/yr",
              delta=("net positive" if r["headline_societal_value_usd"] > 0 else "net negative"))

    # Four-capitals comparison chart
    cats = ["Produced (income)", "Natural (climate+N)", "Social/Human (index×scale)"]
    social_proxy = r["social_human_capital"]["resilience_index_0_1"] * abs(
        r["headline_societal_value_usd"]) * 0.2
    vals = [p["net_income_change_usd"], n["net_natural_value_usd"], social_proxy]
    fig = go.Figure(go.Bar(x=cats, y=vals,
                           marker_color=["#457b9d", CAP_COLORS["environmental"], CAP_COLORS["social"]]))
    fig.update_layout(title=f"Annual change in capital flows — switching to {practice}",
                      yaxis_title="USD / yr (social shown as monetised index proxy)", height=420)
    fig.add_hline(y=0, line_color="#444")
    st.plotly_chart(fig, width='stretch')

    st.info(r["interpretation"])

    if p["net_income_change_usd"] < 0 < r["headline_societal_value_usd"]:
        gap = -p["net_income_change_usd"]
        st.success(
            f"**Policy signal:** the farmer faces a private income gap of "
            f"**${gap:,.0f}/yr**, but society gains **${r['headline_societal_value_usd']:,.0f}/yr**. "
            f"A results-based payment (PES) of up to ${gap:,.0f}/yr would make the "
            f"socially-optimal choice privately rational — the core TEEBAgriFood argument.")


# ==========================================================================
# VIEW 4 — METHODOLOGY & SOURCES
# ==========================================================================
def view_methodology():
    st.title("Methodology & Sources")
    st.markdown("""
AgriTrue implements the **TEEBAgriFood / FAO True Cost Accounting** framework: it scores
food systems across four capitals — **produced, natural, human, social** — and surfaces
the costs that market prices leave out. Every number on the dashboard is generated by the
audited `tca` engine (30 passing unit tests), and every coefficient is shown below with
its source and uncertainty band, in line with SOFA's own guidance to *show ranges and
assumptions rather than false precision.*
""")
    st.markdown("### Monetization coefficients")
    st.dataframe(pd.DataFrame([
        {"Coefficient": k.replace("_", " ").title(), "Default": v["value"],
         "Low": v["low"], "High": v["high"], "Unit": v["unit"], "Source": v["source"]}
        for k, v in DEFAULT_COEFFICIENTS.items()]), width='stretch', hide_index=True)

    st.markdown("### Commodity LCA factors (per kg)")
    cf = pd.DataFrame([
        {"Commodity": k, "Category": v["cat"], "GHG kgCO₂e": v["ghg"],
         "Land m²·yr": v["land"], "Water L": v["water"], "Eutroph gPO₄e": v["eutroph"],
         "Ref price $/kg": v["ref_price"]}
        for k, v in COMMODITY_FACTORS.items()])
    st.dataframe(cf, width='stretch', hide_index=True)
    st.caption("Source: Poore & Nemecek (2018), *Science* 360:987–992, supplementary medians.")

    st.markdown("### Key references")
    st.markdown("""
- **FAO (2024)** — *The State of Food and Agriculture 2024: Value-driven transformation of agrifood systems.* (~$12T hidden costs, 156 countries.)
- **FAO (2023)** — *SOFA 2023: Revealing the true cost of food to transform agrifood systems.*
- **Poore, J. & Nemecek, T. (2018)** — Reducing food's environmental impacts through producers and consumers. *Science.*
- **Rennert et al. (2022)** — A higher social cost of CO₂. *Nature* 610:687–692.
- **TEEB (2018)** — *TEEB for Agriculture & Food: Scientific and Economic Foundations.* UN Environment.
- **Seufert et al. (2012); de Ponti et al. (2012); Gattinger et al. (2012); Tuck et al. (2014)** — organic/agroecology meta-analyses.
""")

    st.markdown("### Localized TCA studies")
    st.markdown(
        "The **Localized TCA Studies** view complements the global SOFA layer with *scenario-level* "
        "country studies built on the **TEEBAgriFood four-capitals framework**. Each one reproduces a "
        "published report's headline on screen as a transparent four-capital ledger — the report's own "
        "equations, coefficients and caveats shown alongside, every line item carrying its source and "
        "adjustable for instant sensitivity analysis. Only the indicators a report actually monetises "
        "are placed on the ledger; each study names its publisher and links to its source report.")
    st.markdown(f"**{len(TEEB_STUDIES)} studies are currently encoded:**")
    for _s in TEEB_STUDIES.values():
        _pub = _s.get("publisher", "")
        # Append the year only if the publisher text doesn't already mention it.
        _year = f", {_s['year']}" if _s.get("year") and str(_s["year"]) not in _pub else ""
        st.markdown(f"- **{_s['name']}** — {_s['country']} · {_s['region']}. {_pub}{_year}.")

    st.markdown("""
### Honest caveats
1. **Per-country values are modelled**, calibrated so regional/global totals match SOFA 2024 — not the official country microdata.
2. **Per-commodity health costs** are intentionally optional and flagged: SOFA attributes health burden to dietary *patterns*, not single foods.
3. **All coefficients are user-adjustable** — the sidebar sliders re-price the entire app so reviewers can stress-test every assumption.
4. **TEEB localized studies** encode each published report's scenario comparison as an adjustable four-capital ledger; every figure is taken from — or derived from — the cited report, and only the indicators a report actually monetises are placed on the ledger.
""")


# ==========================================================================
# VIEW 5 — DIET TRUE-COST COMPARATOR
# ==========================================================================
def view_diet():
    st.title("Diet True-Cost Comparator")
    st.caption("Annual hidden (environmental) cost of a typical diet vs the EAT-Lancet "
               "planetary-health reference — the same true_price engine, applied to whole "
               "diets. Patterns are illustrative archetypes (FAO FBS + EAT-Lancet 2019).")

    diets = list(DIET_PATTERNS.keys())
    c1, c2, c3 = st.columns([2, 2, 1])
    diet_a = c1.selectbox("Diet to assess", [d for d in diets if d != "EAT-Lancet planetary health"])
    diet_b = c2.selectbox("Benchmark", diets, index=diets.index("EAT-Lancet planetary health"))
    water_stress = c3.slider("Water-stress ×", 0.2, 3.0, 1.0, 0.1)
    include_health = st.checkbox("Include illustrative dietary-health surcharge", value=False)

    cmp = compare_diets(diet_a, diet_b, coeffs, water_stress, include_health)
    analytics.track_action(st, "diet_compare", diet=diet_a, benchmark=diet_b)
    ra, rb = cmp["result_a"], cmp["result_b"]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric(f"{diet_a}", f"${ra['total_hidden_cost_usd_yr']:,.0f}/yr")
    m2.metric(f"{diet_b}", f"${rb['total_hidden_cost_usd_yr']:,.0f}/yr")
    m3.metric("Difference", f"${cmp['delta_usd_yr']:,.0f}/yr", delta=f"{cmp['delta_pct']:+.0f}%")
    m4.metric("GHG difference", f"{cmp['ghg_delta_kg_yr']:,.0f} kg CO₂e/yr")

    st.download_button(
        "📄 Download diet comparison PDF", report.diet_pdf(cmp),
        file_name=f"agritrue_diet_{diet_a.replace(' ', '_')}.pdf", mime="application/pdf",
        on_click=lambda: analytics.track_action(st, "pdf_download", kind="diet", diet=diet_a))

    left, right = st.columns(2)
    with left:
        # Grouped component comparison
        comps = sorted(set(ra["components"]) | set(rb["components"]))
        gdf = pd.DataFrame({
            "component": [c.title() for c in comps] * 2,
            "diet": [diet_a] * len(comps) + [diet_b] * len(comps),
            "cost": [ra["components"].get(c, 0) for c in comps]
                    + [rb["components"].get(c, 0) for c in comps],
        })
        fig = px.bar(gdf, x="component", y="cost", color="diet", barmode="group",
                     labels={"cost": "USD / person / yr", "component": ""},
                     title="Hidden cost by externality")
        fig.update_layout(height=400)
        st.plotly_chart(fig, width='stretch')
    with right:
        foods = pd.DataFrame(ra["foods"]).head(12)
        fig2 = px.bar(foods, x="hidden_cost_usd_yr", y="commodity", orientation="h",
                      labels={"hidden_cost_usd_yr": "USD / yr", "commodity": ""},
                      title=f"Top hidden-cost foods — {diet_a}")
        fig2.update_layout(height=400, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig2, width='stretch')

    st.markdown("### Physical footprint (per person / year)")
    fa, fb = ra["footprint"], rb["footprint"]
    foot = pd.DataFrame({
        "metric": ["GHG (kg CO₂e)", "Water (m³)", "Land (m²·yr)", "Food mass (kg)"],
        diet_a: [fa["ghg_kg"], fa["water_m3"], fa["land_m2yr"], fa["mass_kg"]],
        diet_b: [fb["ghg_kg"], fb["water_m3"], fb["land_m2yr"], fb["mass_kg"]],
    })
    st.dataframe(foot, width='stretch', hide_index=True)
    if cmp["delta_usd_yr"] > 0:
        st.success(
            f"Shifting from **{diet_a}** toward the **{diet_b}** pattern would cut hidden "
            f"environmental costs by **${cmp['delta_usd_yr']:,.0f}/person/yr "
            f"({abs(cmp['delta_pct']):.0f}%)** and **{cmp['ghg_delta_kg_yr']:,.0f} kg CO₂e/yr** "
            f"— scale by population for the national prize.")


# ==========================================================================
# VIEW 6 — TEEB LOCALIZED STUDIES  (reproduce a report + live sensitivity)
# ==========================================================================
def _money(v: float) -> str:
    """Format a study value, keeping decimals for small (e.g. Billion-USD) magnitudes so a
    $3.42 bn figure does not collapse to '$3', while large per-hectare values stay clean."""
    return f"${v:,.2f}" if abs(v) < 100 else f"${v:,.0f}"


def view_teeb_studies():
    st.title("Localized TCA Studies")
    st.caption("Localised, scenario-level country studies built on the **TEEBAgriFood four-capitals "
               "framework**. Each study names its publisher and source report below. Reproduce a "
               "report's published headline, then adjust any value to run instant sensitivity analysis.")

    if not TEEB_STUDIES:
        st.info("No studies are loaded yet.")
        return

    study_name = st.selectbox("Study", list(TEEB_STUDIES.keys()))
    study = TEEB_STUDIES[study_name]

    # Projection studies (TEEBAgriFood-India grids) expose district / year / climate selectors;
    # materialize one slice into the standard scenario ledger the rest of this view consumes.
    if study.get("projection"):
        gc1, gc2, gc3 = st.columns(3)
        district = gc1.selectbox("District", study["districts"], index=0)
        year = gc2.selectbox("Projection year", study["years"],
                             index=study["years"].index(study["default_year"]))
        rcp = gc3.selectbox("Climate pathway", study["rcps"],
                            index=study["rcps"].index(study["default_rcp"]),
                            format_func=lambda r: f"RCP {r}")
        study = materialize_study(study, year=year, rcp=rcp, district=district)
        st.caption(f"Showing **{district}** · year **{year}** · **RCP {rcp}**. "
                   "Defaults reproduce the report's Optimistic-vs-BaU 2050 (RCP 4.5) headline; "
                   "change any selector to explore the full projection grid.")

    sc1, sc2 = st.columns(2)
    sc1.markdown(f"**Country / region:** {study['country']} · {study['region']}")
    sc2.markdown(f"**Basis:** {study['basis']}")
    if study.get("publisher"):
        st.markdown(f"**Publisher:** {study['publisher']}  \n"
                    f"**Framework:** {study.get('framework', 'TEEBAgriFood')}.")
    st.markdown(study["summary"])
    src = study["source"]
    if study.get("url"):
        src += f"  ·  [source report]({study['url']})"
    st.caption(f"Source: {src}")

    meth = study.get("methodology")
    if meth:
        with st.expander("📐 Methodology & equations (as published in the report)"):
            st.markdown(f"**Framework** — {meth['framework']}")
            st.markdown("**Equations**")
            for eq in meth["equations"]:
                st.markdown(f"- {eq}")
            if meth.get("coefficients"):
                st.markdown("**Coefficients / valuation factors**")
                st.dataframe(pd.DataFrame(meth["coefficients"]), width='stretch', hide_index=True)
            st.markdown(f"**Data** — {meth['data']}")
            st.markdown("**Caveats (kept faithful to the report)**")
            for cav in meth["caveats"]:
                st.markdown(f"- {cav}")

    scenarios = list(study.get("scenarios") or {})

    # Some genuine reports (Uttarakhand, Assam) did not publish a single monetised four-capital
    # total. Rather than fabricate a ledger, we show their methodology and reported indicators.
    if not scenarios:
        st.info("ℹ️ This report did **not** publish a single monetised four-capital total, so there "
                "is no scenario ledger to compare. To stay faithful to the source, only the figures "
                "it actually reported are shown below (as indicators).")
        analytics.track_action(st, "teeb_study", study=study_name,
                               baseline=None, alternative=None)
        _render_teeb_indicators(study, expanded=True)
        return

    pc1, pc2 = st.columns(2)
    baseline = pc1.selectbox("Baseline scenario", scenarios, index=0)
    alt = pc2.selectbox("Alternative scenario", scenarios,
                        index=min(1, len(scenarios) - 1))

    # --- Sensitivity controls: one number input per adjustable line item ----
    overrides: dict[str, dict] = {}
    with st.expander("⚙️ Adjust the study's values (sensitivity analysis)", expanded=False):
        st.caption("Defaults are the study's figures. Change any value to see the comparison "
                   "re-compute live — the whole point of moving from a static report to a model.")
        for scen_name in {baseline, alt}:
            scen = study["scenarios"][scen_name]
            items = adjustable_items(scen)
            if not items:
                continue
            st.markdown(f"**{scen_name}**")
            cols = st.columns(2)
            ov = {}
            for i, it in enumerate(items):
                sign = "+" if it["kind"] == "benefit" else "−"
                ov[it["key"]] = cols[i % 2].number_input(
                    f"{sign} {it['label']}  ({it['unit']})",
                    value=float(it["value"]), step=max(float(it["value"]) / 20.0, 0.01),
                    key=f"{study_name}:{scen_name}:{it['key']}",
                    help=it["source"])
            overrides[scen_name] = ov

    cmp = compare_scenarios(study, baseline, alt, overrides)
    analytics.track_action(st, "teeb_study", study=study_name,
                           baseline=baseline, alternative=alt)

    m1, m2, m3 = st.columns(3)
    m1.metric(f"Net societal value: {alt} − {baseline}",
              _money(cmp['delta_net_societal']),
              delta=("net gain" if cmp["delta_net_societal"] > 0 else "net loss"))
    m2.metric("Farmer's private change", _money(cmp['delta_private']),
              help="Produced/financial capital only — what the farmer actually sees")
    m3.metric("External (society) change", _money(cmp['delta_external']),
              help="Natural + human + social capital — what markets leave out")
    st.caption(f"All figures per {study['basis']}.")

    st.download_button(
        "📄 Download study comparison PDF",
        report.teeb_study_pdf(study, cmp),
        file_name=f"agritrue_teeb_{study['country']}_{alt}.pdf".replace(" ", "_"),
        mime="application/pdf",
        on_click=lambda: analytics.track_action(st, "pdf_download", kind="teeb_study",
                                                study=study_name))

    left, right = st.columns([3, 2])
    with left:
        cap_colors = {"produced": "#457b9d", "natural": CAP_COLORS["environmental"],
                      "human": CAP_COLORS["health"], "social": CAP_COLORS["social"]}
        ddf = pd.DataFrame([
            {"capital": CAPITAL_LABELS[c], "delta": cmp["delta_by_capital"][c], "key": c}
            for c in CAPITALS])
        fig = px.bar(ddf, x="delta", y="capital", orientation="h", color="key",
                     color_discrete_map=cap_colors,
                     labels={"delta": f"Change in value ({study['basis']})", "capital": ""},
                     title=f"Change in each capital: {alt} vs {baseline}")
        fig.update_layout(height=360, showlegend=False)
        fig.add_vline(x=0, line_color="#444")
        st.plotly_chart(fig, width='stretch')
    with right:
        st.markdown("#### Net societal value by scenario")
        sdf = pd.DataFrame([
            {"scenario": baseline, "value": cmp["totals_a"]["net_societal"]},
            {"scenario": alt, "value": cmp["totals_b"]["net_societal"]},
        ])
        fig2 = px.bar(sdf, x="scenario", y="value",
                      color="scenario", color_discrete_sequence=["#8ab17d", "#2a9d8f"],
                      labels={"value": f"Net societal value ({study['basis']})", "scenario": ""})
        fig2.update_layout(height=360, showlegend=False)
        st.plotly_chart(fig2, width='stretch')

    # Core TEEBAgriFood policy signal: private vs societal divergence
    if cmp["delta_private"] < 0 < cmp["delta_net_societal"]:
        gap = -cmp["delta_private"]
        st.success(
            f"**Policy signal:** switching to **{alt}** costs the farmer "
            f"**{_money(gap)}** privately but delivers **{_money(cmp['delta_net_societal'])}** "
            f"in net value to society (per {study['basis']}). A results-based payment / PES of "
            f"up to {_money(gap)} would make the socially-optimal choice privately rational — "
            f"the central TEEBAgriFood argument.")
    elif cmp["delta_net_societal"] > 0 and cmp["delta_private"] >= 0:
        st.success(
            f"**Win–win:** **{alt}** improves both the farmer's private position "
            f"({_money(cmp['delta_private'])}) and net societal value "
            f"({_money(cmp['delta_net_societal'])}) per {study['basis']}.")

    with st.expander("📋 Full four-capital ledger (both scenarios)"):
        rows = []
        for scen_name, totals in ((baseline, cmp["totals_a"]), (alt, cmp["totals_b"])):
            for it in totals["items"]:
                rows.append({
                    "Scenario": scen_name,
                    "Capital": CAPITAL_LABELS[it["capital"]],
                    "Line item": it["label"],
                    "Benefit/Cost": it["kind"],
                    "Value": it["value"],
                    "Signed": it["signed"],
                    "Unit": it["unit"],
                    "Source": it["source"],
                })
        ledger = pd.DataFrame(rows)
        st.dataframe(ledger, width='stretch', hide_index=True)
        st.download_button(
            "Download ledger CSV", ledger.to_csv(index=False),
            f"agritrue_teeb_{study['country']}_ledger.csv".replace(" ", "_"), "text/csv")
        st.caption("Every value above is taken from the cited report (or derived from its published "
                   "figures, as the source note says) and is adjustable in the panel for sensitivity "
                   "analysis.")

    _render_teeb_indicators(study)


def _render_teeb_indicators(study, *, expanded=False):
    """Reported-but-not-monetised indicators for a study (context, never summed into totals)."""
    indicators = study.get("indicators")
    if not indicators:
        return
    with st.expander("📈 Reported indicators (not monetised on the ledger)", expanded=expanded):
        st.caption("These are reported by the study but on a different basis or not monetised, "
                   "so they are shown as context and are *not* summed into any monetary total.")
        idf = pd.DataFrame([
            {"Indicator": i["label"],
             "Baseline": i.get("baseline"), "Alternative": i.get("alternative"),
             "Unit": i["unit"], "Reported change": i["change"], "Source": i["source"]}
            for i in indicators])
        st.dataframe(idf, width='stretch', hide_index=True)


# --------------------------------------------------------------------------
VIEWS = {
    "Global & National Dashboard": view_dashboard,
    "True Price Calculator": view_calculator,
    "Diet True-Cost Comparator": view_diet,
    "Farm-Practice Comparator": view_comparator,
    "Localized TCA Studies": view_teeb_studies,
    "Methodology & Sources": view_methodology,
}
VIEWS[view]()
