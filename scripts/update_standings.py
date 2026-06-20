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
        return 0, 0

    duration = score.get("duration")

    ft = score.get("fullTime") or {}
    rt = score.get("regularTime")
    et = score.get("extraTime")

    ft_h, ft_a = pair(ft)
    rt_h, rt_a = pair(rt) if rt else (ft_h, ft_a)
    et_h, et_a = pair(et) if et else (0, 0)

    if duration in ("EXTRA_TIME", "PENALTY_SHOOTOUT"):
        return rt_h + et_h, rt_a + et_a

    return ft_h, ft_a


# ✅ ✅ ✅ BULLETPROOF NORMALISATION (USA + others)
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

    # ✅ load inputs
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

    # ✅ ✅ MATCH FETCH (correct + stable)
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

    print("Fetched raw matches:", len(matches))

    # ✅ ✅ ✅ FIXED DEDUPE (CRITICAL)
    deduped = {}

    for m in matches:
        mid = m["id"]

        if mid not in deduped:
            deduped[mid] = m
        else:
            existing = deduped[mid]

            new_score = m.get("score", {}).get("fullTime")
            old_score = existing.get("score", {}).get("fullTime")

            if new_score and not old_score:
                deduped[mid] = m

    matches = list(deduped.values())

    print("After dedupe:", len(matches))

    # ✅ stats
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

        home = normalise(home_raw, name_map)
        away = normalise(away_raw, name_map)

        # ✅ include if either matters
        if home not in team_stats and away not in team_stats:
            continue

        ch, ca = counted_goals(m.get("score"))

        if home in team_stats:
            team_stats[home]["gf"] += ch
            team_stats[home]["ga"] += ca

        if away in team_stats:
            team_stats[away]["gf"] += ca
            team_stats[away]["ga"] += ch

        # ✅ count both finished + live
        if status in ("FINISHED", "IN_PLAY"):

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

    # ✅ GD
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
