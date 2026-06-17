"""
teeb_studies.py
===============
Localized TEEBAgriFood country-study scenarios for AgriTrue.

Where the rest of the app works from GLOBAL SOFA 2024 aggregates, this module reproduces
*localised*, fully-sourced country studies that APPLY the TEEBAgriFood Evaluation Framework.

PROVENANCE — important: these studies use the TEEBAgriFood four-capitals *framework* but are not
necessarily *published by* TEEB/UNEP. Each study therefore carries a `publisher`, a `framework`
note, and a `teeb_published` flag. The currently-encoded India (GIST Impact / Global Alliance) and
Kenya (CGIAR NATURE+ / IFPRI) studies are framework applications, not TEEB publications. Genuine
TEEB/UNEP publications (e.g. the Senegal rice value-chain study on teebweb.org, or Chapter 8 of the
2018 'Scientific & Economic Foundations' report) can be added the same way once their tables are
extracted. The Malawi maize study (Global Alliance, 2019) is intentionally NOT included: it is not a
TEEB publication and contains no monetised scenario comparison to reproduce.

Each study is encoded so that:

  1. the published report numbers are reproduced on screen by default,
  2. the report's own valuation equations, coefficients and caveats are shown alongside, and
  3. every line item is user-adjustable, so a reviewer can run instant sensitivity analysis
     — the value-add of moving from a static report to a live model.

DATA MODEL
----------
A study is a dict with:
    name, country, region, basis, currency, year, url, source, summary
    methodology : {framework, equations[], coefficients[], data, caveats[]}  — "the equations"
    scenarios   : {scenario_name: {"items": [line item, ...]}}                — the monetised ledger
    indicators  : [ {label, baseline, alternative, unit, change, source} ]    — reported but NOT
                  monetised on the ledger basis (context only; never summed into the totals)

Each line item is {"key","capital","label","value","unit","kind","source","adjustable"} where
  * capital ∈ {produced, natural, human, social}  — the TEEBAgriFood four-capital frame,
  * kind ∈ {"benefit","cost"}                     — benefits add, costs subtract,
  * value is a NON-NEGATIVE magnitude on the study's `basis`.

Net societal value of a scenario = Σ benefits − Σ costs. We surface the *private* net (produced
capital) separately from the *external* net (natural+human+social): the gap between them is the
core TEEBAgriFood policy signal — a practice can be privately marginal yet socially valuable.

FIDELITY
--------
Values come from the cited reports (see each item's `source`); a few are explicitly DERIVED from
published figures (e.g. cost of cultivation = gross − net income). Only the indicators a report
actually monetises appear on the ledger — e.g. the APCNF study does NOT monetise GHG, so no carbon
line is invented; the Kenya study excludes human-health costs (no data), so human capital is zero
there. Both facts are stated in the study caveats rather than papered over.
"""

from __future__ import annotations

from typing import Optional

CAPITALS = ("produced", "natural", "human", "social")
CAPITAL_LABELS = {
    "produced": "Produced / financial",
    "natural": "Natural / environmental",
    "human": "Human / health",
    "social": "Social",
}


# ---------------------------------------------------------------------------
# Aggregation engine  (pure, unit-testable; no study data dependency)
# ---------------------------------------------------------------------------
def _item_value(item: dict, overrides: Optional[dict]) -> float:
    """Resolve a line item's value, applying a user override by its `key` if present."""
    if overrides and item["key"] in overrides and overrides[item["key"]] is not None:
        return float(overrides[item["key"]])
    return float(item["value"])


def scenario_totals(scenario: dict, overrides: Optional[dict] = None) -> dict:
    """
    Aggregate one scenario's line items into per-capital and headline nets.

    Parameters
    ----------
    scenario  : dict   {"items": [line item, ...], ...}
    overrides : dict   optional {item_key: new_value} for sensitivity analysis

    Returns
    -------
    dict with: by_capital (net per capital), produced_net (private), external_net
    (natural+human+social), net_societal (all four), and the signed item list used.
    """
    by_capital = {c: 0.0 for c in CAPITALS}
    priced_items = []
    for item in scenario["items"]:
        val = _item_value(item, overrides)
        signed = val if item["kind"] == "benefit" else -val
        by_capital[item["capital"]] += signed
        priced_items.append({**item, "value": val, "signed": round(signed, 2)})

    produced_net = by_capital["produced"]
    external_net = by_capital["natural"] + by_capital["human"] + by_capital["social"]
    net_societal = produced_net + external_net
    return {
        "by_capital": {c: round(v, 2) for c, v in by_capital.items()},
        "produced_net": round(produced_net, 2),
        "external_net": round(external_net, 2),
        "net_societal": round(net_societal, 2),
        "items": priced_items,
    }


def compare_scenarios(
    study: dict,
    scenario_a: str,
    scenario_b: str,
    overrides: Optional[dict] = None,
) -> dict:
    """
    Compare two named scenarios within a study (B − A by convention: B is the alternative).

    `overrides` is keyed by scenario name -> {item_key: value}, so the two scenarios can be
    perturbed independently for sensitivity analysis.
    """
    for name in (scenario_a, scenario_b):
        if name not in study["scenarios"]:
            raise KeyError(f"Unknown scenario '{name}'. Options: {sorted(study['scenarios'])}")
    ov = overrides or {}
    ta = scenario_totals(study["scenarios"][scenario_a], ov.get(scenario_a))
    tb = scenario_totals(study["scenarios"][scenario_b], ov.get(scenario_b))

    delta_by_capital = {
        c: round(tb["by_capital"][c] - ta["by_capital"][c], 2) for c in CAPITALS
    }
    return {
        "study_basis": study["basis"],
        "scenario_a": scenario_a, "totals_a": ta,
        "scenario_b": scenario_b, "totals_b": tb,
        "delta_by_capital": delta_by_capital,
        "delta_private": round(tb["produced_net"] - ta["produced_net"], 2),
        "delta_external": round(tb["external_net"] - ta["external_net"], 2),
        "delta_net_societal": round(tb["net_societal"] - ta["net_societal"], 2),
    }


def study_scenarios(study_name: str) -> list[str]:
    """Convenience: scenario names for a study, in declared order."""
    return list(TEEB_STUDIES[study_name]["scenarios"].keys())


def adjustable_items(scenario: dict) -> list[dict]:
    """The subset of a scenario's items that should get a UI control."""
    return [it for it in scenario["items"] if it.get("adjustable", True)]


# ---------------------------------------------------------------------------
# PROJECTION STUDIES  (grid-based: policy x climate-pathway x year x district)
# ---------------------------------------------------------------------------
# Some studies (the TEEBAgriFood-India state studies) do not compare two fixed scenarios;
# they project each capital over a grid of policy scenario (BAU / Optimistic / Pessimistic) x
# climate pathway (RCP 4.5 / 8.5) x year x district. We keep the static `scenarios` data model
# above by *materialising* one (year, rcp, district) slice of the grid into the same
# {scenario_name: {"items": [...]}} shape the engine and app already consume.
#
# A projection study carries:
#   projection      : True
#   policies        : [display name, ...]      ordered; policy i indexes the value tuples
#   districts_data  : [real district name, ...]
#   aggregate_label : str                      a pseudo-district that SUMS all districts
#   districts       : [aggregate_label, *districts_data]   (what the UI offers)
#   years, rcps     : selectable values;  default_year, default_rcp
#   _grids          : {grid_key: {label, capital, unit, source, data}}
#                     where data[district][year][rcp] = (val_policy0, val_policy1, ...)
def _projection_scenarios(study: dict, year, rcp, district) -> dict:
    """Build {policy_name: {"items": [...]}} for one (year, rcp, district) slice of the grid."""
    policies = study["policies"]
    districts = study["districts_data"]
    aggregate = study["aggregate_label"]
    scenarios: dict[str, dict] = {}
    for pi, policy in enumerate(policies):
        items = []
        for gkey, g in study["_grids"].items():
            data = g["data"]
            if district == aggregate:
                val = sum(data[d][year][rcp][pi] for d in districts)
            else:
                val = data[district][year][rcp][pi]
            items.append(_item(gkey, g["capital"], g["label"], round(val, 4),
                               g["unit"], "benefit", g["source"]))
        scenarios[policy] = {"items": items}
    return scenarios


def materialize_study(study: dict, year=None, rcp=None, district=None) -> dict:
    """Return a concrete study with `scenarios` populated.

    Non-projection studies are returned unchanged. For a projection study, build the
    `scenarios` ledger for the chosen (year, rcp, district) — falling back to the study's
    declared defaults — so all downstream code (engine, app, PDF) works unmodified.
    """
    if not study.get("projection"):
        return study
    year = year if year is not None else study["default_year"]
    rcp = rcp if rcp is not None else study["default_rcp"]
    district = district if district is not None else study["aggregate_label"]
    out = dict(study)
    out["scenarios"] = _projection_scenarios(study, year, rcp, district)
    out["_selection"] = {"year": year, "rcp": rcp, "district": district}
    return out


