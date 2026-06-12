"""
Unit tests for the AgriTrue TCA engine.  Run:  python -m pytest -q   (or)  python tests/test_engine.py
Pure-stdlib assertions so they run without pytest installed.
"""

import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from tca.engine import true_price, rank_commodities, national_breakdown, compare_practices
from tca.coefficients import COMMODITY_FACTORS, SOFA_2024_GLOBAL


def test_true_price_basic_structure():
    r = true_price("Beef (beef herd)", 1.0)
    assert r["commodity"] == "Beef (beef herd)"
    assert set(r["components"]) == {"climate", "eutrophication", "water", "land"}
    # central must sit within the low/high band
    hc = r["hidden_cost"]
    assert hc["low"] <= hc["central"] <= hc["high"], hc
    assert r["true_price"] > r["market_price"]


def test_beef_costlier_than_peas():
    beef = true_price("Beef (beef herd)")["hidden_cost"]["central"]
    peas = true_price("Peas")["hidden_cost"]["central"]
    assert beef > peas * 20, (beef, peas)  # beef hidden cost is enormously larger


def test_mass_scales_linearly():
    one = true_price("Rice", 1.0)["hidden_cost"]["central"]
    ten = true_price("Rice", 10.0)["hidden_cost"]["central"]
    assert abs(ten - 10 * one) < 1e-6


def test_coeff_override_changes_climate_cost():
    low = true_price("Beef (beef herd)", coeffs={"social_cost_carbon": 50})
    high = true_price("Beef (beef herd)", coeffs={"social_cost_carbon": 300})
    assert high["components"]["climate"]["central"] > low["components"]["climate"]["central"] * 5


def test_health_surcharge_optional():
    base = true_price("Beef (beef herd)", include_health=False)
    with_h = true_price("Beef (beef herd)", include_health=True)
    assert "health" not in base["components"]
    assert "health" in with_h["components"]
    assert with_h["hidden_cost"]["central"] > base["hidden_cost"]["central"]


def test_rank_is_sorted_desc():
    rows = rank_commodities()
    costs = [r["hidden_cost_per_kg"] for r in rows]
    assert costs == sorted(costs, reverse=True)
    assert rows[0]["category"] in ("Meat", "Other")  # beef or chocolate/coffee on top


def test_unknown_commodity_raises():
    try:
        true_price("Unobtanium")
    except KeyError:
        return
    raise AssertionError("expected KeyError for unknown commodity")


def test_national_breakdown_shares_sum_to_one():
    nb = national_breakdown(1000, 0.10, 0.7, 0.21, 0.09)
    s = nb["health_share"] + nb["environmental_share"] + nb["social_share"]
    assert abs(s - 1.0) < 1e-6
    assert abs(nb["total_busd"] - 100.0) < 1e-6
    parts = nb["health_busd"] + nb["environmental_busd"] + nb["social_busd"]
    assert abs(parts - nb["total_busd"]) < 0.05


def test_national_breakdown_renormalises_bad_shares():
    # shares that don't sum to 1 must be re-normalised, not trusted blindly
    nb = national_breakdown(1000, 0.10, 7, 2.1, 0.9)
    s = nb["health_share"] + nb["environmental_share"] + nb["social_share"]
    assert abs(s - 1.0) < 1e-6


def test_compare_practices_organic_sequesters_carbon():
    r = compare_practices(
        practice="Organic", area_ha=100, baseline_yield_t_ha=3.0,
        crop_price_usd_t=300, baseline_n_cost_usd_ha=120,
    )
    assert r["natural_capital"]["co2_sequestered_t"] > 0
    assert r["natural_capital"]["carbon_value_usd"] > 0
    # organic dips yield but should save inputs
    assert r["produced_capital"]["input_savings_usd"] > 0


def test_compare_practices_headline_is_consistent():
    r = compare_practices("Agroforestry", 50, 2.5, 250, 100)
    expect = (r["produced_capital"]["net_income_change_usd"]
              + r["natural_capital"]["net_natural_value_usd"])
    assert abs(r["headline_societal_value_usd"] - expect) < 0.5


def test_global_anchor_shares_sum_to_one():
    g = SOFA_2024_GLOBAL
    assert abs(g["health_share"] + g["environmental_share"] + g["social_share"] - 1.0) < 1e-9


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  PASS  {fn.__name__}")
    print(f"\n{passed}/{len(fns)} tests passed.")


if __name__ == "__main__":
    _run_all()
