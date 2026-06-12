"""
diets.py
========
Diet-pattern true-cost comparison for AgriTrue.

Compares the hidden (externalised) cost of typical national diet archetypes against the
EAT-Lancet "planetary health diet" reference, reusing the same audited true_price engine.

Diet patterns are expressed as grams/person/day of representative commodities and are
ILLUSTRATIVE archetypes loosely based on FAO Food Balance Sheet consumption patterns and
the EAT-Lancet Commission (2019) reference intakes — clearly flagged as such in the UI.

References
----------
* Willett et al. (2019). "Food in the Anthropocene: the EAT-Lancet Commission on healthy
  diets from sustainable food systems." The Lancet 393(10170): 447-492.
* FAO Food Balance Sheets (consumption patterns by region).
"""

from __future__ import annotations

from typing import Optional

from .engine import true_price
from .coefficients import COMMODITY_FACTORS

# Grams/person/day of representative commodities (keys must exist in COMMODITY_FACTORS).
DIET_PATTERNS: dict[str, dict[str, float]] = {
    "EAT-Lancet planetary health": {
        "Rice": 100, "Wheat & Rye": 100, "Maize": 32,
        "Potatoes": 50,
        "Tomatoes": 100, "Brassicas": 100, "Root Vegetables": 100,
        "Apples": 100, "Bananas": 100,
        "Milk": 250,
        "Beef (beef herd)": 7, "Pig Meat": 7,
        "Poultry Meat": 29, "Eggs": 13, "Farmed Fish": 28,
        "Peas": 25, "Other Pulses": 50, "Nuts": 50,
        "Olive Oil": 24, "Soybean Oil": 16, "Cane Sugar": 31,
    },
    "High-income Western": {
        "Wheat & Rye": 200, "Maize": 30, "Potatoes": 150,
        "Beef (beef herd)": 70, "Pig Meat": 80, "Poultry Meat": 70,
        "Cheese": 50, "Milk": 350, "Eggs": 30, "Farmed Fish": 40,
        "Tomatoes": 80, "Brassicas": 60, "Root Vegetables": 60,
        "Apples": 90, "Citrus Fruit": 70, "Berries & Grapes": 40,
        "Cane Sugar": 110, "Soybean Oil": 50, "Palm Oil": 20,
    },
    "South Asian": {
        "Rice": 200, "Wheat & Rye": 180, "Potatoes": 80,
        "Other Pulses": 60, "Peas": 20, "Milk": 200,
        "Poultry Meat": 20, "Beef (dairy herd)": 10,
        "Tomatoes": 60, "Brassicas": 50, "Root Vegetables": 80,
        "Bananas": 60, "Citrus Fruit": 40,
        "Cane Sugar": 60, "Palm Oil": 30, "Soybean Oil": 20,
    },
    "Sub-Saharan African": {
        "Maize": 250, "Rice": 60, "Wheat & Rye": 40,
        "Root Vegetables": 200, "Potatoes": 50, "Other Pulses": 50,
        "Poultry Meat": 15, "Beef (beef herd)": 15, "Farmed Fish": 20,
        "Bananas": 100, "Tomatoes": 40, "Brassicas": 40,
        "Palm Oil": 25, "Cane Sugar": 30,
    },
    "East Asian": {
        "Rice": 280, "Wheat & Rye": 80,
        "Pig Meat": 90, "Poultry Meat": 40,
        "Farmed Fish": 60, "Farmed Prawns": 10, "Eggs": 30,
        "Brassicas": 120, "Root Vegetables": 80, "Tomatoes": 60,
        "Tofu (Soybeans)": 40, "Apples": 80, "Citrus Fruit": 50,
        "Soybean Oil": 35, "Cane Sugar": 40,
    },
}

DAYS_PER_YEAR = 365.0


def diet_hidden_cost(
    pattern: dict[str, float],
    coeffs: Optional[dict] = None,
    water_stress: float = 1.0,
    include_health: bool = False,
) -> dict:
    """
    Annual per-person hidden cost + physical footprint of a diet pattern.

    Parameters
    ----------
    pattern : dict   {commodity: grams_per_day}

    Returns
    -------
    dict with: total_hidden_cost_usd_yr, component totals, per-food rows, and the
    physical footprint (kg CO2e, m3 water, m2*yr land) for the whole year.
    """
    components = {"climate": 0.0, "eutrophication": 0.0, "water": 0.0, "land": 0.0}
    if include_health:
        components["health"] = 0.0
    foods = []
    foot = {"ghg_kg": 0.0, "water_m3": 0.0, "land_m2yr": 0.0, "mass_kg": 0.0}

    for commodity, grams_day in pattern.items():
        kg_year = grams_day * DAYS_PER_YEAR / 1000.0
        tp = true_price(commodity, kg_year, coeffs, water_stress, include_health)
        for k, v in tp["components"].items():
            components[k] += v["central"]
        foods.append({
            "commodity": commodity,
            "kg_per_year": round(kg_year, 1),
            "hidden_cost_usd_yr": round(tp["hidden_cost"]["central"], 2),
        })
        f = COMMODITY_FACTORS[commodity]
        foot["ghg_kg"] += f["ghg"] * kg_year
        foot["water_m3"] += f["water"] * kg_year / 1000.0
        foot["land_m2yr"] += f["land"] * kg_year
        foot["mass_kg"] += kg_year

    total = sum(components.values())
    foods.sort(key=lambda r: r["hidden_cost_usd_yr"], reverse=True)
    return {
        "total_hidden_cost_usd_yr": round(total, 2),
        "components": {k: round(v, 2) for k, v in components.items()},
        "foods": foods,
        "footprint": {k: round(v, 1) for k, v in foot.items()},
    }


def compare_diets(
    diet_a: str,
    diet_b: str = "EAT-Lancet planetary health",
    coeffs: Optional[dict] = None,
    water_stress: float = 1.0,
    include_health: bool = False,
) -> dict:
    """Compare two named diet patterns; returns both results plus the delta (A - B)."""
    for name in (diet_a, diet_b):
        if name not in DIET_PATTERNS:
            raise KeyError(f"Unknown diet '{name}'. Options: {sorted(DIET_PATTERNS)}")
    ra = diet_hidden_cost(DIET_PATTERNS[diet_a], coeffs, water_stress, include_health)
    rb = diet_hidden_cost(DIET_PATTERNS[diet_b], coeffs, water_stress, include_health)
    delta = ra["total_hidden_cost_usd_yr"] - rb["total_hidden_cost_usd_yr"]
    pct = (delta / rb["total_hidden_cost_usd_yr"] * 100.0) if rb["total_hidden_cost_usd_yr"] else 0.0
    return {
        "diet_a": diet_a, "result_a": ra,
        "diet_b": diet_b, "result_b": rb,
        "delta_usd_yr": round(delta, 2),
        "delta_pct": round(pct, 1),
        "ghg_delta_kg_yr": round(ra["footprint"]["ghg_kg"] - rb["footprint"]["ghg_kg"], 1),
    }