# ---------------------------------------------------------------------------
# STUDY REGISTRY  (numbers taken from the cited reports; see module docstring)
# ---------------------------------------------------------------------------
def _item(key, capital, label, value, unit, kind, source, adjustable=True):
    return {"key": key, "capital": capital, "label": label, "value": value,
            "unit": unit, "kind": kind, "source": source, "adjustable": adjustable}


# ===========================================================================
# INDIA — APCNF (Andhra Pradesh Community-managed Natural Farming) TCA study
# "Natural Farming Through a Wide-Angle Lens" (GIST Impact / Global Alliance for the Future of
# Food / RySS, 2023), TEEBAgriFood Evaluation Framework. All values below are from the report's
# Table 18 (income, per ha, all farms) and Table 35 (cost of illness), at INR 1.00 = USD 0.013.
# ===========================================================================
_IN = "USD/ha/yr"
_IN_INCOME = ("APCNF TCA study 2023, Table 18 (per ha, all farms): gross income $2,413->$3,097 "
              "(+28.3% / +$684); net income $1,187->$2,364 (+99.1% / +$1,177). INR->USD 0.013.")
_IN_COST = ("Derived: cost of cultivation = gross - net income (Table 18). The report also reports "
            "input costs falling 44% on average with CNF adoption.")
_IN_HEALTH = ("APCNF TCA study 2023, Table 35: average economic loss from short-term pesticide "
              "symptoms INR 1,120 (chemical-intensive) vs INR 821 (CNF) = -26.7%. INR->USD 0.013.")

# ===========================================================================
# KENYA — "The True Costs of Food Production in Kenya" (CGIAR NATURE+ / IFPRI DP #2269, 2024)
# Benfica et al. 2024. Farm level, PPP $ per household per year. Values from the policy brief
# (Dec 2024): true cost $1,026 = direct $715 + external $311 ($260 social + $51 environmental).
# Direct breakdown = Fig 3; external breakdown = Fig 4. Human-health costs were NOT collected.
# ===========================================================================
_KE = "PPP USD/household/yr"
_KE_DIRECT = "Kenya True Costs study 2024 (IFPRI DP #2269), Fig 3 — direct production cost ($/household)."
_KE_SOC = "Kenya True Costs study 2024 (IFPRI DP #2269), Fig 4 — social externality ($/household)."
_KE_ENV = "Kenya True Costs study 2024 (IFPRI DP #2269), Fig 4 — environmental externality ($/household)."

# Kenya direct-cost lines are identical in both scenarios (they are not externalities).
_KE_DIRECT_ITEMS = lambda: [
    _item("hired_labour", "produced", "Hired labour", 220, _KE, "cost", _KE_DIRECT),
    _item("seed", "produced", "Seed", 148, _KE, "cost", _KE_DIRECT),
    _item("fertiliser", "produced", "Inorganic fertiliser", 93, _KE, "cost", _KE_DIRECT),
    _item("land_rental", "produced", "Land rental", 93, _KE, "cost", _KE_DIRECT),
    _item("equip_rental", "produced", "Equipment rental", 80, _KE, "cost", _KE_DIRECT),
    _item("energy", "produced", "Energy", 26, _KE, "cost", _KE_DIRECT),
    _item("pesticide", "produced", "Pesticide", 15, _KE, "cost", _KE_DIRECT),
    _item("water", "produced", "Water", 15, _KE, "cost", _KE_DIRECT),
    _item("other_direct", "produced", "Other direct costs", 25, _KE, "cost", _KE_DIRECT),
]


TEEB_STUDIES: dict[str, dict] = {
    "India — APCNF natural farming vs conventional (Andhra Pradesh)": {
        "name": "India — APCNF natural farming vs conventional (Andhra Pradesh)",
        "country": "India",
        "region": "South Asia",
        "publisher": "GIST Impact & Global Alliance for the Future of Food (with RySS / APCNF)",
        "framework": "TEEBAgriFood Evaluation Framework",
        "teeb_published": False,
        "basis": "USD per hectare per year",
        "currency": "USD (INR converted at 0.013); average farm ~1 ha, so per-ha ≈ per-household",
        "year": 2023,
        "url": "https://www.gistimpact.com/wp-content/uploads/2023/07/Natural-Farming-Through-A-Wide-Angle-Lens_July-2023_Final.pdf",
        "source": "Natural Farming Through a Wide-Angle Lens: TCA Study of Community-Managed Natural "
                  "Farming in Andhra Pradesh (GIST Impact / Global Alliance for the Future of Food / "
                  "RySS, 2023) — TEEBAgriFood Evaluation Framework.",
        "summary": "Andhra Pradesh Community-managed Natural Farming (**APCNF**, no synthetic inputs) "
                   "vs the conventional/chemical counterfactual. The report monetises **produced "
                   "capital** (income, per ha) and a **health** cost of illness; it reports — but does "
                   "not monetise — crop diversity, labour and pesticide use (shown as indicators). "
                   "Headline: gross income +28.3% (+$684/ha), net income +99.1% (+$1,177/ha), inputs "
                   "−44%, health costs −26%.",
        "methodology": {
            "framework": "TEEBAgriFood Evaluation Framework (four capitals: produced, natural, human, social).",
            "equations": [
                "Net income = Gross income − Cost of cultivation",
                "Health cost of illness = treatment expenditure + productivity loss "
                "(productive days lost × daily wage)",
                "USD = INR × 0.013   (and 1 ha = 2.47 acres)",
            ],
            "coefficients": [
                {"name": "INR → USD", "value": "0.013", "source": "Table 18 note"},
                {"name": "Hectare conversion", "value": "1 ha = 2.47 acres", "source": "Table 18 note"},
            ],
            "data": "Farm survey across 13 districts of Andhra Pradesh (Study 1) and 3 agro-ecological "
                    "zones — tribal, semi-arid, Godavari delta (Study 2). Counterfactuals: chemical-"
                    "intensive, low-input rainfed, and tribal organic farming.",
            "caveats": [
                "Two net-income measures exist: +49% across 13 districts (Study 1) vs +99.1% per ha "
                "across 3 zones (Study 2, used in this ledger).",
                "GHG / carbon is discussed qualitatively but NOT monetised in the study — no carbon "
                "line is shown.",
                "Health cost is per household; with average farm ≈ 1 ha it is treated as ≈ per ha.",
            ],
        },
        "scenarios": {
            "Conventional (counterfactual avg)": {"items": [
                _item("gross", "produced", "Gross crop income", 2413, _IN, "benefit", _IN_INCOME),
                _item("cost", "produced", "Cost of cultivation", 1226, _IN, "cost", _IN_COST),
                _item("health", "human", "Health cost (cost of illness, short-term symptoms)", 14.56, _IN, "cost", _IN_HEALTH),
            ]},
            "APCNF natural farming": {"items": [
                _item("gross", "produced", "Gross crop income (+28.3%)", 3097, _IN, "benefit", _IN_INCOME),
                _item("cost", "produced", "Cost of cultivation (inputs −44%)", 733, _IN, "cost", _IN_COST),
                _item("health", "human", "Health cost (−26%)", 10.67, _IN, "cost", _IN_HEALTH),
            ]},
        },
        "indicators": [
            {"label": "Crop diversity", "baseline": 2.1, "alternative": 4.0, "unit": "crops/farm",
             "change": "+88%", "source": "APCNF study 2023, Sec. 3 (avg 2.1 → 4 crops/farm)"},
            {"label": "Average crop yield", "baseline": None, "alternative": None, "unit": "—",
             "change": "+11%", "source": "APCNF study 2023, Study 1 (13 districts)"},
            {"label": "Input costs", "baseline": None, "alternative": None, "unit": "—",
             "change": "−44%", "source": "APCNF study 2023 (avg over study area)"},
            {"label": "On-farm labour use", "baseline": None, "alternative": None, "unit": "—",
             "change": "+20%", "source": "APCNF study 2023, Sec. 3.6"},
        ],
    },
    "Kenya — true cost of farm food production (CGIAR NATURE+ / IFPRI)": {
        "name": "Kenya — true cost of farm food production (CGIAR NATURE+ / IFPRI)",
        "country": "Kenya",
        "region": "Sub-Saharan Africa",
        "publisher": "CGIAR NATURE+ / IFPRI (Benfica et al., Discussion Paper #2269)",
        "framework": "TEEBAgriFood framework + TCA Handbook (2022)",
        "teeb_published": False,
        "basis": "PPP USD per household per year",
        "currency": "Purchasing-power-parity (PPP) USD",
        "year": 2024,
        "url": "https://cgspace.cgiar.org/server/api/core/bitstreams/955317f4-9697-44c5-94eb-4a610d2d780c/content",
        "source": "The True Costs of Food Production in Kenya (Benfica et al., CGIAR NATURE+ / IFPRI "
                  "Discussion Paper #2269, 2024). Farm-level true cost ≈ $1,026/household/yr.",
        "summary": "A true-cost **decomposition** of smallholder crop production at NATURE+ sites "
                   "(Kajiado, Kisumu, Vihiga). Comparing the **market (direct) cost** with the **true "
                   "cost** exposes the externalities — the report's own 'true cost gap' (Fig 1). The "
                   "hidden ≈ **$311/household/yr** is overwhelmingly **social** (forced labour $76, "
                   "child labour $54, underpayment $44, gender wage gap $40 …); environmental is small "
                   "(land occupation $46, soil $5). Health costs were not collected.",
        "methodology": {
            "framework": "TEEBAgriFood framework + TCA Handbook (2022); monetisation via Impact "
                         "Institute / True Price (2021) factors and the Global Impact Database (GID).",
            "equations": [
                "True cost = Direct production cost + Σ External costs  (external = the 'true cost gap')",
                "External cost = Σ (impact quantity × monetisation factor)  over each social / "
                "environmental indicator",
                "Child-labour cost = compensation for lost future earnings (out-of-school) + harm "
                "from hazardous work",
            ],
            "coefficients": [
                {"name": "Monetisation factors", "value": "Impact Institute / True Price (2021) + GID",
                 "source": "brief Figs 2–4"},
                {"name": "Currency", "value": "PPP USD", "source": "brief p.4"},
            ],
            "data": "Household survey N=1,102 (Kajiado, Kisumu, Vihiga; May–Jul 2023); worker survey "
                    "N=1,056; national crop-sector analysis via the Global Impact Database.",
            "caveats": [
                "Human-HEALTH externalities were NOT included (data not collected) — human capital = 0.",
                "Direct costs exclude unpaid family / free labour (would raise labour cost).",
                "National crop-sector external costs = 27% of output value (90% social / 10% env); "
                "farm-level external = 30% of true cost (84% social / 16% env).",
            ],
        },
        "scenarios": {
            "Market (direct) cost": {"items": _KE_DIRECT_ITEMS()},
            "True cost (incl. externalities)": {"items": _KE_DIRECT_ITEMS() + [
                _item("forced_labour", "social", "Forced labour", 76, _KE, "cost", _KE_SOC),
                _item("child_labour", "social", "Child labour", 54, _KE, "cost", _KE_SOC),
                _item("underpayment", "social", "Underpayment / insufficient income", 44, _KE, "cost", _KE_SOC),
                _item("gender_gap", "social", "Gender wage gap", 40, _KE, "cost", _KE_SOC),
                _item("harassment", "social", "Occurrence of harassment", 34, _KE, "cost", _KE_SOC),
                _item("workplace_hs", "social", "Workplace health & safety incidents", 12, _KE, "cost", _KE_SOC),
                _item("overtime", "social", "Excessive / underpaid overtime", 1, _KE, "cost", _KE_SOC),
                _item("land_occ", "natural", "Land occupation (biodiversity / ecosystem services)", 46, _KE, "cost", _KE_ENV),
                _item("soil_deg", "natural", "Soil degradation", 5, _KE, "cost", _KE_ENV),
                _item("climate", "natural", "Contribution to climate change", 0.3, _KE, "cost", _KE_ENV),
            ]},
        },
        "indicators": [
            {"label": "External (hidden) share of true cost", "baseline": None, "alternative": 30,
             "unit": "%", "change": "30% of true cost (84% social / 16% env)", "source": "brief Fig 2"},
            {"label": "National crop-sector external / output value", "baseline": None,
             "alternative": 27, "unit": "%", "change": "27% (90% social / 10% env)", "source": "brief Table 1"},
            {"label": "Direct cost / gross crop income", "baseline": None, "alternative": 62,
             "unit": "%", "change": "62%", "source": "brief p.5"},
        ],
    },
}


