"""
analytics.py
============
First-party, privacy-aware usage analytics for the AgriTrue demo.

What it does
------------
* Captures best-effort visitor context (IP, user-agent, locale, timezone, referrer)
  using Streamlit's supported `st.context` API.
* Logs structured events (visits, page views, calculations, downloads) to a local
  JSONL file you own — no third-party tracker, no cookies set beyond Streamlit's own.
* Enriches public IPs to an approximate city/country via the free ip-api.com service
  (cached, short timeout, fails gracefully — private/local IPs are never sent).
* Provides helpers the owner dashboard uses to summarise sessions and locations.

Responsible-use note
---------------------
This is standard first-party analytics for your OWN demo app. If you deploy publicly to
an audience that may include EU/UK visitors, add a short privacy notice / consent banner
(GDPR/ePrivacy). The app shows a visible disclosure caption by default. IP geolocation is
approximate and never used to identify individuals.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import ipaddress
import json
import os
import threading
import urllib.request
import uuid

LOG_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "data", "analytics_log.jsonl"))


# ---------------------------------------------------------------------------
# Visitor context
# ---------------------------------------------------------------------------
def _safe(getter, default=None):
    try:
        return getter()
    except Exception:  # noqa: BLE001
        return default


def get_client_info(st) -> dict:
    """Best-effort visitor context from st.context (degrades gracefully off-cloud)."""
    ctx = st.context
    headers = _safe(lambda: dict(ctx.headers), {}) or {}
    ip = _safe(lambda: ctx.ip_address)
    # Fallback: parse the left-most X-Forwarded-For entry.
    if not ip:
        xff = headers.get("X-Forwarded-For") or headers.get("x-forwarded-for")
        if xff:
            ip = xff.split(",")[0].strip()
    return {
        "ip": str(ip) if ip else "unknown",
        "user_agent": headers.get("User-Agent", headers.get("user-agent", "unknown")),
        "referrer": headers.get("Referer", headers.get("referer", "")),
        "locale": _safe(lambda: ctx.locale) or "",
        "timezone": _safe(lambda: ctx.timezone) or "",
        "url": _safe(lambda: ctx.url) or "",
    }


def anonymise_ip(ip: str) -> str:
    """Short, non-reversible hash so the owner can count unique visitors without storing raw IPs in views."""
    return hashlib.sha256(str(ip).encode("utf-8")).hexdigest()[:10]


def _is_public_ip(ip: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
        return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved)
    except ValueError:
        return False


def geolocate(ip: str, timeout: int = 3) -> dict:
    """Approximate {city, country, lat, lon} for a public IP via ip-api.com. Never sends private IPs."""
    if not _is_public_ip(ip):
        return {"city": "local/private", "country": "", "lat": None, "lon": None}
    try:
        url = f"http://ip-api.com/json/{ip}?fields=status,country,city,lat,lon"
        req = urllib.request.Request(url, headers={"User-Agent": "AgriTrue/0.1"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            d = json.loads(resp.read().decode("utf-8"))
        if d.get("status") == "success":
            return {"city": d.get("city", ""), "country": d.get("country", ""),
                    "lat": d.get("lat"), "lon": d.get("lon")}
    except Exception:  # noqa: BLE001
        pass
    return {"city": "", "country": "", "lat": None, "lon": None}


# ---------------------------------------------------------------------------
# Event logging
# ---------------------------------------------------------------------------
def log_event(event_type: str, session_id: str, client: dict, **detail) -> None:
    """Append one structured event to the JSONL log (best-effort; never raises)."""
    record = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "event": event_type,
        "session": session_id,
        "visitor": anonymise_ip(client.get("ip", "unknown")),
        "ip": client.get("ip", "unknown"),
        "geo": client.get("geo", {}),
        "user_agent": client.get("user_agent", ""),
        "locale": client.get("locale", ""),
        "timezone": client.get("timezone", ""),
        "referrer": client.get("referrer", ""),
        "detail": detail,
    }
    # 1) Append to the local JSONL log file (used when running locally).
    try:
        os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except Exception:  # noqa: BLE001
        pass

    # 2) Also emit a one-line entry to stdout so the events show up in the hosting
    #    platform's log viewer (e.g. Streamlit Cloud -> "Manage app" -> logs). This is
    #    the "analytics in the logs only" path — nothing is surfaced in the app UI.
    try:
        geo = record["geo"] or {}
        loc = f"{geo.get('city', '')}/{geo.get('country', '')}".strip("/")
        detail = " ".join(f"{k}={v}" for k, v in detail.items())
        print(f"[AGRITRUE-ANALYTICS] {record['ts']} {event:<14} "
              f"ip={record['ip']} loc={loc or '-'} session={session_id} {detail}".rstrip(),
              flush=True)
    except Exception:  # noqa: BLE001
        pass


def load_events() -> list[dict]:
    """Read all logged events (newest last). Returns [] if no log yet."""
    if not os.path.exists(LOG_PATH):
        return []
    out = []
    with open(LOG_PATH, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    return out


def summarise(events: list[dict]) -> dict:
    """Aggregate the log into headline metrics for the owner dashboard."""
    sessions, visitors, countries = set(), set(), {}
    by_event, by_view = {}, {}
    for e in events:
        sessions.add(e.get("session"))
        visitors.add(e.get("visitor"))
        by_event[e["event"]] = by_event.get(e["event"], 0) + 1
        geo = e.get("geo") or {}
        c = geo.get("country") or ""
        if c:
            countries[c] = countries.get(c, 0) + 1
        if e["event"] == "page_view":
            v = e.get("detail", {}).get("view", "?")
            by_view[v] = by_view.get(v, 0) + 1
    return {
        "total_events": len(events),
        "sessions": len(sessions - {None}),
        "unique_visitors": len(visitors - {None}),
        "countries": countries,
        "by_event": by_event,
        "by_view": by_view,
    }


# ---------------------------------------------------------------------------
# Streamlit session glue
# ---------------------------------------------------------------------------
def _resolve_geo_async(session_id: str, client: dict) -> None:
    """Geolocate the visitor in a background thread so it never delays first paint."""
    def worker():
        geo = geolocate(client.get("ip", "unknown"))
        if geo and geo.get("country"):
            client["geo"] = geo                       # mutate the cached dict in place
            log_event("geo", session_id, client)
    threading.Thread(target=worker, daemon=True).start()


def ensure_session(st) -> tuple[str, dict]:
    """
    Get (or create) this browser session's id + cached client context.
    Logs a single 'session_start' event the first time the session is seen.

    Geolocation runs in the background (non-blocking) so the first page render is never
    held up waiting on the external IP-lookup service.
    """
    ss = st.session_state
    if "agritrue_session" not in ss:
        sid = uuid.uuid4().hex[:12]
        ss["agritrue_session"] = sid
        client = get_client_info(st)
        client["geo"] = {}                            # filled asynchronously below
        ss["agritrue_client"] = client
        log_event("session_start", sid, client)       # log immediately, no network wait
        _resolve_geo_async(sid, client)
    return ss["agritrue_session"], ss["agritrue_client"]


def track_view(st, view: str) -> None:
    """Log a page_view only when the active view actually changes (avoids rerun spam)."""
    ss = st.session_state
    if ss.get("agritrue_last_view") != view:
        ss["agritrue_last_view"] = view
        sid, client = ss["agritrue_session"], ss["agritrue_client"]
        log_event("page_view", sid, client, view=view)


def track_action(st, action: str, **detail) -> None:
    """Log a discrete user action (calc run, download, etc.)."""
    ss = st.session_state
    if "agritrue_session" in ss:
        log_event(action, ss["agritrue_session"], ss["agritrue_client"], **detail)
