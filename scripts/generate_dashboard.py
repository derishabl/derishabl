#!/usr/bin/env python3
"""Generate a minimal, neutral GitHub activity dashboard.

Data comes directly from GitHub's GraphQL API. The generated SVG has no
external dependencies and supports both light and dark GitHub themes.
"""

from __future__ import annotations

import argparse
import calendar
import json
import math
import os
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

USERNAME = os.environ.get("PROFILE_USERNAME", "derishabl")
GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = r"""
query ProfileActivity($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          firstDay
          contributionDays {
            date
            contributionCount
            weekday
          }
        }
      }
    }
  }
}
"""

PALETTES = {
    "dark": {
        "bg": "#0d0f10",
        "border": "#2c3033",
        "text": "#f0f1f2",
        "muted": "#8d9398",
        "faint": "#555b60",
        "rule": "#25292c",
        "idle": "#24282b",
        "levels": ["#41474c", "#666d72", "#9ba1a6", "#e1e4e6"],
        "scan": "#d8dcdf",
        "cursor": "#f0f1f2",
    },
    "light": {
        "bg": "#f7f7f6",
        "border": "#d5d8da",
        "text": "#202326",
        "muted": "#686e73",
        "faint": "#a1a6aa",
        "rule": "#e1e3e4",
        "idle": "#e4e6e7",
        "levels": ["#c9ccce", "#a4a9ad", "#73797e", "#34393d"],
        "scan": "#555c61",
        "cursor": "#202326",
    },
}


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_data(username: str, token: str) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today - timedelta(days=364), time.min, timezone.utc)
    end = datetime.combine(today, time.max, timezone.utc).replace(microsecond=0)
    body = json.dumps(
        {
            "query": QUERY,
            "variables": {
                "login": username,
                "from": iso_z(start),
                "to": iso_z(end),
            },
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "derishabl-profile-activity",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API returned HTTP {exc.code}: {detail}") from exc
    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {result['errors']}")
    if not result.get("data", {}).get("user"):
        raise RuntimeError(f"GitHub user {username!r} was not found")
    return result


def calendar_data(data: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    user = data["data"]["user"]
    raw_weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    days = [day for week in raw_weeks for day in week["contributionDays"]]
    days.sort(key=lambda item: item["date"])
    if not days:
        raise RuntimeError("GitHub returned an empty contribution calendar")
    first, last = days[0]["date"], days[-1]["date"]
    weeks = []
    for raw_week in raw_weeks:
        selected = [day for day in raw_week["contributionDays"] if first <= day["date"] <= last]
        if selected:
            weeks.append({"days": selected})
    return user, days, weeks


def streaks(days: list[dict[str, Any]]) -> tuple[int, int]:
    longest = run = 0
    for day in days:
        if day["contributionCount"] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    # Today is allowed to be empty while yesterday's run is still current.
    cursor = len(days) - 1
    if cursor >= 0 and days[cursor]["contributionCount"] == 0:
        cursor -= 1
    if cursor < len(days) - 2:
        return 0, longest

    current = 0
    while cursor >= 0 and days[cursor]["contributionCount"] > 0:
        current += 1
        cursor -= 1
    return current, longest


def level_for(count: int, maximum: int) -> int:
    if count <= 0 or maximum <= 0:
        return -1
    ratio = math.sqrt(count / maximum)
    if ratio < 0.28:
        return 0
    if ratio < 0.48:
        return 1
    if ratio < 0.72:
        return 2
    return 3


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def build_dashboard(data: dict[str, Any], username: str, theme: str) -> str:
    colors = PALETTES[theme]
    _, days, weeks = calendar_data(data)
    total = sum(day["contributionCount"] for day in days)
    active_days = sum(day["contributionCount"] > 0 for day in days)
    current_streak, longest_streak = streaks(days)
    maximum = max((day["contributionCount"] for day in days), default=0)
    first_date = date.fromisoformat(days[0]["date"])
    last_date = date.fromisoformat(days[-1]["date"])

    grid_left, grid_right = 74.0, 919.0
    grid_top, row_step = 205.0, 10.5
    week_count = max(1, len(weeks))
    week_step = (grid_right - grid_left) / max(1, week_count - 1)
    cell_width = min(12.4, week_step - 3.0)
    cell_height = 6.5

    date_to_week: dict[str, int] = {}
    week_groups: list[str] = []
    latest_date = days[-1]["date"]
    for week_index, week in enumerate(weeks):
        x = grid_left + week_index * week_step
        cells: list[str] = []
        for day in week["days"]:
            date_to_week[day["date"]] = week_index
            count = int(day["contributionCount"])
            level = level_for(count, maximum)
            fill = colors["idle"] if level < 0 else colors["levels"][level]
            y = grid_top + int(day["weekday"]) * row_step
            latest_class = " latest-day" if day["date"] == latest_date else ""
            noun = "contribution" if count == 1 else "contributions"
            cells.append(
                f'<rect class="day-cell{latest_class}" x="{fmt(x)}" y="{fmt(y)}" '
                f'width="{fmt(cell_width)}" height="{fmt(cell_height)}" rx="3.25" fill="{fill}">'
                f'<title>{escape(day["date"])}: {count} {noun}</title></rect>'
            )
        week_groups.append(
            f'<g class="week" style="animation-delay:{week_index * 0.018:.3f}s">'
            f'{"".join(cells)}</g>'
        )

    month_labels: list[str] = []
    previous_month: tuple[int, int] | None = None
    for day in days:
        day_date = date.fromisoformat(day["date"])
        month_key = (day_date.year, day_date.month)
        if month_key == previous_month:
            continue
        previous_month = month_key
        week_index = date_to_week.get(day["date"], 0)
        x = grid_left + week_index * week_step
        month_labels.append(
            f'<text x="{fmt(x)}" y="191" class="mono" fill="{colors["muted"]}" '
            f'font-size="7.5" letter-spacing="0.5">{calendar.month_abbr[day_date.month].upper()}</text>'
        )

    stat_positions = [40, 270, 500, 730]
    stats = [
        (f"{total:,}", "CONTRIBUTIONS"),
        (str(active_days), "ACTIVE DAYS"),
        (str(current_streak), "CURRENT STREAK"),
        (str(longest_streak), "LONGEST STREAK"),
    ]
    stat_markup: list[str] = []
    for index, ((value, label), x) in enumerate(zip(stats, stat_positions)):
        stat_markup.append(
            f'<g class="stat" style="animation-delay:{index * 0.08:.2f}s">'
            f'<text x="{x}" y="113" class="sans" fill="{colors["text"]}" '
            f'font-size="32" font-weight="680" letter-spacing="-0.8">{value}</text>'
            f'<text x="{x}" y="136" class="mono" fill="{colors["muted"]}" '
            f'font-size="8.5" letter-spacing="1.15">{label}</text></g>'
        )

    first_label = first_date.strftime("%d %b %Y").upper()
    last_label = last_date.strftime("%d %b %Y").upper()
    description = (
        f"Minimal {theme} activity dashboard for {username}: {total} contributions, "
        f"{active_days} active days, current streak {current_streak}, longest streak {longest_streak}."
    )

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="320" viewBox="0 0 960 320" role="img" aria-labelledby="title desc">
  <title id="title">{escape(username)} — GitHub activity</title>
  <desc id="desc">{escape(description)}</desc>
  <!-- Generated from GitHub data through {days[-1]["date"]}. Do not edit by hand. -->

  <defs>
    <linearGradient id="scan" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{colors["scan"]}" stop-opacity="0"/>
      <stop offset="0.5" stop-color="{colors["scan"]}" stop-opacity="0.09"/>
      <stop offset="1" stop-color="{colors["scan"]}" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="calendarClip"><rect x="68" y="198" width="860" height="82" rx="7"/></clipPath>
  </defs>

  <style>
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; font-variant-numeric: tabular-nums; }}
    .sans {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-variant-numeric: tabular-nums; }}
    .stat {{ animation: enter .45s ease-out both; }}
    .week {{ animation: enter .32s ease-out both; }}
    .calendar-scan {{ animation: sweep 10s 1.3s ease-in-out infinite; }}
    .latest-day {{ stroke: {colors["cursor"]}; stroke-width: 1; animation: cursor 2.8s ease-in-out infinite; }}
    @keyframes enter {{ from {{ opacity: 0; transform: translateY(4px); }} to {{ opacity: 1; transform: translateY(0); }} }}
    @keyframes sweep {{ 0% {{ transform: translateX(-70px); opacity: 0; }} 12%, 82% {{ opacity: 1; }} 100% {{ transform: translateX(930px); opacity: 0; }} }}
    @keyframes cursor {{ 0%, 100% {{ stroke-opacity: .2; }} 50% {{ stroke-opacity: .85; }} }}
    @media (prefers-reduced-motion: reduce) {{
      .stat, .week, .calendar-scan, .latest-day {{ animation: none; opacity: 1; transform: none; }}
    }}
  </style>

  <rect width="960" height="320" rx="22" fill="{colors["bg"]}"/>
  <rect x="0.75" y="0.75" width="958.5" height="318.5" rx="21.25" fill="none" stroke="{colors["border"]}" stroke-width="1.5"/>

  <text x="40" y="37" class="mono" fill="{colors["text"]}" font-size="11" font-weight="700" letter-spacing="1.6">ACTIVITY / LAST 365 DAYS</text>
  <text x="920" y="37" text-anchor="end" class="mono" fill="{colors["muted"]}" font-size="8" letter-spacing="0.85">UPDATED {last_label}</text>
  <path d="M35 58H925" stroke="{colors["rule"]}"/>

  {''.join(stat_markup)}
  <g stroke="{colors["rule"]}"><path d="M250 76V140"/><path d="M480 76V140"/><path d="M710 76V140"/></g>
  <path d="M35 157H925" stroke="{colors["rule"]}"/>

  <text x="40" y="178" class="mono" fill="{colors["muted"]}" font-size="8.5" letter-spacing="1.15">DAILY CONTRIBUTIONS</text>
  {''.join(month_labels)}
  <g class="mono" fill="{colors["faint"]}" font-size="7">
    <text x="57" y="219" text-anchor="end">MON</text>
    <text x="57" y="240" text-anchor="end">WED</text>
    <text x="57" y="261" text-anchor="end">FRI</text>
  </g>
  <g clip-path="url(#calendarClip)">
    {''.join(week_groups)}
    <rect x="68" y="198" width="54" height="82" fill="url(#scan)" class="calendar-scan"/>
  </g>

  <text x="40" y="304" class="mono" fill="{colors["faint"]}" font-size="7.5" letter-spacing="0.7">{first_label} — {last_label}</text>
  <g transform="translate(787 296)" class="mono">
    <text x="0" y="8" fill="{colors["muted"]}" font-size="7">LESS</text>
    <rect x="31" y="1" width="8" height="8" rx="4" fill="{colors["idle"]}"/>
    <rect x="44" y="1" width="8" height="8" rx="4" fill="{colors["levels"][0]}"/>
    <rect x="57" y="1" width="8" height="8" rx="4" fill="{colors["levels"][1]}"/>
    <rect x="70" y="1" width="8" height="8" rx="4" fill="{colors["levels"][2]}"/>
    <rect x="83" y="1" width="8" height="8" rx="4" fill="{colors["levels"][3]}"/>
    <text x="98" y="8" fill="{colors["muted"]}" font-size="7">MORE</text>
  </g>
</svg>
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, help="Use saved GraphQL JSON instead of calling GitHub")
    parser.add_argument("--output-dir", type=Path, default=Path("assets"))
    parser.add_argument("--username", default=USERNAME)
    args = parser.parse_args()

    if args.input:
        data = json.loads(args.input.read_text(encoding="utf-8"))
    else:
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            parser.error("GITHUB_TOKEN or GH_TOKEN is required unless --input is used")
        data = fetch_data(args.username, token)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    for theme in ("dark", "light"):
        output = args.output_dir / f"stats-{theme}.svg"
        output.write_text(build_dashboard(data, args.username, theme), encoding="utf-8", newline="\n")
        print(f"generated {output}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
