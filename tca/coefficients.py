"""
coefficients.py
===============
Transparent, fully-sourced coefficients for the AgriTrue True Cost Accounting engine.

Design principle (from FAO SOFA 2024): show ranges and assumptions, never false
precision. Every number here carries a citation and is overridable at runtime via the
dashboard, so the model is auditable rather than a black box.

Sources
-------
* Poore, J. & Nemecek, T. (2018). "Reducing food's environmental impacts through
  producers and consumers." Science 360(6392): 987-992.  -> per-kg LCA medians.
* Rennert et al. (2022). "Comprehensive evidence implies a higher social cost of CO2."
  Nature 610: 687-692.  -> social cost of carbon central estimate ~USD 185 / t CO2e.
* FAO (2024). The State of Food and Agriculture 2024 (SOFA): ~USD 12 trillion hidden
  costs/yr, ~10% of global GDP; ~70% health, remainder environmental + social.
* van Grinsven et al. (2013). Environ. Sci. Technol.  -> reactive-N damage cost range.
* Seufert et al. (2012) Nature; de Ponti et al. (2012); Gattinger et al. (2012) PNAS;
  Tuck et al. (2014) J. Appl. Ecol.  -> organic vs conventional meta-analysis deltas.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# 1. MONETIZATION COEFFICIENTS  (the "valuation layer" — all user-overridable)
# ---------------------------------------------------------------------------
# Each entry: (default value, low, high, unit, citation). Low/high define the
# uncertainty band that the dashboard renders instead of a single false-precise number.
DEFAULT_COEFFICIENTS = {
    "social_cost_carbon": {
        "value": 185.0, "low": 50.0, "high": 300.0,
        "unit": "USD / t CO2e",
        "source": "Rennert et al. 2022, Nature (central 185; IWG range 50-300)",
    },
    "eutrophication": {
        "value": 3.1, "low": 1.0, "high": 8.0,
        "unit": "USD / kg PO4e",
        "source": "van Grinsven et al. 2013 (reactive-N damage, converted to PO4e)",
    },
    "water_scarcity": {
        "value": 0.90, "low": 0.10, "high": 2.50,
        "unit": "USD / m3 (scarcity-weighted)",
        "source": "Pfister et al. 2009 water stress + AWARE-style shadow pricing",
    },
    "land_use": {
        "value": 0.09, "low": 0.02, "high": 0.25,
        "unit": "USD / m2 / yr",
        "source": "TEEB biodiversity/ecosystem-service opportunity cost (illustrative)",
    },
}

# ---------------------------------------------------------------------------
# 2. COMMODITY LCA FACTORS  (per kg of product, global medians)
# ---------------------------------------------------------------------------
# Keys: ghg = kg CO2e/kg ; land = m2*yr/kg ; water = L/kg ; eutroph = g PO4e/kg
# ref_price = indicative global retail price USD/kg (for the true-price ratio) ;
# health = dietary-risk class used by the optional health module.
# Values are Poore & Nemecek (2018) supplementary medians.
COMMODITY_FACTORS = {
    # --- Animal-sourced -----------------------------------------------------
    "Beef (beef herd)":   {"cat": "Meat",   "ghg": 99.5, "land": 326.0, "water": 1451, "eutroph": 365, "ref_price": 12.0, "health": "red_meat"},
    "Beef (dairy herd)":  {"cat": "Meat",   "ghg": 33.3, "land": 43.2,  "water": 2714, "eutroph": 365, "ref_price": 10.5, "health": "red_meat"},
    "Lamb & Mutton":      {"cat": "Meat",   "ghg": 39.7, "land": 369.0, "water": 1803, "eutroph": 97,  "ref_price": 14.0, "health": "red_meat"},
    "Pig Meat":           {"cat": "Meat",   "ghg": 12.3, "land": 17.4,  "water": 1796, "eutroph": 76,  "ref_price": 6.5,  "health": "red_meat"},
    "Poultry Meat":       {"cat": "Meat",   "ghg": 9.9,  "land": 12.2,  "water": 660,  "eutroph": 49,  "ref_price": 4.0,  "health": "neutral"},
    "Cheese":             {"cat": "Dairy",  "ghg": 23.9, "land": 88.0,  "water": 5605, "eutroph": 98,  "ref_price": 11.0, "health": "neutral"},
    "Eggs":               {"cat": "Dairy",  "ghg": 4.7,  "land": 6.3,   "water": 578,  "eutroph": 22,  "ref_price": 3.5,  "health": "beneficial"},
    "Milk":               {"cat": "Dairy",  "ghg": 3.2,  "land": 9.0,   "water": 628,  "eutroph": 11,  "ref_price": 1.2,  "health": "beneficial"},
    "Farmed Fish":        {"cat": "Seafood","ghg": 13.6, "land": 9.0,   "water": 3691, "eutroph": 236, "ref_price": 9.0,  "health": "beneficial"},
    "Farmed Prawns":      {"cat": "Seafood","ghg": 26.9, "land": 2.0,   "water": 3515, "eutroph": 227, "ref_price": 18.0, "health": "neutral"},
    # --- Plant-sourced ------------------------------------------------------
    "Rice":               {"cat": "Grains", "ghg": 4.5,  "land": 2.8,   "water": 2248, "eutroph": 35,  "ref_price": 1.0,  "health": "neutral"},
    "Wheat & Rye":        {"cat": "Grains", "ghg": 1.6,  "land": 3.9,   "water": 649,  "eutroph": 6,   "ref_price": 0.8,  "health": "beneficial"},
    "Maize":              {"cat": "Grains", "ghg": 1.1,  "land": 2.9,   "water": 216,  "eutroph": 3,   "ref_price": 0.6,  "health": "neutral"},
    "Oats":               {"cat": "Grains", "ghg": 2.5,  "land": 7.6,   "water": 283,  "eutroph": 9,   "ref_price": 1.5,  "health": "beneficial"},
    "Tofu (Soybeans)":    {"cat": "Pulses", "ghg": 3.2,  "land": 2.2,   "water": 149,  "eutroph": 7,   "ref_price": 3.0,  "health": "beneficial"},
    "Peas":               {"cat": "Pulses", "ghg": 0.9,  "land": 7.5,   "water": 397,  "eutroph": 4,   "ref_price": 2.5,  "health": "beneficial"},
    "Other Pulses":       {"cat": "Pulses", "ghg": 1.8,  "land": 16.0,  "water": 1180, "eutroph": 12,  "ref_price": 2.2,  "health": "beneficial"},
    "Nuts":               {"cat": "Pulses", "ghg": 0.4,  "land": 13.0,  "water": 4134, "eutroph": 7,   "ref_price": 12.0, "health": "beneficial"},
    "Tomatoes":           {"cat": "Veg",    "ghg": 1.4,  "land": 0.8,   "water": 370,  "eutroph": 5,   "ref_price": 2.5,  "health": "beneficial"},
    "Brassicas":          {"cat": "Veg",    "ghg": 0.5,  "land": 0.8,   "water": 76,   "eutroph": 3,   "ref_price": 1.8,  "health": "beneficial"},
    "Root Vegetables":    {"cat": "Veg",    "ghg": 0.4,  "land": 1.7,   "water": 28,   "eutroph": 2,   "ref_price": 1.0,  "health": "beneficial"},
    "Potatoes":           {"cat": "Veg",    "ghg": 0.5,  "land": 0.9,   "water": 59,   "eutroph": 2,   "ref_price": 0.9,  "health": "neutral"},
    "Bananas":            {"cat": "Fruit",  "ghg": 0.9,  "land": 1.9,   "water": 115,  "eutroph": 3,   "ref_price": 1.2,  "health": "beneficial"},
    "Apples":             {"cat": "Fruit",  "ghg": 0.4,  "land": 0.6,   "water": 180,  "eutroph": 2,   "ref_price": 2.0,  "health": "beneficial"},
    "Citrus Fruit":       {"cat": "Fruit",  "ghg": 0.4,  "land": 0.9,   "water": 83,   "eutroph": 2,   "ref_price": 1.8,  "health": "beneficial"},
    "Berries & Grapes":   {"cat": "Fruit",  "ghg": 1.5,  "land": 2.3,   "water": 420,  "eutroph": 5,   "ref_price": 6.0,  "health": "beneficial"},
    "Coffee":             {"cat": "Other",  "ghg": 28.5, "land": 21.0,  "water": 1969, "eutroph": 49,  "ref_price": 25.0, "health": "neutral"},
    "Dark Chocolate":     {"cat": "Other",  "ghg": 46.7, "land": 247.0, "water": 3400, "eutroph": 105, "ref_price": 20.0, "health": "neutral"},
    "Cane Sugar":         {"cat": "Other",  "ghg": 3.2,  "land": 2.0,   "water": 197,  "eutroph": 10,  "ref_price": 1.0,  "health": "sugar"},
    "Palm Oil":           {"cat": "Oils",   "ghg": 7.6,  "land": 6.0,   "water": 1098, "eutroph": 18,  "ref_price": 1.5,  "health": "neutral"},
    "Soybean Oil":        {"cat": "Oils",   "ghg": 6.3,  "land": 31.0,  "water": 1287, "eutroph": 32,  "ref_price": 1.8,  "health": "neutral"},
    "Olive Oil":          {"cat": "Oils",   "ghg": 5.4,  "land": 27.0,  "water": 5658, "eutroph": 38,  "ref_price": 9.0,  "health": "beneficial"},
}

# ---------------------------------------------------------------------------
# 3. OPTIONAL DIETARY-HEALTH SURCHARGE
# ---------------------------------------------------------------------------
# SOFA 2024 attributes ~70% of hidden costs to dietary patterns (not single foods),
# so per-commodity health costs are inherently approximate. We expose a transparent,
# OFF-by-default surcharge (USD/kg) for risk-associated food classes, derived from
# GBD 2019 diet-risk attributable burden. Clearly flagged as illustrative.
HEALTH_RISK_SURCHARGE = {
    "red_meat":   {"value": 2.8, "source": "GBD 2019 diet-risk (red/processed meat) — illustrative"},
    "sugar":      {"value": 1.5, "source": "GBD 2019 diet-risk (sugar-sweetened) — illustrative"},
    "neutral":    {"value": 0.0, "source": "no net dietary-risk surcharge applied"},
    "beneficial": {"value": 0.0, "source": "protective foods — surcharge floored at 0"},
}

# ---------------------------------------------------------------------------
# 4. AGRIFOOD-SYSTEM TYPOLOGY  (SOFA 2024 six-category framework)
# ---------------------------------------------------------------------------
# typical_pct_gdp + composition shares are calibrated to SOFA 2024 aggregate findings:
# industrial systems are health-cost dominated; protracted-crisis & traditional systems
# carry the largest SOCIAL burden (undernourishment, poverty) as a share of GDP.
AGRIFOOD_SYSTEM_TYPES = {
    "Protracted crisis": {"health": 0.20, "environmental": 0.18, "social": 0.62, "note": "Largest social burden"},
    "Traditional":       {"health": 0.30, "environmental": 0.22, "social": 0.48, "note": "High undernourishment cost"},
    "Expanding":         {"health": 0.45, "environmental": 0.33, "social": 0.22, "note": "Rising NCDs + land conversion"},
    "Diversifying":      {"health": 0.58, "environmental": 0.30, "social": 0.12, "note": "Transition stage"},
    "Formalizing":       {"health": 0.68, "environmental": 0.26, "social": 0.06, "note": "Health-dominated"},
    "Industrial":        {"health": 0.78, "environmental": 0.19, "social": 0.03, "note": "Health-dominated, low social share"},
}

# Global SOFA 2024 anchors (used for calibration & the headline KPIs).
SOFA_2024_GLOBAL = {
    "total_hidden_cost_trillion_usd": 12.0,
    "share_of_global_gdp": 0.10,
    "health_share": 0.70,
    "environmental_share": 0.21,
    "social_share": 0.09,
    "countries_covered": 156,
    "currency_basis": "2020 PPP dollars",
    "source": "FAO, The State of Food and Agriculture 2024",
}