# ===========================================================================
# GENUINE TEEB / UNEP-PUBLISHED LOCALIZED STUDIES
# TEEBAgriFood Initiative in India (UNEP, EU-funded, 2019-2023): state synthesis reports.
# Unlike the two studies above, these ARE TEEB/UNEP publications (teeb_published=True).
# They are *scenario-projection* studies — organic-farming + agroforestry expansion under
# BAU / Optimistic / Pessimistic policy, crossed with climate pathways (RCP 4.5 / 8.5),
# projected to 2030 & 2050, by district.
#
# FIDELITY NOTE (important — these go to real TEEB/TCAA people): of the three state reports,
# only UTTAR PRADESH (ICAR-IIFSR) published a full monetised grid (Tables 2 & 3, Billion USD).
# UTTARAKHAND (GBPUAT) monetised only selected ecosystem services for two watersheds, and
# ASSAM (CAFRI) reported almost everything as physical stocks or % changes. We therefore encode
# UP as a full comparable ledger and keep Uttarakhand & Assam as honest, indicator-only studies
# rather than fabricate a monetised four-capital total the reports never produced.
# ===========================================================================
_TEEB_INDIA_URL = "https://teebweb.org/our-work/agrifood/"

# --- Uttar Pradesh: per-district economic value, Billion USD ----------------
# data[district][year][rcp] = (BAU, Optimistic, Pessimistic)
_UP_DISTRICTS = ["Meerut", "Aligarh", "Bulandshahr", "Mirzapur", "Hamirpur"]
_UP_NAT = {  # Natural capital, Table 2 (C sequestration + water yield + sediment), BUSD
    "Meerut":      {2030: {"4.5": (2.80, 2.93, 2.78), "8.5": (2.83, 2.96, 2.81)},
                    2050: {"4.5": (2.96, 3.25, 2.92), "8.5": (2.98, 3.25, 2.92)}},
    "Aligarh":     {2030: {"4.5": (3.43, 3.62, 3.41), "8.5": (3.37, 3.64, 3.35)},
                    2050: {"4.5": (4.11, 5.08, 3.99), "8.5": (3.98, 4.84, 3.80)}},
    "Bulandshahr": {2030: {"4.5": (3.93, 4.10, 3.91), "8.5": (4.04, 4.25, 4.03)},
                    2050: {"4.5": (4.42, 4.98, 4.32), "8.5": (4.48, 5.07, 4.40)}},
    "Mirzapur":    {2030: {"4.5": (17.69, 17.87, 17.62), "8.5": (14.51, 14.93, 14.46)},
                    2050: {"4.5": (16.56, 17.23, 16.38), "8.5": (12.61, 14.05, 12.37)}},
    "Hamirpur":    {2030: {"4.5": (3.03, 3.24, 3.00), "8.5": (2.96, 3.16, 2.93)},
                    2050: {"4.5": (3.05, 3.42, 2.96), "8.5": (3.02, 3.39, 2.93)}},
}
_UP_PROD = {  # Produced capital, Table 3 (crop + timber economic yield), BUSD
    "Meerut":      {2030: {"4.5": (1.6053, 1.6123, 1.5950), "8.5": (1.7498, 1.7583, 1.7371)},
                    2050: {"4.5": (1.6410, 1.8816, 1.5508), "8.5": (1.5970, 1.8780, 1.4917)}},
    "Aligarh":     {2030: {"4.5": (0.1837, 0.1845, 0.1825), "8.5": (0.1954, 0.1961, 0.1943)},
                    2050: {"4.5": (0.2048, 0.2307, 0.1951), "8.5": (0.1632, 0.1822, 0.1561)}},
    "Bulandshahr": {2030: {"4.5": (1.1491, 1.1541, 1.1416), "8.5": (1.1987, 1.2044, 1.1902)},
                    2050: {"4.5": (1.1739, 1.3672, 1.1015), "8.5": (1.1476, 1.3365, 1.0768)}},
    "Mirzapur":    {2030: {"4.5": (0.3190, 0.3200, 0.3176), "8.5": (0.3241, 0.3251, 0.3227)},
                    2050: {"4.5": (0.2414, 0.2930, 0.2221), "8.5": (0.2298, 0.2910, 0.2068)}},
    "Hamirpur":    {2030: {"4.5": (0.3237, 0.3251, 0.3217), "8.5": (0.2908, 0.2921, 0.2889)},
                    2050: {"4.5": (0.3280, 0.3792, 0.3088), "8.5": (0.3098, 0.3584, 0.2915)}},
}
_UP_NAT_SRC = ("UP synthesis report, Table 2 — natural-capital economic value "
               "(carbon sequestration + water yield + sediment), Billion USD, by district.")
_UP_PROD_SRC = ("UP synthesis report, Table 3 — produced-capital economic value "
                "(crop + timber yield; organic priced 20% above conventional), Billion USD.")
_UP_AGG = "State total (5 study districts)"

