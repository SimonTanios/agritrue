# AgriTrue 🌍 — True Cost Accounting for Agrifood Systems

A working **True Cost Accounting (TCA)** platform built on the **TEEBAgriFood** four-capitals
framework and calibrated to **FAO's State of Food and Agriculture (SOFA) 2024** — which valued
the hidden costs of global agrifood systems at **~US$12 trillion/year (~10% of global GDP),
~70% of it health-driven, across 156 countries.**

It turns that published evidence into three decision tools a programme team or country partner
can actually use, plus a transparent methodology layer.

---

## What it does

| View | Question it answers | Data behind it |
|------|--------------------|----------------|
| **Global & National Dashboard** | *Where do hidden costs fall — by country, capital, and agrifood-system type?* | SOFA 2024 aggregates + modelled country split |
| **True Price Calculator** | *What does 1 kg of this food really cost once externalities are priced in?* | Poore & Nemecek (2018) LCA medians + monetization coefficients |
| **Diet True-Cost Comparator** | *How does a national diet compare to the EAT-Lancet planetary-health diet on hidden cost & footprint?* | EAT-Lancet (2019) + FAO Food Balance Sheet archetypes |
| **Farm-Practice Comparator** | *Conventional vs organic/agroforestry/watershed — what changes across the four capitals?* | Organic/agroecology meta-analyses (Seufert, Gattinger, Tuck …) |
| **Methodology & Sources** | *Every coefficient, citation, and caveat.* | Fully documented, all user-adjustable |

*(Usage analytics run silently in the background — see below — with no view in the app UI.)*

Every figure on screen is produced by the audited `tca` engine (**22 passing unit tests**), and
the sidebar sliders re-price the *entire* app live — the core TCA transparency principle of
*showing ranges and assumptions, not false precision.*

**Extra capabilities baked in:**
- 📄 **One-page PDF briefs** — every calculator, diet comparison, and country profile exports a
  branded PDF (pure-Python `fpdf2`, charts drawn natively, no headless browser needed).
- 📊 **First-party analytics** — a built-in, privacy-aware usage log (page views, actions,
  downloads) with approximate visitor geolocation and an owner-only dashboard + visitor map.
- 🔌 **FAOSTAT client** — a `FAOStatClient` in `tca/data_pipeline.py` documents the production
  data path for swapping the bundled seed for live/official figures.

---

## Quick start (Windows)

Double-click **`run.bat`** — it creates a virtual environment, installs dependencies, runs the
tests, and opens the dashboard at <http://localhost:8501>.

Or manually:

```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m tca.data_pipeline      :: generate the seed dataset
python tests\test_engine.py      :: run the tests (optional)
streamlit run app.py
```

## Share a live URL with the manager (free, 5 minutes)

1. Push this folder to a GitHub repo.
2. Go to <https://share.streamlit.io>, sign in with GitHub, and point it at `app.py`.
3. Streamlit Community Cloud builds it and gives you a public `…streamlit.app` URL you can
   email or put in your interview portfolio. No server to maintain.

---

## Architecture

```
TEEBAgriFood/
├── app.py                    # Streamlit dashboard (6 views)
├── tca/
│   ├── engine.py             # TCA engine — true_price / national_breakdown / compare_practices
│   ├── coefficients.py       # All LCA factors & monetization coefficients (fully sourced)
│   ├── diets.py              # Diet patterns + diet true-cost comparator
│   ├── report.py             # One-page PDF brief generator (fpdf2)
│   ├── analytics.py          # First-party usage analytics + IP geolocation
│   └── data_pipeline.py      # National dataset loader + live FAOSTAT API client
├── tests/
│   ├── test_engine.py        # 12 engine unit tests
│   └── test_features.py      # 10 diet / PDF / analytics unit tests
├── data/                     # Generated seed dataset (CSV) + analytics log (JSONL)
├── .streamlit/
│   └── secrets.toml.example  # OWNER_KEY for the analytics view
├── requirements.txt
├── run.bat                   # One-click Windows launcher
└── README.md
```

## Analytics — logs only, no UI ("who's looking at my site")

There is **no analytics view in the app** — reviewers never see it. Every visit and action is
recorded silently to two places:

1. **The server logs.** Each event prints one line beginning `[AGRITRUE-ANALYTICS]`. On
   Streamlit Community Cloud, open your app → **Manage app → Logs** to read who opened the link,
   their approximate location, and what they clicked — without any dashboard in the app.
2. **A local file** `data/analytics_log.jsonl` (when running on your own machine).

Read the local log from the command line:

```bat
python view_logs.py            :: summary + recent events
python view_logs.py --all      :: every event
python view_logs.py --watch    :: live tail
```

It captures session, approximate city/country (via free `ip-api.com`; public IPs only — private/
local IPs are never sent), pages viewed, calculations, comparisons, and PDF downloads.

> **Privacy note (worth knowing):** logging visitor IPs is first-party analytics, the same thing
> a link shortener or email-open pixel does. It is low-risk for a personal demo shared with one
> reviewer. If you ever point this at a broad/EU audience, add a short privacy/consent notice —
> standard GDPR/ePrivacy hygiene for anything that logs IPs.

The engine is **pure-Python (stdlib only)**, so it is portable, testable, and embeddable
independently of the dashboard. `data_pipeline.py` ships a `FAOStatClient` that pulls live
emissions/land-use data from the FAOSTAT public API (no key required), demonstrating the full
production data path — the dashboard degrades gracefully to bundled data when offline.

---

## Honest caveats (by design)

1. **Per-country values are modelled** estimates calibrated so regional/global totals match the
   published SOFA 2024 headline — not the official country microdata. The `FAOStatClient` shows
   exactly how to swap in live/official sources.
2. **Per-commodity health costs** are optional and clearly flagged: SOFA attributes the health
   burden to dietary *patterns*, not single foods.
3. **All coefficients are adjustable** in the UI so any reviewer can stress-test every assumption.

---

## Key references

- FAO (2024). *The State of Food and Agriculture 2024.*
- FAO (2023). *SOFA 2023: Revealing the true cost of food.*
- Poore & Nemecek (2018). *Science* 360:987–992.
- Rennert et al. (2022). *Nature* 610:687–692 (social cost of carbon).
- TEEB (2018). *TEEB for Agriculture & Food.* UN Environment.

---

*Built as a demonstration for the TEEBAgriFood programme, UN Environment Programme.*
