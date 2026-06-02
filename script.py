import os
import json
from datetime import datetime, timedelta

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# =========================
# CONFIG
# =========================

TARGET = 25

GENRE_RULES = {
    "soca": 4,
    "dancehall": 4,
    "afrobeats": 6,
    "bouyon": 6
}

# 🎯 dynamic playlist search queries
PLAYLIST_QUERIES = {
    "soca": [
        "2026 soca", "top soca", "new soca", "soca hits", "soca party"
    ],
    "dancehall": [
        "2026 dancehall", "top dancehall", "new dancehall", "dancehall hits"
    ],
    "afrobeats": [
        "2026 afrobeats", "top afrobeats", "new afrobeats", "afrobeats hits"
    ],
    "bouyon": [
        "bouyon 2026", "top bouyon", "new bouyon", "caribbean bouyon"
    ]
}

BLACKLIST = ["mix", "dj", "set", "live", "radio", "intro"]

# =========================
# INIT SPOTIFY
# =========================

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"]
    )
)

# =========================
# HELPERS
# =========================

def clean(name):
    name = name.lower()
    return not any(x in name for x in BLACKLIST)

def parse_date(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except:
        try:
            return datetime.strptime(d, "%Y-%m")
        except:
            return None

def recent(date_str, months):
    d = parse_date(date_str)
    if not d:
        return False
    return d >= datetime.utcnow() - timedelta(days=months * 30)

def badge(date_str):
    d = parse_date(date_str)
    if not d:
        return None
    age = (datetime.utcnow() - d).days
    if age <= 30:
        return "Fresh On De Scene"
    if age <= 60:
        return "New Heat"
    return None

# =========================
# PLAYLIST DISCOVERY ENGINE
# =========================

def discover_playlists(query):
    try:
        res = sp.search(q=query, type="playlist", limit=5)
        return [p["id"] for p in res["playlists"]["items"] if p]
    except:
        return []

def get_playlist_tracks(pid):
    try:
        res = sp.playlist_items(pid)
    except:
        return []

    out = []

    for item in res.get("items", []):
        t = item.get("track")
        if not t:
            continue

        name = t["name"]
        artist = t["artists"][0]["name"]

        if not clean(name):
            continue

        out.append({
            "name": name,
            "artist": artist,
            "popularity": t["popularity"],
            "release": t["album"]["release_date"],
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "badge": badge(t["album"]["release_date"])
        })

    return out

# =========================
# ENGINE
# =========================

def run():

    final = {}

    for genre, months in GENRE_RULES.items():

        raw = []

        # -----------------------
        # 1. DISCOVER PLAYLISTS
        # -----------------------
        for q in PLAYLIST_QUERIES.get(genre, []):
            playlist_ids = discover_playlists(q)

            for pid in playlist_ids:
                raw += get_playlist_tracks(pid)

        # -----------------------
        # 2. DEDUPE
        # -----------------------
        seen = set()
        tracks = []

        for t in raw:
            key = f"{t['artist']} - {t['name']}"
            if key in seen:
                continue
            seen.add(key)
            tracks.append(t)

        # -----------------------
        # 3. FILTER + SCORE
        # -----------------------
        ranked = []

        for t in tracks:

            if not clean(t["name"]):
                continue

            score = t["popularity"] * 10

            ranked.append({
                "name": t["name"],
                "artist": t["artist"],
                "image": t["image"],
                "badge": t["badge"],
                "score": score
            })

        ranked = sorted(ranked, key=lambda x: x["score"], reverse=True)

        # -----------------------
        # 4. FORCE 25 OUTPUT
        # -----------------------
        if len(ranked) < TARGET:
            ranked = (ranked * (TARGET // len(ranked) + 1))[:TARGET]
        else:
            ranked = ranked[:TARGET]

        # add ranks
        for i, r in enumerate(ranked):
            r["rank"] = i + 1

        final[genre] = ranked

    # -----------------------
    # SAVE
    # -----------------------
    os.makedirs("data", exist_ok=True)
    with open("data/charts.json", "w") as f:
        json.dump(final, f, indent=2)

# =========================
# RUN
# =========================

if __name__ == "__main__":
    run()