TEEB_STUDIES["Uttar Pradesh — organic & agroforestry expansion (TEEBAgriFood India)"] = {
    "name": "Uttar Pradesh — organic & agroforestry expansion (TEEBAgriFood India)",
    "country": "India",
    "region": "North India (Uttar Pradesh)",
    "publisher": "ICAR-Indian Institute of Farming Systems Research (IIFSR), Modipuram — UNEP TEEBAgriFood Initiative in India",
    "framework": "TEEBAgriFood Evaluation Framework",
    "teeb_published": True,
    "basis": "Billion USD per year (economic value of natural + produced capital)",
    "currency": "USD (billion). Produced capital = crop + timber economic yield (organic priced 20% above conventional).",
    "year": 2023,
    "url": _TEEB_INDIA_URL,
    "source": "Synthesis Report: TEEB for Agriculture & Food Application in Uttar Pradesh "
              "(ICAR-IIFSR; UNEP TEEBAgriFood Initiative in India, EU-funded, 2023).",
    "summary": "A **TEEBAgriFood-India** study projecting the value of expanding **organic "
               "farming + agroforestry** across five UP districts (Meerut, Aligarh, Bulandshahr, "
               "Mirzapur, Hamirpur). It monetises **natural capital** (carbon + water yield + "
               "sediment) and **produced capital** (crop + timber) in Billion USD under three "
               "policy scenarios × two climate pathways (RCP 4.5/8.5) to 2030 & 2050. The default "
               "view compares the report's **Optimistic policy vs Business-as-usual at 2050 (RCP 4.5), "
               "summed over the five districts** — use the selectors to change district, year or "
               "climate pathway. Social capital (SLSI), agro-biodiversity, women's workdays and "
               "malaria risk are reported separately (indicators), as in the report.",
    "methodology": {
        "framework": "TEEBAgriFood Evaluation Framework (four capitals). Spatial modelling with "
                     "InVEST (carbon, water yield, sediment, crop provisioning) under RCP 4.5/8.5.",
        "equations": [
            "Natural-capital value = carbon-sequestration value + water-yield value + sediment value (Table 2 total)",
            "Produced-capital value = crop economic yield + timber economic yield",
            "Organic produce priced at 20% above the conventional maximum selling price",
            "State total = Σ over the 5 study districts (area-weighted within each district)",
        ],
        "coefficients": [
            {"name": "Organic price premium", "value": "+20% vs conventional", "source": "report §Produced capital"},
            {"name": "Sediment value", "value": "Rs. 60 / cu.m", "source": "CWC 2012 (report §1.3)"},
            {"name": "Climate pathways", "value": "RCP 4.5 & RCP 8.5", "source": "report scenario design"},
        ],
        "data": "Five districts across UP agro-climatic zones. Area accounted: Meerut 64.1%, Aligarh "
                "29.7%, Bulandshahr 37.8%, Mirzapur 52.9%, Hamirpur 45.8% of district area. "
                "2020 is the base year; scenarios run to 2030 and 2050.",
        "caveats": [
            "Natural + produced capital are both in Billion USD and comparable; SOCIAL capital is "
            "reported on a different basis (SLSI, USD/household/ha) and HUMAN health as malaria-risk "
            "area (%), so neither is summed into the monetary ledger — both appear as indicators.",
            "The report's natural-capital total adds the sediment term to carbon + water yield; we "
            "reproduce the report's published Table 2 totals exactly.",
            "Hamirpur's natural-capital value is dominated by carbon storage (water/sediment not modelled there).",
            "Mirzapur shows much higher and more climate-sensitive natural-capital value (large forest "
            "carbon stock), which dominates the state total.",
        ],
    },
    "indicators": [
        {"label": "SLSI — Aligarh (sustainable livelihood security)", "baseline": 73200.0,
         "alternative": 78087.7, "unit": "USD/HH/ha", "change": "organic > inorganic", "source": "UP report, Table 4"},
        {"label": "SLSI — Bulandshahr", "baseline": 70723.0, "alternative": 74939.0,
         "unit": "USD/HH/ha", "change": "organic > inorganic", "source": "UP report, Table 4"},
        {"label": "SLSI — Meerut", "baseline": 69123.6, "alternative": 71799.3,
         "unit": "USD/HH/ha", "change": "organic > inorganic", "source": "UP report, Table 4"},
        {"label": "SLSI — Hamirpur", "baseline": 27427.2, "alternative": 24058.8,
         "unit": "USD/HH/ha", "change": "organic < inorganic", "source": "UP report, Table 4"},
        {"label": "SLSI — Mirzapur", "baseline": 32345.0, "alternative": 26635.7,
         "unit": "USD/HH/ha", "change": "organic < inorganic", "source": "UP report, Table 4"},
        {"label": "Agro-biodiversity index (Meerut, organic vs conventional)", "baseline": 50.86,
         "alternative": 57.21, "unit": "ADI", "change": "organic higher in all districts", "source": "UP report, Fig 3"},
        {"label": "Women's share of farm workdays (organic)", "baseline": None, "alternative": None,
         "unit": "% of workdays", "change": "52-59% across districts", "source": "UP report §3.2"},
        {"label": "Malaria-risk area under land-use/climate change", "baseline": None, "alternative": None,
         "unit": "%", "change": "no significant change (BaU/Optimistic/Pessimistic)", "source": "UP report §4"},
    ],
    # --- projection grid wiring ---
    "projection": True,
    "policies": ["Business-as-usual", "Optimistic policy", "Pessimistic policy"],
    "districts_data": _UP_DISTRICTS,
    "aggregate_label": _UP_AGG,
    "districts": [_UP_AGG, *_UP_DISTRICTS],
    "years": [2030, 2050],
    "rcps": ["4.5", "8.5"],
    "default_year": 2050,
    "default_rcp": "4.5",
    "_grids": {
        "natural": {"label": "Natural capital (C sequestration + water yield + sediment)",
                    "capital": "natural", "unit": "BUSD/yr", "source": _UP_NAT_SRC, "data": _UP_NAT},
        "produced": {"label": "Produced capital (crop + timber yield)",
                     "capital": "produced", "unit": "BUSD/yr", "source": _UP_PROD_SRC, "data": _UP_PROD},
    },
}

# --- Uttarakhand: indicator-only (selected monetised services for 2 watersheds) ---
_UK_SRC = "Uttarakhand synthesis report (GBPUAT; TEEBAgriFood India), Summary of Results."
TEEB_STUDIES["Uttarakhand — organic & agroforestry scaling (TEEBAgriFood India)"] = {
    "name": "Uttarakhand — organic & agroforestry scaling (TEEBAgriFood India)",
    "country": "India",
    "region": "North India / Himalaya (Uttarakhand)",
    "publisher": "G.B. Pant University of Agriculture & Technology (GBPUAT), Pantnagar — UNEP TEEBAgriFood Initiative in India",
    "framework": "TEEBAgriFood Evaluation Framework",
    "teeb_published": True,
    "basis": "Selected ecosystem-service values for the Kosi & Kailash watersheds — the report did "
             "NOT publish a single monetised four-capital total, so no ledger is shown",
    "currency": "Mixed (million USD; timber in lakh INR), as reported",
    "year": 2023,
    "url": _TEEB_INDIA_URL,
    "source": "Synthesis Report: TEEBAgriFood Initiative in Uttarakhand (GBPUAT; UNEP TEEBAgriFood "
              "Initiative in India, EU-funded, 2023).",
    "summary": "A **TEEBAgriFood-India** study of scaling organic farming + agroforestry "
               "(per Uttarakhand Vision 2030) in the Kosi (hill) and Kailash watersheds. The report "
               "valued only **selected ecosystem services** and did **not** produce a single "
               "monetised four-capital total — so it is reported here as **indicators** "
               "rather than a comparable ledger. Headline: the optimistic (organic + agroforestry "
               "expansion) scenario improves erosion control, carbon storage, nutrient control and "
               "farmer income from timber, while moderating excess monsoon runoff.",
    "methodology": {
        "framework": "TEEBAgriFood framework; InVEST modelling of water yield, sediment, nutrient "
                     "export, carbon and crop provisioning under RCP 4.5 / 8.5 to 2050.",
        "equations": [
            "Service values reported per watershed (water yield, soil-erosion control, timber provisioning)",
            "Policy scenarios = area under organic farming + agroforestry "
            "(BAU vs Optimistic vs Pessimistic), per the hill/plain scenario tables",
        ],
        "coefficients": [
            {"name": "Optimistic organic area (hills)", "value": "up to 95% of cultivated area",
             "source": "UK report, Table 1"},
            {"name": "Agroforestry growth (optimistic)", "value": "+3.5% / yr", "source": "UK report, Table 1/2"},
        ],
        "data": "Field demonstration plots at Sunkiya (hills, Nainital) and Bidaura (plains, Udham "
                "Singh Nagar); InVEST modelling of the Kosi & Kailash watersheds to 2050.",
        "caveats": [
            "The report monetised only SELECTED services for TWO watersheds; it published no "
            "summed four-capital total, so no monetary ledger is shown (indicators only).",
            "The two water-yield figures are reported under DIFFERENT climate pathways (BAU at RCP 8.5 "
            "vs Optimistic at RCP 4.5); higher water yield reflects monsoon runoff, not pure benefit.",
            "Crop-yield effects are described qualitatively: organic yields dip then recover by the "
            "second year of transition; not monetised here.",
        ],
    },
    "scenarios": {},  # no monetised ledger — indicators only
    "indicators": [
        {"label": "Water-yield service value (Kosi + Kailash)", "baseline": 140.96, "alternative": 132.68,
         "unit": "million USD/yr", "change": "BaU(RCP8.5) 140.96 → Optimistic(RCP4.5) 132.68; "
         "optimistic moderates excess runoff", "source": _UK_SRC + " (2020 base 120.66)"},
        {"label": "Soil-erosion-control service (Kosi watershed, 2050)", "baseline": 12.2, "alternative": 11.7,
         "unit": "million USD/yr", "change": "less erosion to control under optimistic scaling",
         "source": _UK_SRC + " (present 8.2)"},
        {"label": "Timber provisioning gain, optimistic (Kosi + Kailash)", "baseline": None,
         "alternative": 844.36, "unit": "lakh INR/yr", "change": "Kosi 683.84 + Kailash 160.52 lakh INR",
         "source": _UK_SRC},
        {"label": "Organic area, hill region (optimistic vs BaU)", "baseline": 65, "alternative": 95,
         "unit": "% of cultivated area", "change": "BaU 65% → Optimistic 95%", "source": "UK report, Table 1"},
    ],
}

