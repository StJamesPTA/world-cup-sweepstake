#!/usr/bin/env python3

import os
import json
from datetime import datetime, timedelta
import urllib.request
import urllib.parse

BASE = "https://api.football-data.org/v4"
TOKEN = os.environ.get("FOOTBALL_DATA_TOKEN")

if not TOKEN:
    raise SystemExit("Missing FOOTBALL_DATA_TOKEN")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TICKETS_PATH = os.path.join(ROOT, "data", "tickets.json")
MAP_PATH     = os.path.join(ROOT, "data", "team_name_map.json")

OUT_TEAMS  = os.path.join(ROOT, "standings", "teams.json")
OUT_RECENT = os.path.join(ROOT, "standings", "recent_finished.json")

HEADERS = {"X-Auth-Token": TOKEN}


def http_get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers=HEADERS)

    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def safe(x):
    return 0 if x is None else int(x)


def pair(d):
    if not d:
        return 0, 0
    return safe(d.get("home")), safe(d.get("away"))


def counted_goals(score):
    if not score:
        return None, None

    ft = score.get("fullTime") or {}
    rt = score.get("regularTime") or {}
    et = score.get("extraTime") or {}

    def valid(s):
        return s and s.get("home") is not None and s.get("away") is not None

    if valid(ft):
        h, a = pair(ft)
    elif valid(rt):
        h, a = pair(rt)
    elif valid(et):
        h, a = pair(et)
    else:
        return None, None

    return h, a


def normalise(name, name_map):
    if not name:
        return ""

    name = name.strip()
    lower = name.lower()

    if "united" in lower or lower in ("usa", "us", "u.s.a."):
        return "USA"

    return name_map.get(name, name)


def main():

    os.makedirs(os.path.join(ROOT, "standings"), exist_ok=True)

    with open(TICKETS_PATH) as f:
        tickets = json.load(f)

    try:
        with open(MAP_PATH) as f:
            name_map = json.load(f)
    except:
        name_map = {}

    sweep_teams = set()
    for t in tickets:
        for team in t["teams"]:
            sweep_teams.add(team)

    print("Tracking teams:", sweep_teams)

    # ✅ FETCH MATCHES
    matches = []

    start_date = datetime.utcnow() - timedelta(days=30)
    end_date   = datetime.utcnow() + timedelta(days=2)

    current = start_date

    while current <= end_date:

        chunk_end = min(current + timedelta(days=7), end_date)

        print("Fetching:", current.date(), "to", chunk_end.date())

        try:
            data = http_get("/matches", {
                "dateFrom": current.strftime("%Y-%m-%d"),
                "dateTo": chunk_end.strftime("%Y-%m-%d")
            })

            matches.extend(data.get("matches", []))

        except Exception as e:
            print("Chunk failed:", e)

        current = chunk_end + timedelta(days=1)

    print("\n=== TOTAL RAW MATCHES ===", len(matches))

    # ✅ DEBUG — show ALL USA matches RAW
    print("\n=== USA RAW MATCHES ===")
    for m in matches:
        home = m.get("homeTeam", {}).get("name")
        away = m.get("awayTeam", {}).get("name")

        if "United" in str(home) or "United" in str(away):
            print(json.dumps(m, indent=2))

    # ✅ dedupe only
    matches = {m["id"]: m for m in matches}.values()
    matches = list(matches)

    print("\n=== AFTER DEDUPE ===", len(matches))

    team_stats = {
        t: {"team": t, "gf": 0, "ga": 0, "gd": 0, "played": 0}
        for t in sweep_teams
    }

    finished = []

    # ✅ PROCESS MATCHES
    for m in matches:

        home_raw = m.get("homeTeam", {}).get("name")
        away_raw = m.get("awayTeam", {}).get("name")

        home = normalise(home_raw, name_map)
        away = normalise(away_raw, name_map)

        ch, ca = counted_goals(m.get("score"))

        # ✅ DEBUG USA processing
        if "United" in str(home_raw) or "United" in str(away_raw):
            print("\n=== USA PROCESS CHECK ===")
            print("RAW:", home_raw, "vs", away_raw)
            print("NORMALISED:", home, "vs", away)
            print("GOALS:", ch, "-", ca)

        if home not in team_stats and away not in team_stats:
            continue

        if ch is None and ca is None:
            continue

        if home in team_stats:
            team_stats[home]["gf"] += ch
            team_stats[home]["ga"] += ca

        if away in team_stats:
            team_stats[away]["gf"] += ca
            team_stats[away]["ga"] += ch

        finished.append({
            "home": home,
            "away": away,
            "score": f"{ch}-{ca}",
            "utcDate": m.get("utcDate")
        })

    for t in team_stats.values():
        t["gd"] = t["gf"] - t["ga"]

    finished.sort(key=lambda x: x["utcDate"], reverse=True)

    generated_at = datetime.utcnow().isoformat() + "Z"

    with open(OUT_TEAMS, "w") as f:
        json.dump({
            "generated_at": generated_at,
            "teams": list(team_stats.values())
        }, f, indent=2)

    with open(OUT_RECENT, "w") as f:
        json.dump({
            "generated_at": generated_at,
            "matches": finished[:5]
        }, f, indent=2)

    print("✅ DONE")


if __name__ == "__main__":
    main()
