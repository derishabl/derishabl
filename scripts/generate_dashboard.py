#!/usr/bin/env python3
"""Generate the custom GitHub profile telemetry SVGs.

The script uses GitHub's GraphQL API directly and has no third-party runtime
 dependencies. Pass --input to render previously downloaded GraphQL JSON.
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
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone
from html import escape
from pathlib import Path
from typing import Any

USERNAME = os.environ.get("PROFILE_USERNAME", "derishabl")
GRAPHQL_URL = "https://api.github.com/graphql"

QUERY = r"""
query ProfileTelemetry($login: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $login) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        totalContributions
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
    repositories(
      first: 100
      ownerAffiliations: OWNER
      isFork: false
      privacy: PUBLIC
    ) {
      nodes {
        name
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges {
            size
            node { name color }
          }
        }
      }
    }
  }
}
"""

PALETTES = {
    "dark": {
        "bg": "#0b0b11",
        "panel": "#101019",
        "border": "#302a36",
        "grid": "#312b38",
        "text": "#f6f2f6",
        "soft": "#d9d3dc",
        "muted": "#8b828f",
        "faint": "#625a67",
        "idle": "#302a38",
        "purple": "#d079d8",
        "purple_soft": "#82518a",
        "cyan": "#6dd6ff",
        "lime": "#b9f56a",
        "coral": "#ff8c78",
        "levels": ["#57395d", "#7c4a84", "#a45bad", "#d079d8"],
    },
    "light": {
        "bg": "#f7f3f6",
        "panel": "#f0eaf0",
        "border": "#d6cad8",
        "grid": "#d9cfda",
        "text": "#18131a",
        "soft": "#312a33",
        "muted": "#746a78",
        "faint": "#a095a3",
        "idle": "#ddd3df",
        "purple": "#9b3da8",
        "purple_soft": "#bd86c4",
        "cyan": "#167b9c",
        "lime": "#4d7c25",
        "coral": "#c45143",
        "levels": ["#d6b6da", "#bd85c4", "#a65ab1", "#8f309d"],
    },
}

LANGUAGE_ACCENTS = ["purple", "cyan", "lime", "coral"]


def iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def fetch_data(username: str, token: str) -> dict[str, Any]:
    today = datetime.now(timezone.utc).date()
    start = datetime.combine(today - timedelta(days=364), time.min, timezone.utc)
    end = datetime.combine(today, time.max, timezone.utc).replace(microsecond=0)
    payload = json.dumps(
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
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "derishabl-profile-telemetry",
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


def flatten_days(user: dict[str, Any]) -> list[dict[str, Any]]:
    calendar_data = user["contributionsCollection"]["contributionCalendar"]
    days = [day for week in calendar_data["weeks"] for day in week["contributionDays"]]
    days.sort(key=lambda item: item["date"])
    if not days:
        raise RuntimeError("GitHub returned an empty contribution calendar")
    return days


def streaks(days: list[dict[str, Any]]) -> tuple[int, int]:
    longest = run = 0
    for day in days:
        if day["contributionCount"] > 0:
            run += 1
            longest = max(longest, run)
        else:
            run = 0

    # An unfinished zero-contribution day does not end yesterday's streak.
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


def weekly_totals(user: dict[str, Any], first: str, last: str) -> list[dict[str, Any]]:
    weeks = []
    raw_weeks = user["contributionsCollection"]["contributionCalendar"]["weeks"]
    for week in raw_weeks:
        selected = [day for day in week["contributionDays"] if first <= day["date"] <= last]
        if selected:
            weeks.append(
                {
                    "firstDay": selected[0]["date"],
                    "lastDay": selected[-1]["date"],
                    "count": sum(day["contributionCount"] for day in selected),
                }
            )
    return weeks


def aggregate_languages(user: dict[str, Any]) -> list[dict[str, Any]]:
    totals: defaultdict[str, int] = defaultdict(int)
    for repo in user.get("repositories", {}).get("nodes", []):
        for edge in repo.get("languages", {}).get("edges", []):
            totals[edge["node"]["name"]] += int(edge["size"])
    grand_total = sum(totals.values())
    if grand_total == 0:
        return []
    ranked = sorted(totals.items(), key=lambda item: item[1], reverse=True)
    return [
        {"name": name, "size": size, "share": size / grand_total}
        for name, size in ranked[:4]
    ]


def contribution_level(count: int, maximum: int) -> int:
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


def polar(cx: float, cy: float, radius: float, degrees: float) -> tuple[float, float]:
    radians = math.radians(degrees)
    return cx + radius * math.cos(radians), cy + radius * math.sin(radians)


def fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def plural_days(value: int) -> str:
    return "DAY" if value == 1 else "DAYS"


def build_dashboard(data: dict[str, Any], username: str, theme: str) -> str:
    colors = PALETTES[theme]
    user = data["data"]["user"]
    days = flatten_days(user)
    weeks = weekly_totals(user, days[0]["date"], days[-1]["date"])
    languages = aggregate_languages(user)

    total = sum(day["contributionCount"] for day in days)
    active_days = sum(day["contributionCount"] > 0 for day in days)
    current_streak, longest_streak = streaks(days)
    peak = max(days, key=lambda item: item["contributionCount"])
    max_day = max((day["contributionCount"] for day in days), default=0)
    max_week = max((week["count"] for week in weeks), default=0)
    last_date = date.fromisoformat(days[-1]["date"])
    first_date = date.fromisoformat(days[0]["date"])

    # 365-day contribution orbit.
    cx, cy = 174.0, 218.0
    orbit_lines: list[str] = []
    month_ticks: list[str] = []
    seen_months: set[tuple[int, int]] = set()
    day_count = max(1, len(days))
    for index, day in enumerate(days):
        angle = -90 + (index / day_count) * 360
        count = int(day["contributionCount"])
        level = contribution_level(count, max_day)
        stroke = colors["idle"] if level < 0 else colors["levels"][level]
        width = 1.45 if level < 0 else 2.45
        opacity = 0.82 if level < 0 else 1
        if count == max_day and max_day > 0:
            stroke = colors["coral"]
            width = 3.2
        x1, y1 = polar(cx, cy, 103, angle)
        x2, y2 = polar(cx, cy, 114 if count else 111, angle)
        orbit_lines.append(
            f'<line x1="{fmt(x1)}" y1="{fmt(y1)}" x2="{fmt(x2)}" y2="{fmt(y2)}" '
            f'stroke="{stroke}" stroke-width="{width}" stroke-linecap="round" opacity="{opacity}"/>'
        )

        day_date = date.fromisoformat(day["date"])
        month_key = (day_date.year, day_date.month)
        if day_date.day <= 7 and month_key not in seen_months:
            seen_months.add(month_key)
            tx1, ty1 = polar(cx, cy, 119, angle)
            tx2, ty2 = polar(cx, cy, 124, angle)
            lx, ly = polar(cx, cy, 133, angle)
            month_ticks.append(
                f'<line x1="{fmt(tx1)}" y1="{fmt(ty1)}" x2="{fmt(tx2)}" y2="{fmt(ty2)}" '
                f'stroke="{colors["faint"]}" stroke-width="1"/>'
                f'<text x="{fmt(lx)}" y="{fmt(ly + 2.6)}" text-anchor="middle" '
                f'class="mono month-label" fill="{colors["muted"]}" font-size="7">'
                f'{calendar.month_abbr[day_date.month].upper()}</text>'
            )

    # Weekly signal graph.
    graph_left, graph_right = 370.0, 912.0
    graph_top, graph_bottom = 116.0, 231.0
    graph_width, graph_height = graph_right - graph_left, graph_bottom - graph_top
    points: list[tuple[float, float]] = []
    bars: list[str] = []
    denominator = max(1, len(weeks) - 1)
    bar_width = max(3.5, graph_width / max(1, len(weeks)) * 0.54)
    for index, week in enumerate(weeks):
        x = graph_left + (index / denominator) * graph_width
        ratio = week["count"] / max_week if max_week else 0
        y = graph_bottom - ratio * graph_height
        points.append((x, y))
        height = max(1.5, graph_bottom - y)
        bar_color = colors["coral"] if week["count"] == max_week and max_week else colors["purple"]
        bars.append(
            f'<rect class="week-bar" x="{fmt(x - bar_width / 2)}" y="{fmt(y)}" '
            f'width="{fmt(bar_width)}" height="{fmt(height)}" rx="{fmt(bar_width / 2)}" '
            f'fill="{bar_color}" opacity="{0.22 if week["count"] else 0.08}" '
            f'style="animation-delay:{index * 0.025:.3f}s"/>'
        )
    if not points:
        points = [(graph_left, graph_bottom), (graph_right, graph_bottom)]
    line_path = "M" + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in points)
    area_path = (
        f"M{fmt(graph_left)} {fmt(graph_bottom)} L"
        + " L".join(f"{fmt(x)} {fmt(y)}" for x, y in points)
        + f" L{fmt(graph_right)} {fmt(graph_bottom)} Z"
    )

    # Month labels under the weekly graph.
    month_labels: list[str] = []
    cursor = date(first_date.year, first_date.month, 1)
    if cursor < first_date:
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    total_span = max(1, (last_date - first_date).days)
    while cursor <= last_date:
        ratio = (cursor - first_date).days / total_span
        x = graph_left + ratio * graph_width
        month_labels.append(
            f'<text x="{fmt(x)}" y="252" text-anchor="middle" class="mono" '
            f'fill="{colors["muted"]}" font-size="7.5" letter-spacing="0.6">'
            f'{calendar.month_abbr[cursor.month].upper()}</text>'
        )
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)

    # Pulse the latest non-zero week.
    latest_active_index = next(
        (index for index in range(len(weeks) - 1, -1, -1) if weeks[index]["count"] > 0),
        len(weeks) - 1,
    )
    pulse_x, pulse_y = points[max(0, latest_active_index)]

    # Language channel segments and legend.
    language_segments: list[str] = []
    language_legend: list[str] = []
    language_left, language_width = 220.0, 692.0
    offset = 0.0
    if not languages:
        language_segments.append(
            f'<rect x="{language_left}" y="372" width="{language_width}" height="9" rx="4.5" fill="{colors["idle"]}"/>'
        )
        language_legend.append(
            f'<text x="{language_left}" y="405" class="mono" fill="{colors["muted"]}" font-size="8">NO LANGUAGE DATA</text>'
        )
    else:
        for index, language in enumerate(languages):
            segment_width = language_width * language["share"]
            accent_name = LANGUAGE_ACCENTS[index % len(LANGUAGE_ACCENTS)]
            accent = colors[accent_name]
            language_segments.append(
                f'<rect x="{fmt(language_left + offset)}" y="372" width="{fmt(max(1.5, segment_width))}" '
                f'height="9" rx="4.5" fill="{accent}"/>'
            )
            legend_x = language_left + index * 148
            percent = round(language["share"] * 100)
            language_legend.append(
                f'<circle cx="{fmt(legend_x + 3)}" cy="402" r="2.5" fill="{accent}"/>'
                f'<text x="{fmt(legend_x + 12)}" y="405" class="mono" fill="{colors["muted"]}" '
                f'font-size="8" letter-spacing="0.55">{escape(language["name"].upper())} {percent}%</text>'
            )
            offset += segment_width

    activity_percent = round(active_days / len(days) * 100) if days else 0
    peak_date = date.fromisoformat(peak["date"])
    latest_label = last_date.strftime("%d %b %Y").upper()
    peak_label = peak_date.strftime("%d %b %Y").upper()
    if current_streak:
        current_end_index = len(days) - 1
        if days[current_end_index]["contributionCount"] == 0:
            current_end_index -= 1
        current_end = date.fromisoformat(days[current_end_index]["date"])
        current_subtitle = f"ENDING {current_end.strftime('%d %b').upper()}"
    else:
        current_subtitle = "NO ACTIVE RUN"
    theme_description = "dark" if theme == "dark" else "light"

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="960" height="430" viewBox="0 0 960 430" role="img" aria-labelledby="title desc">
  <title id="title">{escape(username)} — Signal Atlas</title>
  <desc id="desc">A {theme_description} animated dashboard: {total} contributions, {active_days} active days, a {current_streak}-day current run, and a {longest_streak}-day longest run in the last year.</desc>
  <!-- Generated from GitHub data through {days[-1]["date"]}. Do not edit by hand. -->

  <defs>
    <linearGradient id="edge" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{colors["purple"]}"/>
      <stop offset="0.52" stop-color="{colors["cyan"]}"/>
      <stop offset="1" stop-color="{colors["lime"]}"/>
    </linearGradient>
    <linearGradient id="area" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{colors["purple"]}" stop-opacity="0.22"/>
      <stop offset="1" stop-color="{colors["purple"]}" stop-opacity="0"/>
    </linearGradient>
    <linearGradient id="scanner" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0" stop-color="{colors["cyan"]}" stop-opacity="0"/>
      <stop offset="0.5" stop-color="{colors["cyan"]}" stop-opacity="0.16"/>
      <stop offset="1" stop-color="{colors["cyan"]}" stop-opacity="0"/>
    </linearGradient>
    <filter id="glow" x="-200%" y="-200%" width="500%" height="500%">
      <feGaussianBlur stdDeviation="2.4" result="blur"/>
      <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <clipPath id="graphClip"><rect x="360" y="108" width="562" height="127" rx="8"/></clipPath>
    <clipPath id="languageClip"><rect x="220" y="372" width="692" height="9" rx="4.5"/></clipPath>
  </defs>

  <style>
    .mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", monospace; font-variant-numeric: tabular-nums; }}
    .sans {{ font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; font-variant-numeric: tabular-nums; }}
    .orbit-scan {{ transform-origin: 174px 218px; animation: orbit 13s linear infinite; }}
    .signal-line {{ stroke-dasharray: 1500; stroke-dashoffset: 1500; animation: draw 2.5s cubic-bezier(.22,.8,.3,1) forwards; }}
    .signal-area {{ opacity: 0; animation: reveal .9s .45s ease-out forwards; }}
    .week-bar {{ transform-box: fill-box; transform-origin: center bottom; animation: rise .65s cubic-bezier(.2,.8,.3,1) both; }}
    .scanner {{ animation: scan 7.5s 1.4s ease-in-out infinite; }}
    .live-pulse {{ transform-box: fill-box; transform-origin: center; animation: pulse 2.4s ease-in-out infinite; }}
    .metric {{ opacity: 0; transform: translateY(5px); animation: metric-in .55s ease-out forwards; }}
    .language-shimmer {{ animation: shimmer 5.5s 1.8s ease-in-out infinite; }}
    @keyframes orbit {{ to {{ transform: rotate(360deg); }} }}
    @keyframes draw {{ to {{ stroke-dashoffset: 0; }} }}
    @keyframes reveal {{ to {{ opacity: 1; }} }}
    @keyframes rise {{ from {{ transform: scaleY(0); opacity: 0; }} }}
    @keyframes scan {{ 0% {{ transform: translateX(-85px); opacity: 0; }} 12%, 82% {{ opacity: 1; }} 100% {{ transform: translateX(625px); opacity: 0; }} }}
    @keyframes pulse {{ 0%, 100% {{ opacity: .28; transform: scale(.72); }} 50% {{ opacity: 1; transform: scale(1.22); }} }}
    @keyframes metric-in {{ to {{ opacity: 1; transform: translateY(0); }} }}
    @keyframes shimmer {{ 0%, 72%, 100% {{ transform: translateX(-120px); opacity: 0; }} 82% {{ opacity: .5; }} 94% {{ transform: translateX(760px); opacity: 0; }} }}
    @media (prefers-reduced-motion: reduce) {{
      .orbit-scan, .signal-line, .signal-area, .week-bar, .scanner, .live-pulse, .metric, .language-shimmer {{ animation: none; opacity: 1; transform: none; stroke-dashoffset: 0; }}
    }}
  </style>

  <rect width="960" height="430" rx="26" fill="{colors["bg"]}"/>
  <rect x="0.75" y="0.75" width="958.5" height="428.5" rx="25.25" fill="none" stroke="{colors["border"]}" stroke-width="1.5"/>
  <path d="M26 1H274" stroke="url(#edge)" stroke-width="2"/>

  <!-- Header pixel mark -->
  <g transform="translate(39 24) scale(.72)" fill="{colors["purple"]}">
    <rect x="0" y="0" width="9" height="9" rx="1"/><rect x="36" y="0" width="9" height="9" rx="1"/>
    <rect x="9" y="9" width="9" height="9" rx="1"/><rect x="18" y="9" width="9" height="9" rx="1"/><rect x="27" y="9" width="9" height="9" rx="1"/>
    <rect x="0" y="18" width="9" height="9" rx="1"/><rect x="18" y="18" width="9" height="9" rx="1"/><rect x="36" y="18" width="9" height="9" rx="1"/>
    <rect x="9" y="27" width="9" height="9" rx="1"/><rect x="18" y="27" width="9" height="9" rx="1"/><rect x="27" y="27" width="9" height="9" rx="1"/>
    <rect x="9" y="36" width="9" height="9" rx="1"/><rect x="27" y="36" width="9" height="9" rx="1"/>
  </g>
  <text x="86" y="38" class="mono" fill="{colors["text"]}" font-size="13" font-weight="700" letter-spacing="2.2">SIGNAL ATLAS</text>
  <text x="86" y="56" class="mono" fill="{colors["muted"]}" font-size="8.5" letter-spacing="1.1">365 DAYS OF BUILD ACTIVITY / FOLDED INTO ONE ORBIT</text>
  <g transform="translate(778 29)">
    <circle cx="3" cy="8" r="3" fill="{colors["lime"]}"/>
    <circle cx="3" cy="8" r="7" fill="{colors["lime"]}" opacity=".12" class="live-pulse"/>
    <text x="16" y="11" class="mono" fill="{colors["muted"]}" font-size="8.5" letter-spacing="1">SYNC / {latest_label}</text>
  </g>
  <path d="M35 77H925" stroke="{colors["grid"]}"/>

  <!-- Year orbit -->
  <text x="48" y="102" class="mono" fill="{colors["muted"]}" font-size="8.5" letter-spacing="1.4">YEAR ORBIT / 365D</text>
  <circle cx="174" cy="218" r="95" fill="{colors["panel"]}" stroke="{colors["grid"]}"/>
  <circle cx="174" cy="218" r="78" fill="none" stroke="{colors["grid"]}" stroke-width=".8" stroke-dasharray="2 7"/>
  <g class="orbit-days">{''.join(orbit_lines)}</g>
  <g>{''.join(month_ticks)}</g>
  <circle cx="174" cy="218" r="121" fill="none" stroke="url(#edge)" stroke-width="2" stroke-linecap="round" stroke-dasharray="58 702" class="orbit-scan" filter="url(#glow)"/>
  <text x="174" y="211" text-anchor="middle" class="sans" fill="{colors["text"]}" font-size="42" font-weight="760" letter-spacing="-1.5">{total:,}</text>
  <text x="174" y="232" text-anchor="middle" class="mono" fill="{colors["muted"]}" font-size="8" letter-spacing="1.2">CONTRIBUTIONS</text>
  <circle cx="137" cy="251" r="2" fill="{colors["purple"]}"/>
  <text x="145" y="254" class="mono" fill="{colors["soft"]}" font-size="9">{active_days} ACTIVE DAYS</text>

  <!-- Weekly signal -->
  <text x="370" y="100" class="mono" fill="{colors["muted"]}" font-size="8.5" letter-spacing="1.35">WEEKLY SIGNAL / LINEAR SCALE</text>
  <text x="912" y="100" text-anchor="end" class="mono" fill="{colors["faint"]}" font-size="8">PEAK {max_week} / WEEK</text>
  <g class="mono" fill="{colors["faint"]}" font-size="7">
    <text x="360" y="119" text-anchor="end">{max_week}</text>
    <text x="360" y="177" text-anchor="end">{round(max_week / 2)}</text>
    <text x="360" y="234" text-anchor="end">0</text>
  </g>
  <g stroke="{colors["grid"]}" stroke-width=".8" stroke-dasharray="2 6">
    <path d="M370 116H912"/><path d="M370 173.5H912"/><path d="M370 231H912"/>
  </g>
  <g clip-path="url(#graphClip)">
    <path d="{area_path}" fill="url(#area)" class="signal-area"/>
    {''.join(bars)}
    <rect x="360" y="108" width="72" height="127" fill="url(#scanner)" class="scanner"/>
    <path d="{line_path}" fill="none" stroke="{colors["purple"]}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round" class="signal-line" filter="url(#glow)"/>
  </g>
  <circle cx="{fmt(pulse_x)}" cy="{fmt(pulse_y)}" r="10" fill="{colors["cyan"]}" opacity=".1" class="live-pulse"/>
  <circle cx="{fmt(pulse_x)}" cy="{fmt(pulse_y)}" r="3" fill="{colors["bg"]}" stroke="{colors["cyan"]}" stroke-width="1.5" filter="url(#glow)"/>
  {''.join(month_labels)}

  <!-- Metric strip -->
  <path d="M354 267H924" stroke="{colors["grid"]}"/>
  <g class="metric">
    <text x="370" y="285" class="mono" fill="{colors["muted"]}" font-size="8" letter-spacing="1">CURRENT RUN</text>
    <text x="370" y="316" class="sans" fill="{colors["cyan"]}" font-size="27" font-weight="720">{current_streak}<tspan dx="7" class="mono" fill="{colors["soft"]}" font-size="9" font-weight="400">{plural_days(current_streak)}</tspan></text>
    <text x="370" y="335" class="mono" fill="{colors["faint"]}" font-size="7.5">{current_subtitle}</text>
  </g>
  <path d="M505 278V337" stroke="{colors["grid"]}"/>
  <g class="metric" style="animation-delay:.12s">
    <text x="522" y="285" class="mono" fill="{colors["muted"]}" font-size="8" letter-spacing="1">LONGEST RUN</text>
    <text x="522" y="316" class="sans" fill="{colors["purple"]}" font-size="27" font-weight="720">{longest_streak}<tspan dx="7" class="mono" fill="{colors["soft"]}" font-size="9" font-weight="400">{plural_days(longest_streak)}</tspan></text>
    <text x="522" y="335" class="mono" fill="{colors["faint"]}" font-size="7.5">IN ROLLING YEAR</text>
  </g>
  <path d="M657 278V337" stroke="{colors["grid"]}"/>
  <g class="metric" style="animation-delay:.24s">
    <text x="674" y="285" class="mono" fill="{colors["muted"]}" font-size="8" letter-spacing="1">ACTIVE DAYS</text>
    <text x="674" y="316" class="sans" fill="{colors["lime"]}" font-size="27" font-weight="720">{active_days}<tspan dx="7" class="mono" fill="{colors["soft"]}" font-size="9" font-weight="400">/ {len(days)}</tspan></text>
    <text x="674" y="335" class="mono" fill="{colors["faint"]}" font-size="7.5">{activity_percent}% OF THE ORBIT</text>
  </g>
  <path d="M809 278V337" stroke="{colors["grid"]}"/>
  <g class="metric" style="animation-delay:.36s">
    <text x="826" y="285" class="mono" fill="{colors["muted"]}" font-size="8" letter-spacing="1">PEAK SIGNAL</text>
    <text x="826" y="316" class="sans" fill="{colors["coral"]}" font-size="27" font-weight="720">{peak["contributionCount"]}</text>
    <text x="826" y="335" class="mono" fill="{colors["faint"]}" font-size="7.5">{peak_label}</text>
  </g>

  <!-- Language telemetry -->
  <path d="M35 351H925" stroke="{colors["grid"]}"/>
  <text x="48" y="379" class="mono" fill="{colors["muted"]}" font-size="8.5" letter-spacing="1.25">LANGUAGE CHANNELS</text>
  <text x="48" y="402" class="mono" fill="{colors["faint"]}" font-size="7.5">PUBLIC REPOSITORIES</text>
  <g clip-path="url(#languageClip)">{''.join(language_segments)}
    <rect x="220" y="369" width="95" height="15" fill="url(#scanner)" class="language-shimmer"/>
  </g>
  {''.join(language_legend)}
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
