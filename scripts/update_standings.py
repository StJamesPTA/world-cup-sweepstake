#!/usr/bin/env python3

import os
import json
from datetime import datetime
import urllib.request

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


def http_get(path):
    url = BASE + path
    req = urllib.request.Request(url, headers=HEADERS)

    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def safe(x):
    return 0 if x is None else int(x)


def pair(d):
    if not d:
        return 0, 0
    return safe(d.get("home")), safe(d.get("away"))


# ✅ correct score extraction (handles RT vs FT)
def counted_goals(score):
    if not score:
        return None, None

    duration = score.get("duration")

    rt = score.get("regularTime") or {}
    et = score.get("extraTime") or {}
    ft = score.get("fullTime") or {}

    def valid(s):
        return (
            s and
            s.get("home") is not None and
            s.get("away") is not None
        )

    # ✅ Penalties: count ONLY regular time + extra time
    if duration == "PENALTY_SHOOTOUT":

        rt_h, rt_a = pair(rt) if valid(rt) else (0, 0)
        et_h, et_a = pair(et) if valid(et) else (0, 0)

        return (
            rt_h + et_h,
            rt_a + et_a
        )

    # ✅ Extra time: count regular time + extra time
    if duration == "EXTRA_TIME":

        rt_h, rt_a = pair(rt) if valid(rt) else (0, 0)
        et_h, et_a = pair(et) if valid(et) else (0, 0)

        return (
            rt_h + et_h,
            rt_a + et_a
        )

    # ✅ Normal games
    if valid(ft):
        return pair(ft)

    if valid(rt):
        return pair(rt)

    return None, None
    
# ✅ safe name mapping (NO "United" bug)
def normalise(name, name_map):
    if not name:
        return ""

    name = name.strip()
    lower = name.lower()

    if lower in ("united states", "united states of america", "usa", "us"):
        return "USA"

    if lower in ("korea republic", "south korea"):
        return "South Korea"

    if lower in ("ir iran", "iran"):
        return "Iran"

    if lower in ("czech republic", "czechia"):
        return "Czechia"

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

    # ✅ collect teams
    sweep_teams = set()
    for t in tickets:
        for team in t["teams"]:
            sweep_teams.add(team)

    print("Tracking teams:", sweep_teams)

    # ✅ ✅ ✅ FETCH ALL WORLD CUP MATCHES (NO FILTERS NEEDED)
    print("Fetching all World Cup matches...")

    data = http_get("/competitions/WC/matches")
    matches = data.get("matches", [])

    print("Total WC matches returned:", len(matches))

    team_stats = {
        t: {"team": t, "gf": 0, "ga": 0, "gd": 0, "played": 0}
        for t in sweep_teams
    }

    finished = []

    for m in matches:

        # ✅ ONLY finished matches
        if m.get("status") != "FINISHED":
            continue

        home_raw = m.get("homeTeam", {}).get("name")
        away_raw = m.get("awayTeam", {}).get("name")

        home = normalise(home_raw, name_map)
        away = normalise(away_raw, name_map)

        if home not in team_stats and away not in team_stats:
            continue

        ch, ca = counted_goals(m.get("score"))

        if ch is None or ca is None:
            continue

        if home in team_stats:
            team_stats[home]["gf"] += ch
            team_stats[home]["ga"] += ca
            team_stats[home]["played"] += 1

        if away in team_stats:
            team_stats[away]["gf"] += ca
            team_stats[away]["ga"] += ch
            team_stats[away]["played"] += 1

        finished.append({
            "home": home,
            "away": away,
            "score": f"{ch}-{ca}",
            "utcDate": m.get("utcDate")
        })

    # ✅ calculate GD
    for t in team_stats.values():
        t["gd"] = t["gf"] - t["ga"]

    finished.sort(key=lambda x: x["utcDate"], reverse=True)

    generated_at = datetime.utcnow().isoformat() + "Z"

    # ✅ output
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