# --- Assam: indicator-only (mostly physical stocks & % changes) -------------
_AS_SRC = "Assam synthesis report (ICAR-CAFRI; TEEBAgriFood India), Key Results."
TEEB_STUDIES["Assam — organic & agroforestry projections (TEEBAgriFood India)"] = {
    "name": "Assam — organic & agroforestry projections (TEEBAgriFood India)",
    "country": "India",
    "region": "Northeast India (Assam)",
    "publisher": "ICAR-Central Agroforestry Research Institute (CAFRI), Jhansi — UNEP TEEBAgriFood Initiative in India",
    "framework": "TEEBAgriFood Evaluation Framework",
    "teeb_published": True,
    "basis": "Projected physical stocks & percentage changes — the report monetised almost nothing "
             "in absolute terms, so no ledger is shown",
    "currency": "Mostly non-monetary; two absolute USD figures reported (see indicators)",
    "year": 2023,
    "url": _TEEB_INDIA_URL,
    "source": "Synthesis Report: TEEB for Agriculture & Food Application in Assam (ICAR-CAFRI; UNEP "
              "TEEBAgriFood Initiative in India, EU-funded, 2023).",
    "summary": "A **TEEBAgriFood-India** study (conducted in the initiative's final year, on "
               "a compressed timeframe) projecting organic-farming + agroforestry expansion to 2030/"
               "2040/2050 under BAU / Optimistic / Pessimistic policy (RCP 4.5). It reports four-"
               "capital changes mainly as **physical stocks and percentage changes** rather than a "
               "monetised ledger — so it is reported here as **indicators**. Headline: the "
               "optimistic scenario lifts organic area to ~20% of the gross cropped area, raises soil "
               "carbon and paddy/tea value, and expands SHGs and FPOs.",
    "methodology": {
        "framework": "TEEBAgriFood framework. Natural: CASA model for NPP + RUSLE for soil erosion. "
                     "Produced: econometric/trend models for rice, tea, bamboo. Social: SHG/FPO & "
                     "social-capital-index trend analysis.",
        "equations": [
            "Projections from historical trends → hectarage under organic / agroforestry in 2030/40/50",
            "Soil organic carbon stock = area × 94.70 Mg C/ha (0-100 cm); agroforestry SOC 79.16 t C/ha (0-90 cm)",
            "Workforce value via agricultural gross value added (AGVA) per worker",
        ],
        "coefficients": [
            {"name": "Cropland SOC", "value": "94.70 Mg C/ha (0-100 cm)", "source": "Rekwar & Ahmed 2022"},
            {"name": "Agroforestry SOC", "value": "79.16 t C/ha (0-90 cm)", "source": "ICAR-CAFRI"},
        ],
        "data": "State-level assessment from secondary data and remote sensing (CASA/RUSLE); two "
                "stakeholder consultations in Guwahati (Sep & Nov 2023).",
        "caveats": [
            "Assam was added in the initiative's final year; the study is a state-level trend "
            "projection, NOT a monetised four-capital ledger — so no monetary comparison is shown.",
            "The only absolute monetary values reported are the NPP / green-cover value (US$0.17 bn, "
            "existing land use) and agricultural GVA (~US$1,600 / worker, optimistic 2050).",
            "GHG / carbon is reported as physical soil-carbon stocks (million Mg), not monetised.",
            "No conventional-vs-organic comparative field study was done (noted as a future need).",
        ],
    },
    "scenarios": {},  # no monetised ledger — indicators only
    "indicators": [
        {"label": "Organic area by 2050 (Pessimistic / BaU / Optimistic)", "baseline": 386117,
         "alternative": 625341, "unit": "ha", "change": "30,177 (0.97%) / 386,117 (4.94%) / 625,341 (20% of GCA)",
         "source": _AS_SRC},
        {"label": "Soil organic carbon stock by 2050 (Pess / BaU / Opt)", "baseline": 37,
         "alternative": 59, "unit": "million Mg", "change": "3 / 37 / 59 million Mg", "source": _AS_SRC},
        {"label": "NPP / green-cover value (existing land use)", "baseline": None, "alternative": 0.17,
         "unit": "billion USD", "change": "green cover declining 150 → 56 kg C/m² by 2050", "source": _AS_SRC},
        {"label": "Paddy value, optimistic vs BaU (2030/40/50)", "baseline": None, "alternative": None,
         "unit": "%", "change": "+6% / +14% / +25%", "source": _AS_SRC},
        {"label": "Tea value, optimistic vs BaU", "baseline": None, "alternative": None,
         "unit": "%", "change": "+3.46% (2030) → +12% (2050); pessimistic −0.40 to −1.42%", "source": _AS_SRC},
        {"label": "Agricultural GVA per worker (optimistic 2050)", "baseline": None, "alternative": 1600,
         "unit": "USD/worker", "change": "~1,600 USD/worker", "source": _AS_SRC},
        {"label": "Bamboo carbon stock (optimistic, 2030 → 2050)", "baseline": 1.90, "alternative": 3.16,
         "unit": "million Mg/yr", "change": "1.90 → 3.16", "source": _AS_SRC},
        {"label": "Self-Help Groups (2021-22 → 2050, optimistic)", "baseline": 6758, "alternative": 27815,
         "unit": "SHGs", "change": "6,758 → 27,815", "source": _AS_SRC},
        {"label": "Farmer Producer Organisations (2030 → 2050, optimistic)", "baseline": 667,
         "alternative": 6442, "unit": "FPOs", "change": "667 → 6,442", "source": _AS_SRC},
        {"label": "Average annual soil loss (2021 → 2030 → 2050, RCP 4.5)", "baseline": 22,
         "alternative": 31, "unit": "t/ha", "change": "20 → 22 → 31", "source": _AS_SRC},
    ],
}


# ===========================================================================
# AGROFORESTRY FEEDER STUDY — "Agroforestry: an attractive REDD+ policy option?"
# UNEP TEEB with World Agroforestry Centre (ICRAF) and UNEP-WCMC, Oct 2015. Edited by
# Salman Hussain & Kavita Sharma (UNEP TEEB) and Ivo Mulder (UNEP) — a genuine TEEB/UNEP
# publication (teeb_published=True). Three case studies value the CHANGE in ecosystem-service
# value of converting an agroforestry system to an alternative land use (and of enhancing it),
# in 2013 US$ PPP, at landscape scale (Tables 2/3/4 of the executive summary).
#
# DATA MODEL NOTE: the report tabulates CHANGES relative to the baseline agroforestry system
# (it does not publish absolute per-service landscape totals). We therefore encode the baseline
# agroforestry system as a zero reference and each scenario as the report's published deltas,
# with the EXACT table signs preserved (positive value -> benefit, negative -> cost). Only the
# leaf line items are encoded (the "Provisioning" / "Other regulating" rows are their subtotals).
# Provisioning -> produced capital; carbon / water yield / soil erosion -> natural capital. The
# report does NOT monetise human or social capital (stated in caveats).
# ===========================================================================
_AGF = "million USD/yr (2013 US$ PPP, landscape scale)"
_AGF_PUB = "UNEP TEEB, with the World Agroforestry Centre (ICRAF) and UNEP-WCMC"
_AGF_URL = "https://teebweb.org/our-work/agrifood/"
_AGF_METH = {
    "framework": "Total Economic Value (TEV) of ecosystem services, mapped to the TEEBAgriFood "
                 "four capitals. Provisioning + regulating/supporting services valued; WaterWorld "
                 "model used to infer service change under land-use scenarios.",
    "equations": [
        "Asset value = net present value at maturity, 10% real discount rate, 20-year horizon "
        "(sensitivity 2.5%–20%)",
        "Provisioning value = gross margin (output value − variable cost); no price premiums",
        "Tabulated figures are CHANGES vs the baseline agroforestry system (Δ million US$/yr)",
    ],
    "coefficients": [
        {"name": "Carbon price (private)", "value": "US$6.50 / t (used in scenarios)", "source": "Forest Trends 2013"},
        {"name": "Carbon (social cost, upper bound)", "value": "US$40.3 / t", "source": "US EPA (sensitivity only)"},
        {"name": "Currency", "value": "2013 US$ (PPP-adjusted)", "source": "report methods"},
        {"name": "Discount rate", "value": "10% real (20-yr NPV)", "source": "report methods"},
    ],
    "data": "Extensive literature/benefit-transfer review plus spatial WaterWorld modelling for "
            "three systems: coffee agroforestry (Ethiopia), shaded cocoa (Ghana), Ngitili "
            "woodland (Tanzania).",
    "caveats": [
        "Values are CHANGES vs the baseline agroforestry system, exactly as the report's Tables "
        "2–4 present them; the agroforestry baseline is the zero reference (no absolute landscape "
        "totals were published).",
        "HUMAN and SOCIAL capital are NOT monetised; biodiversity, water quality and pollination "
        "are noted qualitatively only — so a positive monetised conversion result (e.g. cocoa→full "
        "sun) omits exactly the services where agroforestry's advantage lies.",
        "Carbon valued at the private US$6.50/t lower bound; the US$40.3/t social cost is used only "
        "in sensitivity analysis.",
        "Built largely on benefit transfer from comparable sites (the report flags the added uncertainty).",
        "Ghana soil-erosion change is 'ND' (not determined) and is omitted from the ledger.",
    ],
}

