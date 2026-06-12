"""AgriTrue — a True Cost Accounting toolkit for TEEBAgriFood / SOFA 2024."""

from .engine import (
    true_price,
    rank_commodities,
    national_breakdown,
    compare_practices,
    PRACTICE_DELTAS,
)
from .coefficients import (
    COMMODITY_FACTORS,
    DEFAULT_COEFFICIENTS,
    AGRIFOOD_SYSTEM_TYPES,
    SOFA_2024_GLOBAL,
)
from .diets import DIET_PATTERNS, diet_hidden_cost, compare_diets

__version__ = "0.2.0"
__all__ = [
    "true_price", "rank_commodities", "national_breakdown", "compare_practices",
    "PRACTICE_DELTAS", "COMMODITY_FACTORS", "DEFAULT_COEFFICIENTS",
    "AGRIFOOD_SYSTEM_TYPES", "SOFA_2024_GLOBAL",
    "DIET_PATTERNS", "diet_hidden_cost", "compare_diets",
]
