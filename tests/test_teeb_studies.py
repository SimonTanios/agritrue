"""
Unit tests for the TEEB localized-studies engine and registry.
Run:  python tests/test_teeb_studies.py
"""

import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from tca.teeb_studies import (
    TEEB_STUDIES, CAPITALS, scenario_totals, compare_scenarios, adjustable_items,
    materialize_study,
)
from tca import report


# A tiny synthetic study exercises the engine independently of the real data.
_TOY = {
    "name": "Toy", "country": "Nowhere", "region": "Test", "basis": "USD/ha/yr",
    "source": "(illustrative)", "summary": "toy",
    "scenarios": {
        "Base": {"items": [
            {"key": "rev", "capital": "produced", "label": "Revenue", "value": 1000,
             "unit": "USD/ha/yr", "kind": "benefit", "source": "x", "adjustable": True},
            {"key": "ghg", "capital": "natural", "label": "GHG cost", "value": 200,
             "unit": "USD/ha/yr", "kind": "cost", "source": "x", "adjustable": True},
        ]},
        "Alt": {"items": [
            {"key": "rev", "capital": "produced", "label": "Revenue", "value": 900,
             "unit": "USD/ha/yr", "kind": "benefit", "source": "x", "adjustable": True},
            {"key": "ghg", "capital": "natural", "label": "GHG cost", "value": 50,
             "unit": "USD/ha/yr", "kind": "cost", "source": "x", "adjustable": True},
        ]},
    },
}


def test_scenario_totals_signs():
    t = scenario_totals(_TOY["scenarios"]["Base"])
    assert t["by_capital"]["produced"] == 1000
    assert t["by_capital"]["natural"] == -200
    assert t["produced_net"] == 1000
    assert t["external_net"] == -200
    assert t["net_societal"] == 800


def test_overrides_apply():
    t = scenario_totals(_TOY["scenarios"]["Base"], {"rev": 1200})
    assert t["by_capital"]["produced"] == 1200
    assert t["net_societal"] == 1000  # 1200 - 200


def test_compare_scenarios_deltas():
    c = compare_scenarios(_TOY, "Base", "Alt")
    # Alt: produced 900, natural -50 -> net 850.  Base net 800.  delta +50.
    assert c["delta_net_societal"] == 50
    assert c["delta_private"] == -100        # 900 - 1000
    assert c["delta_external"] == 150        # -50 - (-200)
    assert c["delta_by_capital"]["natural"] == 150


def test_compare_unknown_scenario_raises():
    try:
        compare_scenarios(_TOY, "Base", "Ghost")
    except KeyError:
        return
    raise AssertionError("expected KeyError")


# --- Real registry invariants ---------------------------------------------
def _well_formed_scenarios(name, scenarios):
    for scen_name, scen in scenarios.items():
        keys = set()
        for it in scen["items"]:
            for k in ("key", "capital", "label", "value", "unit", "kind", "source"):
                assert k in it, f"{name}/{scen_name} item missing '{k}'"
            assert it["capital"] in CAPITALS
            assert it["kind"] in ("benefit", "cost")
            assert float(it["value"]) >= 0, f"{name}/{scen_name}/{it['key']} negative magnitude"
            assert it["key"] not in keys, f"{name}/{scen_name} duplicate key {it['key']}"
            keys.add(it["key"])


def test_registry_studies_well_formed():
    assert TEEB_STUDIES, "expected at least one published study loaded"
    for name, study in TEEB_STUDIES.items():
        for field in ("name", "country", "region", "basis", "source", "summary"):
            assert field in study, f"{name} missing '{field}'"
        # A study is one of: a static comparison (>=2 scenarios), a projection grid, or an
        # honest indicator-only study (no monetised ledger — must then carry indicators).
        if study.get("projection"):
            study = materialize_study(study)
        scenarios = study.get("scenarios") or {}
        if scenarios:
            assert len(scenarios) >= 2, f"{name} needs >=2 scenarios to compare"
            _well_formed_scenarios(name, scenarios)
        else:
            assert study.get("indicators"), f"{name} has no ledger AND no indicators"


def test_india_reproduces_published_income():
    ind = TEEB_STUDIES["India — APCNF natural farming vs conventional (Andhra Pradesh)"]
    c = compare_scenarios(ind, "Conventional (counterfactual avg)", "APCNF natural farming")
    # Table 18 (per ha, all farms): gross +$684 (+28.3%), net +$1,177 (+99.1%)
    ta, tb = c["totals_a"], c["totals_b"]
    assert ta["by_capital"]["produced"] == 1187.0      # baseline net income/ha
    assert tb["by_capital"]["produced"] == 2364.0      # APCNF net income/ha
    assert c["delta_private"] == 1177.0                # +$1,177/ha
    pct = (tb["by_capital"]["produced"] / ta["by_capital"]["produced"] - 1) * 100
    assert 99.0 <= pct <= 99.3                          # report: +99.1% (rounding)