TEEB_STUDIES["Agroforestry — coffee vs maize (Ethiopia, TEEB/ICRAF REDD+)"] = {
    "name": "Agroforestry — coffee vs maize (Ethiopia, TEEB/ICRAF REDD+)",
    "country": "Ethiopia", "region": "East Africa",
    "publisher": _AGF_PUB, "framework": "TEEBAgriFood / TEEB REDD+ (TEV of ecosystem services)",
    "teeb_published": True,
    "basis": "million USD per year (Δ ecosystem-service value vs baseline coffee agroforestry)",
    "currency": "2013 US$ (PPP); landscape scale over the mapped agroforestry area",
    "year": 2015, "url": _AGF_URL,
    "source": "Agroforestry: an attractive REDD+ policy option? (UNEP TEEB / ICRAF / UNEP-WCMC, "
              "2015), coffee-agroforestry case, Ethiopia — Table 2.",
    "summary": "Coffee agroforestry stores 49–150 t C/ha (≈$865M over the area) and yields "
               "provisioning worth $1,100–2,500/ha/yr vs only $450/ha/yr for maize; NPV $2,750–"
               "29,300/ha vs $900–3,000/ha for maize. **Converting the area to maize** would gain "
               "~$90M/yr of maize but lose ~$116M coffee, ~$13M other provisioning and ~$435M of "
               "carbon regulation — a large net societal loss. The other scenarios (raise canopy "
               "≥30%, and ≥30% + expansion) show the regulating-service gains from *enhancing* "
               "agroforestry. Human & social capital are not monetised.",
    "methodology": _AGF_METH,
    "scenarios": {
        "Coffee agroforestry retained (baseline = 0 reference)": {"items": []},
        "Convert to maize (Scenario 1)": {"items": [
            _item("coffee", "produced", "Coffee production", 115.9, _AGF, "cost",
                  "Table 2, Convert-to-maize: coffee −$115.9M/yr"),
            _item("maize", "produced", "Maize production", 90.5, _AGF, "benefit",
                  "Table 2, Convert-to-maize: maize +$90.5M/yr"),
            _item("other_prov", "produced", "Other provisioning (fuelwood, honey)", 13, _AGF, "cost",
                  "Table 2, Convert-to-maize: other provisioning −$13M/yr"),
            _item("carbon", "natural", "Carbon regulation", 435, _AGF, "cost",
                  "Table 2, Convert-to-maize: carbon regulation −$435M/yr"),
            _item("water", "natural", "Water yield", 34.9, _AGF, "cost",
                  "Table 2, Convert-to-maize: water yield −$34.9M/yr"),
            _item("soil", "natural", "Soil erosion control", 15.9, _AGF, "benefit",
                  "Table 2, Convert-to-maize: soil-erosion line +$15.9M/yr (report's sign)"),
        ]},
        "Raise canopy ≥30% (Scenario 2)": {"items": [
            _item("carbon", "natural", "Carbon regulation", 292, _AGF, "benefit", "Table 2, Scenario 2: carbon +$292M/yr"),
            _item("water", "natural", "Water yield", 58.6, _AGF, "benefit", "Table 2, Scenario 2: water yield +$58.6M/yr"),
            _item("soil", "natural", "Soil erosion control", 15.9, _AGF, "benefit", "Table 2, Scenario 2: soil erosion +$15.9M/yr"),
        ]},
        "Raise canopy ≥30% + expansion (Scenario 3)": {"items": [
            _item("coffee", "produced", "Coffee production", 143.9, _AGF, "benefit", "Table 2, Scenario 3: coffee +$143.9M/yr"),
            _item("maize", "produced", "Maize production", 128.3, _AGF, "cost", "Table 2, Scenario 3: maize −$128.3M/yr"),
            _item("other_prov", "produced", "Other provisioning (fuelwood, honey)", 57.9, _AGF, "benefit", "Table 2, Scenario 3: other provisioning +$57.9M/yr"),
            _item("carbon", "natural", "Carbon regulation", 655, _AGF, "benefit", "Table 2, Scenario 3: carbon +$655M/yr"),
            _item("water", "natural", "Water yield", 10.7, _AGF, "benefit", "Table 2, Scenario 3: water yield +$10.7M/yr"),
            _item("soil", "natural", "Soil erosion control", 43.6, _AGF, "benefit", "Table 2, Scenario 3: soil erosion +$43.6M/yr"),
        ]},
    },
    "indicators": [
        {"label": "Coffee agroforestry provisioning value", "baseline": 450, "alternative": 2500,
         "unit": "USD/ha/yr", "change": "maize $450/ha vs coffee AF $1,100–2,500/ha", "source": "report p10 (narrative)"},
        {"label": "Net present value (NPV)", "baseline": 900, "alternative": 29300,
         "unit": "USD/ha", "change": "maize $900–3,000/ha vs coffee AF $2,750–29,300/ha", "source": "report p10"},
        {"label": "Carbon stock", "baseline": None, "alternative": None, "unit": "t C/ha",
         "change": "49–150 t C/ha (≈$865M over area)", "source": "report p10"},
    ],
}

TEEB_STUDIES["Agroforestry — shaded vs full-sun cocoa (Ghana, TEEB/ICRAF REDD+)"] = {
    "name": "Agroforestry — shaded vs full-sun cocoa (Ghana, TEEB/ICRAF REDD+)",
    "country": "Ghana", "region": "West Africa",
    "publisher": _AGF_PUB, "framework": "TEEBAgriFood / TEEB REDD+ (TEV of ecosystem services)",
    "teeb_published": True,
    "basis": "million USD per year (Δ ecosystem-service value vs baseline shaded-cocoa agroforestry)",
    "currency": "2013 US$ (PPP); landscape scale over the mapped agroforestry area",
    "year": 2015, "url": _AGF_URL,
    "source": "Agroforestry: an attractive REDD+ policy option? (UNEP TEEB / ICRAF / UNEP-WCMC, "
              "2015), cocoa-agroforestry case, Ghana — Table 3.",
    "summary": "Shaded cocoa agroforestry stores ~23.4 Mt C (≈$565M) but its provisioning ($2,300/"
               "ha/yr; NPV $600/ha) is *lower* than full-sun cocoa ($3,100/ha; NPV >$4,100/ha) or "
               "high-tech ($6,400/ha; NPV $14,000/ha). On the services this study monetises, "
               "**converting to full sun** is even net-positive (+$60.9M cocoa, +$42.3M water, only "
               "−$12.9M carbon) — an honest result that reflects what is *omitted*: biodiversity, "
               "water quality, pollination and all human/social capital, where shaded cocoa's "
               "advantages lie (see caveats).",
    "methodology": _AGF_METH,
    "scenarios": {
        "Shaded cocoa agroforestry retained (baseline = 0 reference)": {"items": []},
        "Convert to full sun (Scenario 1)": {"items": [
            _item("cocoa", "produced", "Cocoa production", 60.86, _AGF, "benefit", "Table 3, Convert-to-full-sun: cocoa +$60.86M/yr"),
            _item("carbon", "natural", "Carbon regulation", 12.9, _AGF, "cost", "Table 3, Convert-to-full-sun: carbon −$12.9M/yr"),
            _item("water", "natural", "Water yield", 42.3, _AGF, "benefit", "Table 3, Convert-to-full-sun: water yield +$42.3M/yr"),
        ]},
        "Convert to moderate shade (Scenario 2)": {"items": [
            _item("cocoa", "produced", "Cocoa production", 165.8, _AGF, "cost", "Table 3, Moderate-shade: cocoa −$165.8M/yr"),
            _item("timber", "produced", "Timber", 14.6, _AGF, "benefit", "Table 3, Moderate-shade: timber +$14.6M/yr"),
            _item("fruit", "produced", "Fruit-tree products", 70.2, _AGF, "benefit", "Table 3, Moderate-shade: fruit +$70.2M/yr"),
            _item("carbon", "natural", "Carbon regulation", 36.6, _AGF, "benefit", "Table 3, Moderate-shade: carbon +$36.6M/yr"),
            _item("water", "natural", "Water yield", 39.4, _AGF, "cost", "Table 3, Moderate-shade: water yield −$39.4M/yr"),
        ]},
    },
    "indicators": [
        {"label": "Provisioning value (shaded vs full sun vs high-tech)", "baseline": 2300, "alternative": 6400,
         "unit": "USD/ha/yr", "change": "shaded $2,300 · full sun $3,100 · high-tech $6,400", "source": "report p11"},
        {"label": "Net present value (NPV)", "baseline": 600, "alternative": 14000,
         "unit": "USD/ha", "change": "shaded $600 · full sun >$4,100 · high-tech $14,000", "source": "report p11"},
        {"label": "Carbon stock value", "baseline": None, "alternative": 565, "unit": "million USD",
         "change": "≈23.4 Mt C ≈ $565M over the area", "source": "report p11"},
    ],
}

