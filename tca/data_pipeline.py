"""
data_pipeline.py
================
Data access layer for AgriTrue.

Two responsibilities:
  1. load_national_dataset()  -> the country hidden-cost table used by the dashboard.
     Reads data/sofa_hidden_costs.csv if present; otherwise falls back to a built-in,
     fully-deterministic seed table calibrated to SOFA 2024 aggregates.
  2. FAOStatClient            -> a thin, dependency-light client for the FAOSTAT public
     API, so the same dashboard can be pointed at LIVE emissions / land-use data instead
     of the bundled seed. This demonstrates the production data path end-to-end.

IMPORTANT (honesty): the per-country values in the seed table are *modelled* estimates
calibrated so regional and global totals line up with the published SOFA 2024 headline
($12T, ~10% of GDP, ~70% health). They are illustrative — the FAOStatClient and the
methodology tab document exactly how to swap in the official SOFA country dataset.
"""

from __future__ import annotations

import csv
import json
import os
import urllib.parse
import urllib.request
from typing import Optional

from .coefficients import AGRIFOOD_SYSTEM_TYPES

_DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
_CSV_PATH = os.path.normpath(os.path.join(_DATA_DIR, "sofa_hidden_costs.csv"))


# ---------------------------------------------------------------------------
# Built-in seed table  (country, iso3, region, system type, GDP PPP $bn,
#                       hidden cost % of GDP, and the health/env/social split)
# ---------------------------------------------------------------------------
# Columns: name, iso3, region, system, gdp_ppp_busd, hc_pct_gdp, health, env, social
_SEED = [
    ("United States",   "USA", "North America",   "Industrial",        25035, 0.085, 0.80, 0.17, 0.03),
    ("China",           "CHN", "East Asia",       "Formalizing",       30327, 0.110, 0.66, 0.28, 0.06),
    ("India",           "IND", "South Asia",      "Expanding",         11875, 0.140, 0.48, 0.30, 0.22),
    ("Brazil",          "BRA", "Latin America",   "Diversifying",       3837, 0.120, 0.58, 0.33, 0.09),
    ("Indonesia",       "IDN", "Southeast Asia",  "Expanding",          4036, 0.130, 0.50, 0.34, 0.16),
    ("Nigeria",         "NGA", "Sub-Saharan Africa","Traditional",      1275, 0.190, 0.30, 0.24, 0.46),
    ("Germany",         "DEU", "Europe",          "Industrial",         5310, 0.075, 0.81, 0.16, 0.03),
    ("Kenya",           "KEN", "Sub-Saharan Africa","Traditional",       310, 0.200, 0.28, 0.26, 0.46),
    ("Ethiopia",        "ETH", "Sub-Saharan Africa","Traditional",       360, 0.230, 0.26, 0.22, 0.52),
    ("France",          "FRA", "Europe",          "Industrial",         3870, 0.078, 0.79, 0.18, 0.03),
    ("Japan",           "JPN", "East Asia",       "Industrial",         5700, 0.072, 0.82, 0.15, 0.03),
    ("Mexico",          "MEX", "Latin America",   "Diversifying",       2740, 0.115, 0.60, 0.30, 0.10),
    ("Viet Nam",        "VNM", "Southeast Asia",  "Expanding",          1330, 0.135, 0.49, 0.33, 0.18),
    ("Pakistan",        "PAK", "South Asia",      "Expanding",          1500, 0.160, 0.42, 0.28, 0.30),
    ("Bangladesh",      "BGD", "South Asia",      "Expanding",          1300, 0.155, 0.44, 0.27, 0.29),
    ("United Kingdom",  "GBR", "Europe",          "Industrial",         3660, 0.076, 0.80, 0.17, 0.03),
    ("Italy",           "ITA", "Europe",          "Industrial",         3050, 0.080, 0.79, 0.18, 0.03),
    ("South Africa",    "ZAF", "Sub-Saharan Africa","Diversifying",      930, 0.130, 0.55, 0.31, 0.14),
    ("Egypt",           "EGY", "North Africa",    "Expanding",          1700, 0.140, 0.52, 0.30, 0.18),
    ("Turkey",          "TUR", "West Asia",       "Diversifying",       3000, 0.110, 0.62, 0.29, 0.09),
    ("Argentina",       "ARG", "Latin America",   "Diversifying",       1240, 0.118, 0.59, 0.32, 0.09),
    ("Canada",          "CAN", "North America",   "Industrial",         2240, 0.077, 0.80, 0.17, 0.03),
    ("Australia",       "AUS", "Oceania",         "Industrial",         1700, 0.079, 0.79, 0.18, 0.03),
    ("Thailand",        "THA", "Southeast Asia",  "Diversifying",       1480, 0.122, 0.57, 0.32, 0.11),
    ("Philippines",     "PHL", "Southeast Asia",  "Expanding",          1170, 0.140, 0.49, 0.31, 0.20),
    ("Tanzania",        "TZA", "Sub-Saharan Africa","Traditional",       210, 0.210, 0.27, 0.25, 0.48),
    ("Uganda",          "UGA", "Sub-Saharan Africa","Traditional",       130, 0.215, 0.27, 0.24, 0.49),
    ("Ghana",           "GHA", "Sub-Saharan Africa","Traditional",       230, 0.185, 0.32, 0.26, 0.42),
    ("Colombia",        "COL", "Latin America",   "Diversifying",        990, 0.120, 0.58, 0.31, 0.11),
    ("Spain",           "ESP", "Europe",          "Industrial",         2230, 0.080, 0.78, 0.19, 0.03),
    ("Poland",          "POL", "Europe",          "Formalizing",        1700, 0.090, 0.72, 0.23, 0.05),
    ("Ukraine",         "UKR", "Europe",          "Formalizing",         420, 0.130, 0.55, 0.34, 0.11),
    ("Morocco",         "MAR", "North Africa",    "Expanding",           370, 0.145, 0.50, 0.30, 0.20),
    ("Peru",            "PER", "Latin America",   "Diversifying",        560, 0.125, 0.56, 0.31, 0.13),
    ("Myanmar",         "MMR", "Southeast Asia",  "Traditional",         270, 0.180, 0.36, 0.27, 0.37),
    ("Mozambique",      "MOZ", "Sub-Saharan Africa","Protracted crisis",  50, 0.250, 0.22, 0.20, 0.58),
    ("Dem. Rep. Congo", "COD", "Sub-Saharan Africa","Protracted crisis", 130, 0.260, 0.20, 0.20, 0.60),
    ("Yemen",           "YEM", "West Asia",       "Protracted crisis",    65, 0.280, 0.20, 0.18, 0.62),
    ("Afghanistan",     "AFG", "South Asia",      "Protracted crisis",    80, 0.270, 0.21, 0.19, 0.60),
    ("Saudi Arabia",    "SAU", "West Asia",       "Formalizing",        1900, 0.090, 0.70, 0.25, 0.05),
    ("Netherlands",     "NLD", "Europe",          "Industrial",         1280, 0.074, 0.80, 0.17, 0.03),
    ("Republic of Korea","KOR","East Asia",       "Industrial",         2700, 0.075, 0.81, 0.16, 0.03),
    ("Malaysia",        "MYS", "Southeast Asia",  "Formalizing",        1130, 0.105, 0.64, 0.29, 0.07),
    ("Russian Fed.",    "RUS", "Europe",          "Formalizing",        5300, 0.095, 0.68, 0.27, 0.05),
    ("Iran",            "IRN", "West Asia",       "Diversifying",       1700, 0.120, 0.58, 0.30, 0.12),
]

