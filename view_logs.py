"""
view_logs.py  —  read the AgriTrue usage analytics from the command line.

The analytics dashboard was intentionally removed from the app UI (so reviewers never
see it). Usage events are still recorded; inspect them here, privately.

Usage:
    python view_logs.py            # summary + 30 most recent events
    python view_logs.py --all      # summary + every event
    python view_logs.py --watch    # live tail (refreshes every 3s)

When the app is deployed to Streamlit Community Cloud, the same events also print to the
hosting log viewer: open your app at share.streamlit.io -> "Manage app" -> Logs and look
for lines beginning with [AGRITRUE-ANALYTICS].
"""

import sys
import time

from tca import analytics


def show(limit=30, show_all=False):
    events = analytics.load_events()
    if not events:
        print("No events logged yet. Open the app and click around, then re-run this.")
        return
    s = analytics.summarise(events)
    print("=" * 70)
    print("AgriTrue — usage analytics")
    print("=" * 70)
    print(f"  Sessions          : {s['sessions']}")
    print(f"  Unique visitors   : {s['unique_visitors']}")
    print(f"  Total events      : {s['total_events']}")
    if s["countries"]:
        tops = sorted(s["countries"].items(), key=lambda kv: -kv[1])
        print(f"  Countries         : " + ", ".join(f"{c} ({n})" for c, n in tops))
    if s["by_view"]:
        print(f"  Pages viewed      : " + ", ".join(f"{v}={n}" for v, n in
                                                     sorted(s['by_view'].items(), key=lambda kv: -kv[1])))
    print(f"  Event types       : " + ", ".join(f"{e}={n}" for e, n in s["by_event"].items()))
    print("-" * 70)
    rows = events if show_all else events[-limit:]
    for e in rows:
        geo = e.get("geo") or {}
        loc = f"{geo.get('city', '')}/{geo.get('country', '')}".strip("/") or "-"
        detail = " ".join(f"{k}={v}" for k, v in (e.get("detail") or {}).items())
        print(f"  {e.get('ts', ''):<20} {e.get('event', ''):<14} "
              f"ip={e.get('ip', '-'):<16} loc={loc:<22} {detail}")
    print("=" * 70)
    print(f"Log file: {analytics.LOG_PATH}")


if __name__ == "__main__":
    args = set(sys.argv[1:])
    if "--watch" in args:
        try:
            while True:
                print("\033[2J\033[H", end="")  # clear screen
                show(limit=40)
                time.sleep(3)
        except KeyboardInterrupt:
            pass
    else:
        show(show_all="--all" in args)