TEEB_STUDIES["Agroforestry — Ngitili woodland vs maize (Tanzania, TEEB/ICRAF REDD+)"] = {
    "name": "Agroforestry — Ngitili woodland vs maize (Tanzania, TEEB/ICRAF REDD+)",
    "country": "Tanzania", "region": "East Africa",
    "publisher": _AGF_PUB, "framework": "TEEBAgriFood / TEEB REDD+ (TEV of ecosystem services)",
    "teeb_published": True,
    "basis": "million USD per year (Δ ecosystem-service value vs baseline Ngitili agroforestry)",
    "currency": "2013 US$ (PPP); landscape scale over the mapped Ngitili area",
    "year": 2015, "url": _AGF_URL,
    "source": "Agroforestry: an attractive REDD+ policy option? (UNEP TEEB / ICRAF / UNEP-WCMC, "
              "2015), Ngitili case, Tanzania — Table 4.",
    "summary": "The Ngitili (enclosed woodland) system delivers provisioning worth ~$1.6 bn over the "
               "area (mostly subsistence, not cash) plus ~34.7 Mt C (≈$837M/yr); NPV $5,000–16,000/"
               "ha vs $750–2,000/ha for maize. **Converting to maize** gains ~$274M maize but "
               "destroys ~$1,434M of provisioning (charcoal, NTFPs, wood fuel, timber) and ~$176M "
               "carbon — a ~$1.3 bn/yr net societal loss. Scenario 2 (restore canopy ≥20% from "
               "maize) shows the large gains from the reverse move. Human & social capital not monetised.",
    "methodology": _AGF_METH,
    "scenarios": {
        "Ngitili agroforestry retained (baseline = 0 reference)": {"items": []},
        "Convert to maize (Scenario 1)": {"items": [
            _item("maize", "produced", "Maize production", 273.8, _AGF, "benefit", "Table 4, Convert-to-maize: maize +$273.8M/yr"),
            _item("timber_poles", "produced", "Timber & poles", 148.1, _AGF, "cost", "Table 4, Convert-to-maize: timber & poles −$148.1M/yr"),
            _item("charcoal", "produced", "Charcoal", 463.9, _AGF, "cost", "Table 4, Convert-to-maize: charcoal −$463.9M/yr"),
            _item("wood_fuel", "produced", "Wood fuel", 102.8, _AGF, "cost", "Table 4, Convert-to-maize: wood fuel −$102.8M/yr"),
            _item("other_ntfp", "produced", "Other NTFP (honey, medicine, fodder, bushmeat)", 782.7, _AGF, "cost", "Table 4, Convert-to-maize: other NTFP −$782.7M/yr"),
            _item("grazing", "produced", "Grazing-land rentals", 63.19, _AGF, "benefit", "Table 4, Convert-to-maize: grazing rentals +$63.19M/yr"),
            _item("carbon", "natural", "Carbon regulation", 176, _AGF, "cost", "Table 4, Convert-to-maize: carbon −$176M/yr"),
            _item("water", "natural", "Water yield", 0.95, _AGF, "benefit", "Table 4, Convert-to-maize: water yield +$0.95M/yr"),
            _item("soil", "natural", "Soil erosion control", 0.031, _AGF, "benefit", "Table 4, Convert-to-maize: soil erosion +$0.031M/yr"),
        ]},
        "Restore canopy ≥20% from maize (Scenario 2)": {"items": [
            _item("maize", "produced", "Maize production", 424.3, _AGF, "cost", "Table 4, Scenario 2: maize −$424.3M/yr"),
            _item("timber_poles", "produced", "Timber & poles", 229.5, _AGF, "benefit", "Table 4, Scenario 2: timber & poles +$229.5M/yr"),
            _item("charcoal", "produced", "Charcoal", 718.9, _AGF, "benefit", "Table 4, Scenario 2: charcoal +$718.9M/yr"),
            _item("wood_fuel", "produced", "Wood fuel", 159.3, _AGF, "benefit", "Table 4, Scenario 2: wood fuel +$159.3M/yr"),
            _item("other_ntfp", "produced", "Other NTFP (honey, medicine, fodder, bushmeat)", 1212.7, _AGF, "benefit", "Table 4, Scenario 2: other NTFP +$1,212.7M/yr"),
            _item("grazing", "produced", "Grazing-land rentals", 97.9, _AGF, "cost", "Table 4, Scenario 2: grazing rentals −$97.9M/yr"),
            _item("carbon", "natural", "Carbon regulation", 1464, _AGF, "benefit", "Table 4, Scenario 2: carbon +$1,464M/yr"),
            _item("water", "natural", "Water yield", 0.95, _AGF, "cost", "Table 4, Scenario 2: water yield −$0.95M/yr"),
            _item("soil", "natural", "Soil erosion control", 0.009, _AGF, "benefit", "Table 4, Scenario 2: soil erosion +$0.009M/yr"),
        ]},
    },
    "indicators": [
        {"label": "Net present value (NPV)", "baseline": 750, "alternative": 16000, "unit": "USD/ha",
         "change": "maize $750–2,000/ha vs Ngitili $5,000–16,000/ha", "source": "report p12"},
        {"label": "Provisioning value (whole area)", "baseline": None, "alternative": 1600,
         "unit": "million USD", "change": "≈$1.6 bn (mostly subsistence, not cash)", "source": "report p12"},
        {"label": "Carbon stock value", "baseline": None, "alternative": 837, "unit": "million USD/yr",
         "change": "≈34.7 Mt C ≈ $837M/yr", "source": "report p12"},
    ],
}


# ===========================================================================
# INLAND FISHERIES — Columbia River salmon fishery (UNEP-FAO TEEB)
# Morton & Knowler (Simon Fraser U.) for FAO/UNEP TEEB, in "Increasing the visibility of
# fisheries and aquaculture's services" (FAO/UNEP). Table 45: net social benefit of four
# fishery ecosystem services under five development scenarios, US$ 2013/yr. teeb_published=True.
#
# MAPPING NOTE: the report uses Millennium-Assessment service categories, not the four capitals.
# We map commercial fishery -> produced; recreational + cultural/subsistence -> social;
# nutrient cycling -> natural. This mapping is an encoder choice (stated in caveats). All four
# services are positive net-social-benefit values, so all are benefits.
# ===========================================================================
_COL = "US$ 2013/yr (net social benefit)"
_COL_SRC = "Columbia River fishery case, Table 45 (Morton & Knowler; FAO/UNEP TEEB inland-fisheries study)."

def _col_items(commercial, recreational, cultural, nutrient):
    return [
        _item("commercial", "produced", "Commercial fishery (food production / income)", commercial, _COL, "benefit", _COL_SRC),
        _item("recreational", "social", "Recreational fishery", recreational, _COL, "benefit", _COL_SRC),
        _item("cultural", "social", "Cultural / subsistence fishery", cultural, _COL, "benefit", _COL_SRC),
        _item("nutrient", "natural", "Nutrient cycling", nutrient, _COL, "benefit", _COL_SRC),
    ]

