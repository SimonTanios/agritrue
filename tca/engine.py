"""
engine.py
=========
The AgriTrue True Cost Accounting (TCA) calculation engine.

Implements the TEEBAgriFood / SOFA four-capitals logic in three reusable functions,
each returning a transparent, itemised breakdown (never a single opaque number):

    1. true_price()          -> hidden environmental (+optional health) cost of a food item
    2. national_breakdown()  -> a country's hidden cost split across the four capitals
    3. compare_practices()   -> change in capital flows when switching farm practice
                                (conventional -> organic / agroforestry)  [Phase-3 relevant]

The engine is pure-Python (stdlib only) so it can be unit-tested and embedded anywhere;
the Streamlit dashboard and the FAOSTAT pipeline import from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .coefficients import (
    COMMODITY_FACTORS,
    DEFAULT_COEFFICIENTS,
    HEALTH_RISK_SURCHARGE,
    AGRIFOOD_SYSTEM_TYPES,
)


# ===========================================================================
# Helpers
# ===========================================================================
def _coeff(coeffs: Optional[dict], key: str) -> float:
    """Resolve a monetization coefficient, falling back to the documented default."""
    if coeffs and key in coeffs:
        return float(coeffs[key])
    return float(DEFAULT_COEFFICIENTS[key]["value"])


@dataclass
class CostBand:
    """A central estimate with a low/high uncertainty band (SOFA design principle)."""
    central: float
    low: float
    high: float

    def scaled(self, factor: float) -> "CostBand":
        return CostBand(self.central * factor, self.low * factor, self.high * factor)

    def __add__(self, other: "CostBand") -> "CostBand":
        return CostBand(self.central + other.central, self.low + other.low, self.high + other.high)

    def as_dict(self) -> dict:
        return {"central": round(self.central, 4),
                "low": round(self.low, 4),
                "high": round(self.high, 4)}


# ===========================================================================
# 1. TRUE PRICE OF A FOOD ITEM
# ===========================================================================
def true_price(
    commodity: str,
    mass_kg: float = 1.0,
    coeffs: Optional[dict] = None,
    water_stress: float = 1.0,
    include_health: bool = False,
) -> dict:
    """
    Compute the hidden (externalised) cost of producing `mass_kg` of `commodity`.

    Parameters
    ----------
    commodity : str        key in COMMODITY_FACTORS
    mass_kg   : float       quantity in kilograms
    coeffs    : dict|None   optional overrides for monetization coefficients
                            (social_cost_carbon, eutrophication, water_scarcity, land_use)
    water_stress : float    country water-stress multiplier (1.0 = global average)
    include_health : bool   apply the optional, illustrative dietary-health surcharge

    Returns
    -------
    dict with per-component CostBands, the total hidden cost, the reference market
    price, and the "true price" (market + hidden) plus the hidden:market ratio.
    """
    if commodity not in COMMODITY_FACTORS:
        raise KeyError(f"Unknown commodity '{commodity}'. "
                       f"Valid options: {sorted(COMMODITY_FACTORS)}")

    f = COMMODITY_FACTORS[commodity]

    scc = _coeff(coeffs, "social_cost_carbon")        # USD / t CO2e
    eut = _coeff(coeffs, "eutrophication")            # USD / kg PO4e
    wat = _coeff(coeffs, "water_scarcity")            # USD / m3
    lnd = _coeff(coeffs, "land_use")                  # USD / m2 / yr

    # --- Climate (GHG) ------------------------------------------------------
    # kg CO2e/kg * USD/t / 1000  -> USD/kg
    climate_central = f["ghg"] * scc / 1000.0
    climate = CostBand(
        climate_central,
        f["ghg"] * DEFAULT_COEFFICIENTS["social_cost_carbon"]["low"] / 1000.0,
        f["ghg"] * DEFAULT_COEFFICIENTS["social_cost_carbon"]["high"] / 1000.0,
    ) if not coeffs else CostBand(climate_central, climate_central * 0.27, climate_central * 1.62)

    # --- Eutrophication / reactive nitrogen --------------------------------
    # g PO4e/kg -> kg PO4e * USD/kg PO4e
    eutroph_central = (f["eutroph"] / 1000.0) * eut
    eutroph = CostBand(eutroph_central, eutroph_central * 0.32, eutroph_central * 2.58)

    # --- Water scarcity -----------------------------------------------------
    # L/kg -> m3 * USD/m3 * country water-stress multiplier
    water_central = (f["water"] / 1000.0) * wat * water_stress
    water = CostBand(water_central, water_central * 0.11, water_central * 2.78)

    # --- Land use / biodiversity opportunity cost --------------------------
    land_central = f["land"] * lnd
    land = CostBand(land_central, land_central * 0.22, land_central * 2.78)

    components = {
        "climate": climate,
        "eutrophication": eutroph,
        "water": water,
        "land": land,
    }

    # --- Optional dietary-health surcharge (OFF by default, clearly flagged)
    if include_health:
        surcharge = HEALTH_RISK_SURCHARGE.get(f["health"], HEALTH_RISK_SURCHARGE["neutral"])["value"]
        health = CostBand(surcharge, surcharge * 0.5, surcharge * 1.5)
        components["health"] = health

    # --- Aggregate (scaled to requested mass) ------------------------------
    total = CostBand(0, 0, 0)
    scaled_components = {}
    for name, band in components.items():
        sb = band.scaled(mass_kg)
        scaled_components[name] = sb.as_dict()
        total = total + sb

    market_price = f["ref_price"] * mass_kg
    true_price_central = market_price + total.central
    ratio = (total.central / market_price) if market_price else float("inf")

    return {
        "commodity": commodity,
        "mass_kg": mass_kg,
        "category": f["cat"],
        "components": scaled_components,
        "hidden_cost": total.as_dict(),
        "market_price": round(market_price, 4),
        "true_price": round(true_price_central, 4),
        "hidden_to_market_ratio": round(ratio, 3),
        "currency": "USD",
    }


def rank_commodities(coeffs: Optional[dict] = None, include_health: bool = False) -> list[dict]:
    """Return every commodity's hidden cost per kg, sorted high -> low (for the dashboard)."""
    rows = []
    for name in COMMODITY_FACTORS:
        tp = true_price(name, 1.0, coeffs, include_health=include_health)
        rows.append({
            "commodity": name,
            "category": tp["category"],
            "hidden_cost_per_kg": tp["hidden_cost"]["central"],
            "hidden_low": tp["hidden_cost"]["low"],
            "hidden_high": tp["hidden_cost"]["high"],
            **{k: v["central"] for k, v in tp["components"].items()},
        })
    return sorted(rows, key=lambda r: r["hidden_cost_per_kg"], reverse=True)