def test_kenya_reproduces_published_true_cost():
    ke = TEEB_STUDIES["Kenya — true cost of farm food production (CGIAR NATURE+ / IFPRI)"]
    c = compare_scenarios(ke, "Market (direct) cost", "True cost (incl. externalities)")
    ta, tb = c["totals_a"], c["totals_b"]
    # Itemised report figures; their sums match the report's rounded headlines within ~$1.
    assert -ta["net_societal"] == 715.0                          # direct cost $715 (exact)
    assert abs(-tb["net_societal"] - 1026) <= 2                  # true cost ~$1,026
    assert abs(-c["delta_net_societal"] - 311) <= 2             # hidden cost ~$311
    assert abs(-c["delta_by_capital"]["social"] - 260) <= 2     # ~$260 social
    assert abs(-c["delta_by_capital"]["natural"] - 51) <= 1     # ~$51 environmental
    assert c["delta_by_capital"]["human"] == 0.0                 # health excluded by the study


def test_every_study_compares_and_pdfs():
    for name, study in TEEB_STUDIES.items():
        if study.get("projection"):
            study = materialize_study(study)
        scs = list(study.get("scenarios") or {})
        if len(scs) < 2:
            continue  # honest indicator-only study (Uttarakhand, Assam): nothing to compare
        cmp = compare_scenarios(study, scs[0], scs[1])
        assert set(cmp["delta_by_capital"]) == set(CAPITALS)
        pdf = report.teeb_study_pdf(study, cmp)
        assert bytes(pdf[:4]) == b"%PDF" and len(pdf) > 800


# --- TEEBAgriFood-India projection studies --------------------------------
_UP = "Uttar Pradesh — organic & agroforestry expansion (TEEBAgriFood India)"


def test_up_projection_reproduces_published_state_totals():
    # Default headline: Optimistic vs BaU, 2050, RCP 4.5, summed over the 5 study districts.
    study = materialize_study(TEEB_STUDIES[_UP])  # uses declared defaults
    assert study["_selection"] == {"year": 2050, "rcp": "4.5",
                                   "district": "State total (5 study districts)"}
    c = compare_scenarios(study, "Business-as-usual", "Optimistic policy")
    ta, tb = c["totals_a"], c["totals_b"]
    # Natural capital (Table 2) state totals @2050 RCP4.5: BAU 31.10, Optimistic 33.96 BUSD
    assert abs(ta["by_capital"]["natural"] - 31.10) <= 0.01
    assert abs(tb["by_capital"]["natural"] - 33.96) <= 0.01
    # Produced capital (Table 3): BAU 3.5891, Optimistic 4.1517 BUSD
    assert abs(ta["by_capital"]["produced"] - 3.59) <= 0.01
    assert abs(tb["by_capital"]["produced"] - 4.15) <= 0.01
    # Optimistic is a win-win: both private and external improve.
    assert c["delta_private"] > 0 and c["delta_external"] > 0
    assert abs(c["delta_external"] - 2.86) <= 0.02
    assert abs(c["delta_private"] - 0.56) <= 0.02


def test_up_single_district_slice():
    # Aligarh @2050 RCP4.5: natural BAU 4.11 / Opt 5.08; produced BAU 0.2048 / Opt 0.2307.
    study = materialize_study(TEEB_STUDIES[_UP], year=2050, rcp="4.5", district="Aligarh")
    c = compare_scenarios(study, "Business-as-usual", "Optimistic policy")
    assert abs(c["totals_a"]["by_capital"]["natural"] - 4.11) <= 0.001
    assert abs(c["totals_b"]["by_capital"]["natural"] - 5.08) <= 0.001
    # produced (items[1]) carries full 4-dp precision before by_capital rounds to 2 dp
    assert study["scenarios"]["Business-as-usual"]["items"][1]["value"] == 0.2048
    # State total must equal the sum of the five districts (no double counting).
    districts = TEEB_STUDIES[_UP]["districts_data"]
    per_district = sum(
        materialize_study(TEEB_STUDIES[_UP], year=2030, rcp="8.5", district=d)
        ["scenarios"]["Optimistic policy"]["items"][0]["value"]
        for d in districts)
    state = materialize_study(TEEB_STUDIES[_UP], year=2030, rcp="8.5",
                              district="State total (5 study districts)")
    assert abs(state["scenarios"]["Optimistic policy"]["items"][0]["value"] - per_district) <= 0.01