TEEB_STUDIES["Columbia River salmon fishery — development scenarios (UNEP-FAO TEEB)"] = {
    "name": "Columbia River salmon fishery — development scenarios (UNEP-FAO TEEB)",
    "country": "United States", "region": "North America (Pacific Northwest)",
    "publisher": "FAO Marine & Inland Fisheries Branch with UNEP TEEB (case study: Morton & Knowler, Simon Fraser University)",
    "framework": "TEEB / Millennium Assessment ecosystem services (mapped to four capitals)",
    "teeb_published": True,
    "basis": "US$ 2013 per year (net social benefit of fishery ecosystem services)",
    "currency": "US$ 2013; whole Columbia River salmon fishery (Washington-focused)",
    "year": 2016, "url": _AGF_URL,
    "source": "The True Cost / visibility of inland fisheries (FAO/UNEP TEEB), Columbia River case — "
              "Table 45: net social benefit of four fishery ecosystem services across development scenarios.",
    "summary": "Values four salmon-fishery ecosystem services — commercial, recreational, cultural/"
               "subsistence fishing and nutrient cycling — under five river-management scenarios. "
               "Recreational fishing is the largest. Default compares the **Status quo ($29.2M/yr) "
               "with a Conservation priority (+10% flow regulation, $32.5M/yr)** → a **+$3.3M/yr** "
               "societal gain; a Hydropower-priority scenario instead loses $2.6M/yr. (The report "
               "notes the *hydropower* generation benefits themselves were not counted.)",
    "methodology": {
        "framework": "Net social benefit of selected fishery ecosystem services (Millennium Assessment "
                     "categories), compared across river-development scenarios.",
        "equations": [
            "Net societal value = Σ (net social benefit of each fishery ecosystem service)",
            "NPV of a scenario shift = perpetuity of the annual difference at a 10% discount rate",
            "Recreational value via Huppert et al. (2004) WTP; commercial at ex-vessel/retail prices",
        ],
        "coefficients": [
            {"name": "Discount rate", "value": "10% (NPV)", "source": "Table 45 note"},
            {"name": "Currency", "value": "US$ 2013", "source": "Table 45"},
        ],
        "data": "Columbia River salmonid fishery, primarily Washington State; four ecosystem services "
                "with sufficient data (commercial, recreational, cultural/subsistence, nutrient cycling).",
        "caveats": [
            "The report uses Millennium-Assessment service categories, NOT the four capitals; the "
            "mapping here (commercial→produced, recreational+cultural→social, nutrient→natural) is "
            "applied for display in the four-capital frame.",
            "Only four services had sufficient data; water quality, biodiversity and carbon were "
            "NOT valued, and the hydropower-generation benefits of the Hydropower-priority scenario "
            "were explicitly excluded — so scenario comparisons are partial.",
            "Nutrient cycling is the *net* (not gross) sea-to-land nutrient import, hence very small.",
        ],
    },
    "scenarios": {
        "Status quo": {"items": _col_items(6732487, 20958061, 1469256, 47659)},
        "Conservation priority (+10% flow regulation)": {"items": _col_items(8146900, 22772193, 1572854, 51784)},
        "Conservation priority (+20% flow regulation)": {"items": _col_items(8932685, 23780043, 1642466, 54076)},
        "Hydropower priority": {"items": _col_items(5770626, 19648901, 1137183, 44682)},
        "Pristine conditions": {"items": _col_items(12494249, 28272642, 1732817, 64292)},
    },
    "indicators": [
        {"label": "Conservation priority (+10%) vs status quo — NPV", "baseline": None, "alternative": 33362681,
         "unit": "US$ (NPV @10%)", "change": "+$33.4M NPV (+$3.34M/yr)", "source": "Table 45"},
        {"label": "Hydropower priority vs status quo — NPV", "baseline": None, "alternative": -26060711,
         "unit": "US$ (NPV @10%)", "change": "−$26.1M NPV (−$2.61M/yr)", "source": "Table 45"},
        {"label": "Pristine vs status quo — NPV", "baseline": None, "alternative": 133565370,
         "unit": "US$ (NPV @10%)", "change": "+$133.6M NPV (+$13.36M/yr)", "source": "Table 45"},
    ],
}


# ===========================================================================
# PALM OIL — true-cost decomposition (TEEBAgriFood; Raynaud et al. 2016)
# From the TEEBAgriFood Scientific & Economic Foundations Report (2018), Ch 8 Case 4, citing
# Raynaud et al. (2016) "Improving Business Decision Making: Valuing the Hidden Costs of
# Production in the Palm Oil Sector" (a TEEBAgriFood Program study). 11 leading producer
# countries, focus Indonesia; production + milling + refining only. teeb_published=True.
#
# The report gives natural-capital cost ($43bn/yr) and commodity value ($50bn/yr) on the SAME
# aggregate basis -> encoded as a market-vs-true-cost comparison. Human-capital cost is reported
# only per-tonne / per-employee (not aggregated), so it is shown as an indicator, not summed.
# ===========================================================================
_PO = "USD billion/yr (11 producer countries)"
_PO_SRC = ("TEEBAgriFood Scientific & Economic Foundations Report 2018, Ch 8 Case 4, citing "
           "Raynaud et al. 2016 (palm-oil hidden-cost study).")
TEEB_STUDIES["Palm oil — hidden natural-capital cost (TEEBAgriFood, Raynaud et al. 2016)"] = {
    "name": "Palm oil — hidden natural-capital cost (TEEBAgriFood, Raynaud et al. 2016)",
    "country": "Indonesia (+10 other producers)", "region": "Global (11 producer countries)",
    "publisher": "TEEBAgriFood Program (Raynaud et al. 2016); summarised in the TEEB Foundations Report 2018",
    "framework": "TEEBAgriFood Evaluation Framework (true-cost decomposition)",
    "teeb_published": True,
    "basis": "USD billion per year (11 leading producer countries; production + milling + refining)",
    "currency": "USD billion / year (aggregate over the 11 countries)",
    "year": 2016, "url": _AGF_URL,
    "source": "Improving Business Decision Making: Valuing the Hidden Costs of Production in the Palm "
              "Oil Sector (Raynaud et al. 2016, TEEBAgriFood) — via the Foundations Report 2018, Ch 8.",
    "summary": "Palm-oil production across the 11 leading producer countries is worth **$50 bn/yr** "
               "but carries a **$43 bn/yr natural-capital cost** (land degradation, biodiversity "
               "loss, air & water pollution) — i.e. hidden natural-capital costs nearly as large as "
               "the entire commodity value. Per tonne: **$790 natural-capital cost for crude palm "
               "oil**, $897 for palm kernel oil; plus a **$34/tonne human-capital cost** "
               "(underpayment + occupational health, $592/employee). Many ecosystem services and "
               "all social costs were not valued.",
    "methodology": {
        "framework": "TEEBAgriFood Framework; natural- and human-capital impacts of growing, milling "
                     "and refining palm oil, via avoided-cost and damage-cost methods.",
        "equations": [
            "Net = commodity value − natural-capital cost (the gap = the headline hidden natural cost)",
            "Natural-capital cost = Σ monetised damages (land degradation, biodiversity, air & water pollution)",
            "Human-capital cost = underpayment + occupational-health impacts (per employee / per tonne)",
        ],
        "coefficients": [
            {"name": "Natural-capital cost, crude palm oil", "value": "US$790 / tonne", "source": "Raynaud 2016 (Ch 8)"},
            {"name": "Natural-capital cost, palm kernel oil", "value": "US$897 / tonne", "source": "Raynaud 2016 (Ch 8)"},
            {"name": "Human-capital cost", "value": "US$592 / employee = $34/t (palm oil), $53/t (PKO)", "source": "Raynaud 2016 (Ch 8)"},
        ],
        "data": "11 leading palm-oil producer countries, focus Indonesia; production + milling + "
                "refining stages only (excludes transport, food processing, consumption).",
        "caveats": [
            "Human-capital cost is reported per tonne / per employee, NOT as an annual aggregate, so "
            "it is shown as an indicator and is NOT summed into the $bn/yr ledger.",
            "Excludes transport, processing and CONSUMPTION (e.g. health effects of palm-oil "
            "consumption in India) — and excludes many ecosystem services (soil-erosion control, "
            "biodiversity, water regulation) and ALL social capital.",
            "A framework-testing application; figures are reported from Raynaud et al. 2016, not "
            "re-derived here.",
        ],
    },
    "scenarios": {
        "Commodity value (market view)": {"items": [
            _item("value", "produced", "Palm-oil commodity value", 50, _PO, "benefit",
                  _PO_SRC + " Annual commodity value $50bn."),
        ]},
        "True-cost view (incl. natural capital)": {"items": [
            _item("value", "produced", "Palm-oil commodity value", 50, _PO, "benefit",
                  _PO_SRC + " Annual commodity value $50bn."),
            _item("nat_cost", "natural", "Natural-capital cost (land, biodiversity, air & water pollution)", 43, _PO, "cost",
                  _PO_SRC + " Natural-capital cost $43bn/yr."),
        ]},
    },
    "indicators": [
        {"label": "Natural-capital cost per tonne (crude palm oil / palm kernel oil)", "baseline": 790,
         "alternative": 897, "unit": "USD/tonne", "change": "$790/t CPO · $897/t PKO", "source": _PO_SRC},
        {"label": "Human-capital cost (underpayment + occupational health)", "baseline": None, "alternative": 34,
         "unit": "USD/tonne palm oil", "change": "$34/t palm oil · $53/t PKO · $592/employee", "source": _PO_SRC},
        {"label": "Natural-capital cost as share of commodity value", "baseline": None, "alternative": 86,
         "unit": "%", "change": "$43bn cost vs $50bn value ≈ 86%", "source": _PO_SRC},
    ],
}