# ===========================================================================
# 2. NATIONAL HIDDEN-COST BREAKDOWN
# ===========================================================================
def national_breakdown(
    gdp_ppp_busd: float,
    hidden_cost_pct_gdp: float,
    health_share: float,
    environmental_share: float,
    social_share: float,
) -> dict:
    """
    Decompose a country's hidden costs across the three SOFA dimensions.

    Returns absolute USD-billion figures plus normalised shares. Shares are
    re-normalised defensively so rounding never breaks the 100% invariant.
    """
    total = gdp_ppp_busd * hidden_cost_pct_gdp
    s = health_share + environmental_share + social_share
    if s <= 0:
        raise ValueError("Capital shares must sum to a positive number.")
    health_share, environmental_share, social_share = (
        health_share / s, environmental_share / s, social_share / s)

    return {
        "total_busd": round(total, 2),
        "health_busd": round(total * health_share, 2),
        "environmental_busd": round(total * environmental_share, 2),
        "social_busd": round(total * social_share, 2),
        "health_share": round(health_share, 4),
        "environmental_share": round(environmental_share, 4),
        "social_share": round(social_share, 4),
        "per_capita_note": "divide by population for per-capita; see data pipeline",
    }


# ===========================================================================
# 3. FARM-PRACTICE SCENARIO COMPARATOR  (Phase-3 relevant: India / Kenya)
# ===========================================================================
# Meta-analysis deltas for switching from conventional to an agroecological practice.
# Each value is a fractional change (yield) or an absolute annual flow (carbon).
# All overridable in the UI so a country expert can localise them.
PRACTICE_DELTAS = {
    "Organic": {
        "yield_change": -0.20,            # Seufert 2012 / de Ponti 2012: ~ -20%
        "soil_carbon_tco2_ha_yr": 1.65,   # Gattinger 2012: ~0.45 tC -> ~1.65 tCO2/ha/yr
        "synthetic_n_reduction": 1.00,    # ~full removal of synthetic N inputs
        "pesticide_reduction": 0.95,
        "biodiversity_uplift": 0.30,      # Tuck 2014: +~30% species richness
        "source": "Seufert/de Ponti/Gattinger/Tuck meta-analyses",
    },
    "Agroforestry": {
        "yield_change": -0.05,            # variable; conservative small dip on the crop
        "soil_carbon_tco2_ha_yr": 3.50,   # tree biomass + soil C, ~1.5-4 tCO2/ha/yr
        "synthetic_n_reduction": 0.30,
        "pesticide_reduction": 0.40,
        "biodiversity_uplift": 0.50,
        "source": "IPCC AFOLU + agroforestry C-sequestration syntheses",
    },
    "Conservation / Watershed": {
        "yield_change": 0.05,             # restored water regulation can lift yields
        "soil_carbon_tco2_ha_yr": 0.80,
        "synthetic_n_reduction": 0.25,
        "pesticide_reduction": 0.30,
        "biodiversity_uplift": 0.25,
        "source": "Watershed-management restoration literature (Kenya programmes)",
    },
}


