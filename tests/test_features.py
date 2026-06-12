"""
Unit tests for the diet comparator, PDF report builder, and analytics helpers.
Run:  python tests/test_features.py     (pure-stdlib assertions + fpdf2)
"""

import os
import sys

sys.path.insert(0, os.path.normpath(os.path.join(os.path.dirname(__file__), "..")))

from tca.diets import DIET_PATTERNS, diet_hidden_cost, compare_diets
from tca.coefficients import COMMODITY_FACTORS
from tca import report
from tca import analytics


# --- Diets -----------------------------------------------------------------
def test_diet_patterns_reference_valid_commodities():
    for name, pattern in DIET_PATTERNS.items():
        for commodity in pattern:
            assert commodity in COMMODITY_FACTORS, f"{name} -> unknown commodity {commodity}"


def test_diet_hidden_cost_structure():
    r = diet_hidden_cost(DIET_PATTERNS["High-income Western"])
    assert r["total_hidden_cost_usd_yr"] > 0
    assert set(r["components"]) >= {"climate", "eutrophication", "water", "land"}
    assert r["footprint"]["ghg_kg"] > 0
    # foods sorted descending by cost
    costs = [f["hidden_cost_usd_yr"] for f in r["foods"]]
    assert costs == sorted(costs, reverse=True)


def test_western_diet_costlier_than_eatlancet():
    cmp = compare_diets("High-income Western", "EAT-Lancet planetary health")
    assert cmp["delta_usd_yr"] > 0          # western diet has higher hidden cost
    assert cmp["ghg_delta_kg_yr"] > 0       # and higher GHG footprint


def test_compare_diets_unknown_raises():
    try:
        compare_diets("Mars Colony Diet")
    except KeyError:
        return
    raise AssertionError("expected KeyError")


# --- PDF reports -----------------------------------------------------------
def _is_pdf(b: bytes) -> bool:
    return isinstance(b, (bytes, bytearray)) and bytes(b[:4]) == b"%PDF"


def test_true_price_pdf_bytes():
    from tca import true_price
    pdf = report.true_price_pdf(true_price("Beef (beef herd)", 1.0))
    assert _is_pdf(pdf) and len(pdf) > 800


def test_diet_pdf_bytes():
    pdf = report.diet_pdf(compare_diets("East Asian"))
    assert _is_pdf(pdf) and len(pdf) > 800


def test_national_pdf_bytes():
    from tca.data_pipeline import load_national_dataset
    from tca.coefficients import SOFA_2024_GLOBAL
    row = load_national_dataset()[0]
    pdf = report.national_pdf(row, SOFA_2024_GLOBAL)
    assert _is_pdf(pdf) and len(pdf) > 800


# --- Analytics -------------------------------------------------------------
def test_anonymise_ip_stable_and_short():
    a = analytics.anonymise_ip("203.0.113.5")
    b = analytics.anonymise_ip("203.0.113.5")
    assert a == b and len(a) == 10
    assert analytics.anonymise_ip("198.51.100.1") != a


def test_private_ip_not_geolocated():
    for ip in ("127.0.0.1", "192.168.1.10", "10.0.0.4", "::1", "unknown"):
        geo = analytics.geolocate(ip)
        assert geo["lat"] is None  # never makes a network call for private/invalid IPs


def test_summarise_aggregates():
    events = [
        {"event": "session_start", "session": "s1", "visitor": "v1", "geo": {"country": "Kenya"}},
        {"event": "page_view", "session": "s1", "visitor": "v1", "geo": {"country": "Kenya"},
         "detail": {"view": "Dashboard"}},
        {"event": "page_view", "session": "s2", "visitor": "v2", "geo": {"country": "Italy"},
         "detail": {"view": "Dashboard"}},
    ]
    s = analytics.summarise(events)
    assert s["sessions"] == 2
    assert s["unique_visitors"] == 2
    assert s["by_view"]["Dashboard"] == 2
    assert set(s["countries"]) == {"Kenya", "Italy"}


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn in fns:
        fn()
        print(f"  PASS  {fn.__name__}")
    print(f"\n{len(fns)}/{len(fns)} feature tests passed.")


if __name__ == "__main__":
    _run_all()