def test_up_climate_and_year_selectors_change_values():
    base = materialize_study(TEEB_STUDIES[_UP], year=2050, rcp="4.5", district="Mirzapur")
    hot = materialize_study(TEEB_STUDIES[_UP], year=2050, rcp="8.5", district="Mirzapur")
    # Mirzapur natural capital is strongly climate-sensitive (16.56 at RCP4.5 vs 12.61 at RCP8.5, BaU).
    bn = base["scenarios"]["Business-as-usual"]["items"][0]["value"]
    hn = hot["scenarios"]["Business-as-usual"]["items"][0]["value"]
    assert abs(bn - 16.56) <= 0.001 and abs(hn - 12.61) <= 0.001


def test_indicator_only_studies_have_no_ledger_but_carry_indicators():
    for name in ("Uttarakhand — organic & agroforestry scaling (TEEBAgriFood India)",
                 "Assam — organic & agroforestry projections (TEEBAgriFood India)"):
        study = TEEB_STUDIES[name]
        assert study.get("teeb_published") is True
        assert not study.get("scenarios"), f"{name} should NOT fabricate a ledger"
        assert len(study["indicators"]) >= 3, f"{name} should report indicators"


def test_india_state_studies_are_teeb_published():
    for name in (_UP,
                 "Uttarakhand — organic & agroforestry scaling (TEEBAgriFood India)",
                 "Assam — organic & agroforestry projections (TEEBAgriFood India)"):
        assert TEEB_STUDIES[name].get("teeb_published") is True


def test_agroforestry_reproduces_published_deltas():
    # Ethiopia coffee, Table 2, convert-to-maize: provisioning -38.4, carbon -435, water -34.9,
    # soil +15.9 -> external -454.0, net -492.4 (vs the zero agroforestry baseline).
    e = TEEB_STUDIES["Agroforestry — coffee vs maize (Ethiopia, TEEB/ICRAF REDD+)"]
    base = list(e["scenarios"])[0]
    c = compare_scenarios(e, base, "Convert to maize (Scenario 1)")
    assert abs(c["delta_private"] - (-38.4)) <= 0.01
    assert abs(c["delta_external"] - (-454.0)) <= 0.01
    assert abs(c["delta_net_societal"] - (-492.4)) <= 0.01
    # Ghana cocoa, Table 3, convert-to-full-sun is net-positive on the monetised services:
    # cocoa +60.86 (private), carbon -12.9 + water +42.3 = +29.4 (external), net +90.26.
    g = TEEB_STUDIES["Agroforestry — shaded vs full-sun cocoa (Ghana, TEEB/ICRAF REDD+)"]
    cg = compare_scenarios(g, list(g["scenarios"])[0], "Convert to full sun (Scenario 1)")
    assert abs(cg["delta_private"] - 60.86) <= 0.01
    assert abs(cg["delta_external"] - 29.4) <= 0.01
    # Tanzania Ngitili, Table 4, convert-to-maize: provisioning -1160.51, carbon -176.
    t = TEEB_STUDIES["Agroforestry — Ngitili woodland vs maize (Tanzania, TEEB/ICRAF REDD+)"]
    ct = compare_scenarios(t, list(t["scenarios"])[0], "Convert to maize (Scenario 1)")
    assert abs(ct["delta_private"] - (-1160.51)) <= 0.05   # report rounds the subtotal to -1160.1
    assert abs(ct["delta_by_capital"]["natural"] - (-175.019)) <= 0.05  # -176 + 0.95 + 0.031


def test_columbia_reproduces_table45():
    col = TEEB_STUDIES["Columbia River salmon fishery — development scenarios (UNEP-FAO TEEB)"]
    c = compare_scenarios(col, "Status quo", "Conservation priority (+10% flow regulation)")
    assert c["totals_a"]["net_societal"] == 29207463          # status-quo sub-total
    assert c["totals_b"]["net_societal"] == 32543731          # conservation +10% sub-total
    assert c["delta_net_societal"] == 3336268                 # report's +US$3,336,268/yr
    # commercial -> produced (private); recreational+cultural+nutrient -> external
    assert c["delta_private"] == 1414413                      # 8,146,900 - 6,732,487
    ch = compare_scenarios(col, "Status quo", "Hydropower priority")
    assert ch["delta_net_societal"] == -2606071               # report's -US$2,606,071/yr


def test_palm_oil_reproduces_hidden_cost():
    po = TEEB_STUDIES["Palm oil — hidden natural-capital cost (TEEBAgriFood, Raynaud et al. 2016)"]
    c = compare_scenarios(po, "Commodity value (market view)", "True-cost view (incl. natural capital)")
    assert c["totals_a"]["net_societal"] == 50                # commodity value $50bn
    assert c["totals_b"]["net_societal"] == 7                 # $50bn value - $43bn natural cost
    assert c["delta_net_societal"] == -43                     # $43bn/yr hidden natural-capital cost
    assert c["delta_by_capital"]["natural"] == -43


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} TEEB-study tests passed.")


if __name__ == "__main__":
    _run_all()