_FIELDS = ["name", "iso3", "region", "system", "gdp_ppp_busd",
           "hc_pct_gdp", "health", "env", "social"]


def _seed_rows() -> list[dict]:
    rows = []
    for r in _SEED:
        d = dict(zip(_FIELDS, r))
        # derive absolute hidden-cost figures so the dashboard can sum/aggregate
        total = d["gdp_ppp_busd"] * d["hc_pct_gdp"]
        d["hidden_total_busd"] = round(total, 2)
        d["health_busd"] = round(total * d["health"], 2)
        d["env_busd"] = round(total * d["env"], 2)
        d["social_busd"] = round(total * d["social"], 2)
        d["system_note"] = AGRIFOOD_SYSTEM_TYPES.get(d["system"], {}).get("note", "")
        rows.append(d)
    return rows


def write_seed_csv(path: str = _CSV_PATH) -> str:
    """Materialise the seed table to CSV (used by run.bat on first launch)."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    rows = _seed_rows()
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    return path


def load_national_dataset() -> list[dict]:
    """Load the country table from CSV if available, else the built-in seed."""
    if os.path.exists(_CSV_PATH):
        with open(_CSV_PATH, newline="", encoding="utf-8") as fh:
            out = []
            for row in csv.DictReader(fh):
                for k in ("gdp_ppp_busd", "hc_pct_gdp", "health", "env", "social",
                          "hidden_total_busd", "health_busd", "env_busd", "social_busd"):
                    if k in row and row[k] not in (None, ""):
                        row[k] = float(row[k])
                out.append(row)
            if out:
                return out
    return _seed_rows()


# ---------------------------------------------------------------------------
# Live FAOSTAT client — the production data path
# ---------------------------------------------------------------------------
class FAOStatClient:
    """
    Minimal client for the FAOSTAT public API (https://fenixservices.fao.org/faostat).

    Example
    -------
    >>> c = FAOStatClient()
    >>> c.emissions_total(area_codes=["114"], year=2021)   # 114 = Kenya
    No API key required. Network-dependent; the dashboard degrades gracefully to the
    bundled seed when offline.
    """
    BASE = "https://fenixservices.fao.org/faostat/api/v1/en"

    def __init__(self, timeout: int = 20):
        self.timeout = timeout

    def _get(self, path: str, params: dict) -> dict:
        url = f"{self.BASE}{path}?{urllib.parse.urlencode(params, doseq=True)}"
        req = urllib.request.Request(url, headers={"User-Agent": "AgriTrue/0.1"})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))

    def emissions_total(self, area_codes: list[str], year: int = 2021) -> dict:
        """
        Total agrifood-system GHG emissions (GT domain, CO2eq) for the given FAOSTAT
        area codes. Returns the raw FAOSTAT JSON 'data' payload.
        """
        params = {
            "area": area_codes,
            "element": "7273",        # Emissions (CO2eq) (AR5)
            "item": "6825",           # Emissions on agricultural land (aggregate)
            "year": year,
            "output_type": "objects",
        }
        return self._get("/data/GT", params)

    def land_use(self, area_codes: list[str], year: int = 2021) -> dict:
        """Agricultural land use (RL domain), area in 1000 ha."""
        params = {
            "area": area_codes,
            "element": "5110",        # Area
            "item": "6610",           # Agricultural land
            "year": year,
            "output_type": "objects",
        }
        return self._get("/data/RL", params)


if __name__ == "__main__":  # pragma: no cover
    path = write_seed_csv()
    print(f"Wrote {len(_seed_rows())} country rows to {path}")