def compare_practices(
    practice: str,
    area_ha: float,
    baseline_yield_t_ha: float,
    crop_price_usd_t: float,
    baseline_n_cost_usd_ha: float,
    coeffs: Optional[dict] = None,
    deltas: Optional[dict] = None,
) -> dict:
    """
    Estimate the four-capitals change from adopting `practice` on `area_ha`.

    Produced capital : net farm income change (yield delta * price - input savings)
    Natural capital  : monetised soil-carbon sequestration + avoided N/eutrophication
    Social/Human     : qualitative biodiversity & resilience uplift (index, 0-1)

    Returns annual figures; all monetary values in USD. Designed to drive the
    side-by-side conventional-vs-agroecological view the Phase-3 pilots need.
    """
    if practice not in PRACTICE_DELTAS:
        raise KeyError(f"Unknown practice '{practice}'. Options: {sorted(PRACTICE_DELTAS)}")

    d = {**PRACTICE_DELTAS[practice], **(deltas or {})}
    scc = _coeff(coeffs, "social_cost_carbon")

    # --- Produced capital (income) -----------------------------------------
    baseline_revenue = area_ha * baseline_yield_t_ha * crop_price_usd_t
    new_revenue = baseline_revenue * (1 + d["yield_change"])
    revenue_change = new_revenue - baseline_revenue
    input_savings = area_ha * baseline_n_cost_usd_ha * d["synthetic_n_reduction"]
    produced_change = revenue_change + input_savings

    # --- Natural capital (climate value of sequestration) -------------------
    sequestration_tco2 = area_ha * d["soil_carbon_tco2_ha_yr"]
    carbon_value = sequestration_tco2 * scc

    # --- Natural capital (avoided reactive-nitrogen damage) -----------------
    # Proxy: avoided N input cost * a damage-multiplier (external > private cost).
    avoided_n_damage = input_savings * 1.5

    natural_change = carbon_value + avoided_n_damage

    # --- Social / human capital (index uplift) ------------------------------
    social_index = round(0.5 * d["biodiversity_uplift"] + 0.5 * d["pesticide_reduction"], 3)

    total_societal_value = produced_change + natural_change

    return {
        "practice": practice,
        "area_ha": area_ha,
        "produced_capital": {
            "revenue_change_usd": round(revenue_change, 2),
            "input_savings_usd": round(input_savings, 2),
            "net_income_change_usd": round(produced_change, 2),
        },
        "natural_capital": {
            "co2_sequestered_t": round(sequestration_tco2, 2),
            "carbon_value_usd": round(carbon_value, 2),
            "avoided_nitrogen_damage_usd": round(avoided_n_damage, 2),
            "net_natural_value_usd": round(natural_change, 2),
        },
        "social_human_capital": {
            "biodiversity_uplift": d["biodiversity_uplift"],
            "pesticide_reduction": d["pesticide_reduction"],
            "resilience_index_0_1": social_index,
        },
        "headline_societal_value_usd": round(total_societal_value, 2),
        "interpretation": (
            "Positive headline value means the practice's natural-capital gains "
            "outweigh any private income dip — the classic TEEBAgriFood case for "
            "results-based payments / PES to bridge the farmer's private gap."
        ),
    }
