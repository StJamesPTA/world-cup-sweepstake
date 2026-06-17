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

HEADERS = {
    "X-Auth-Token": TOKEN
}


# ✅ HTTP helper
def http_get(path, params=None):
    url = BASE + path
    if params:
        url += "?" + urllib.parse.urlencode(params)

    req = urllib.request.Request(url, headers=HEADERS)

    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


# ✅ helpers
def safe(x):
    return 0 if x is None else int(x)


def pair(d):
    if not d:
        return 0, 0
    return safe(d.get("home")), safe(d.get("away"))


def counted_goals(score):
    if not score:
        return 0, 0

    duration = score.get("duration")

    ft = score.get("fullTime") or {}
    rt = score.get("regularTime")
    et = score.get("extraTime")

    ft_h, ft_a = pair(ft)
    rt_h, rt_a = pair(rt) if rt else (ft_h, ft_a)
    et_h, et_a = pair(et) if et else (0, 0)

    # ✅ include ET, exclude penalties
    if duration in ("EXTRA_TIME", "PENALTY_SHOOTOUT"):
        return rt_h + et_h, rt_a + et_a

    return ft_h, ft_a


# ✅ ✅ MAIN FUNCTION
def main():

    os.makedirs(os.path.join(ROOT, "standings"), exist_ok=True)

    # ✅ load inputs
    with open(TICKETS_PATH) as f:
        tickets = json.load(f)

    try:
        with open(MAP_PATH) as f:
            name_map = json.load(f)
    except:
        name_map = {}

    # ✅ collect teams from tickets
    sweep_teams = set()
    for t in tickets:
        for team in t["teams"]:
            sweep_teams.add(team)

    print("Tracking teams:", sweep_teams)

    # ✅ fetch matches (date range)

    date_from = "2026-06-01"
    date_to   = "2026-07-31"

    data = http_get("/matches", {
        "dateFrom": date_from,
        "dateTo": date_to
    })

    matches = data.get("matches", [])
    print("Matches returned:", len(matches))

    # ✅ init stats
    team_stats = {
        t: {"team": t, "gf": 0, "ga": 0, "gd": 0, "played": 0}
        for t in sweep_teams
    }

    finished = []

    # ✅ process matches
    for m in matches:

        status = m.get("status")
        if status in ("SCHEDULED", "TIMED"):
            continue

        home_raw = m.get("homeTeam", {}).get("name")
        away_raw = m.get("awayTeam", {}).get("name")

        # ✅ map names if needed
        home = name_map.get(home_raw, home_raw)
        away = name_map.get(away_raw, away_raw)

        # ✅ include if either team matters
        if home not in team_stats and away not in team_stats:
            continue

        ch, ca = counted_goals(m.get("score"))

        # ✅ update stats
        if home in team_stats:
            team_stats[home]["gf"] += ch
            team_stats[home]["ga"] += ca

        if away in team_stats:
            team_stats[away]["gf"] += ca
            team_stats[away]["ga"] += ch

        # ✅ finished matches
        if status == "FINISHED":

            if home in team_stats:
                team_stats[home]["played"] += 1
            if away in team_stats:
                team_stats[away]["played"] += 1

            finished.append({
                "home": home,
                "away": away,
                "score": f"{ch}-{ca}",
                "utcDate": m.get("utcDate")
            })

    # ✅ compute GD
    for t in team_stats.values():
        t["gd"] = t["gf"] - t["ga"]

    # ✅ sort recent
    finished.sort(key=lambda x: x["utcDate"], reverse=True)

    # ✅ ✅ TIMESTAMP FIX
    generated_at = datetime.utcnow().isoformat() + "Z"

    # ✅ ✅ WRITE OUTPUT (CORRECTLY PLACED ✅)
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


# ✅ ✅ ENTRY POINT
if __name__ == "__main__":
    main()
