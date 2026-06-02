import os
import json
from datetime import datetime, timedelta

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

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

# 🎯 GENRE ANCHOR ARTISTS (CORE FIX)
GENRE_ARTISTS = {
    "soca": [
        "Machel Montano", "Kes", "Nailah Blackman", "Skinny Fabulous",
        "Voice", "Fay-Ann Lyons", "Problem Child", "Lyrikal",
        "Marzville", "Olatunji", "Lil Rick"
    ],
    "dancehall": [
        "Vybz Kartel", "Popcaan", "Shenseea", "Masicka",
        "Skillibeng", "Alkaline", "Busy Signal", "Valiant",
        "Nigy Boy", "Spice"
    ],
    "afrobeats": [
        "Wizkid", "Davido", "Burna Boy", "Rema",
        "Fireboy DML", "Asake", "Tems", "Omah Lay",
        "Ayra Starr", "Tiwa Savage"
    ],
    "bouyon": [
        "1T1", "Miimii KDS", "Ridge", "Asa Bantan",
        "Dirty Dawg Pudaz", "Litleboy", "Signal Band",
        "Trilla-G", "Quan", "WCK"
    ]
}

PLAYLISTS = {
    "soca": ["37i9dQZF1DX0b1h0H4H1vJ"],
    "dancehall": ["37i9dQZF1DXan38dNVDdl4"],
    "afrobeats": ["37i9dQZF1DX10zKzsJ2jva"],
    "bouyon": []
}

BLACKLIST = ["mix", "dj", "set", "live", "intro", "radio"]

CACHE_FILE = "data/yt_cache.json"
SNAPSHOT_FILE = "data/snapshot.json"

# =========================
# INIT
# =========================

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"]
    )
)

youtube = build(
    "youtube",
    "v3",
    developerKey=os.environ["YOUTUBE_API_KEY"]
)

# =========================
# STATE
# =========================

def load_json(p):
    try:
        return json.load(open(p))
    except:
        return {}

def save_json(p, d):
    os.makedirs("data", exist_ok=True)
    with open(p, "w") as f:
        json.dump(d, f, indent=2)

yt_cache = load_json(CACHE_FILE)
previous = load_json(SNAPSHOT_FILE)

yt_calls = 0

# =========================
# HELPERS
# =========================

def clean(t):
    t = t.lower()
    return not any(x in t for x in BLACKLIST)

def parse(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except:
        try:
            return datetime.strptime(d, "%Y-%m")
        except:
            return None

def recent(d, months):
    d = parse(d)
    if not d:
        return False
    return d >= datetime.utcnow() - timedelta(days=months * 30)

def badge(d):
    d = parse(d)
    if not d:
        return None
    age = (datetime.utcnow() - d).days
    if age <= 30:
        return "Fresh On De Scene"
    if age <= 60:
        return "New Heat"
    return None

# =========================
# 🎯 GENRE SCORING BOOST (NEW CORE)
# =========================

def genre_boost(genre, text):
    text = text.lower()

    for artist in GENRE_ARTISTS.get(genre, []):
        if artist.lower() in text:
            return 1.5  # strong boost

    return 1.0

# =========================
# SPOTIFY
# =========================

def get_playlist_tracks(pid, months):
    try:
        res = sp.playlist_items(pid)
    except:
        return []

    out = []

    for i in res.get("items", []):
        t = i.get("track")
        if not t:
            continue

        name = t["name"]
        artist = t["artists"][0]["name"]
        release = t["album"]["release_date"]

        if not clean(name):
            continue

        if not recent(release, months):
            continue

        out.append({
            "name": name,
            "artist": artist,
            "popularity": t["popularity"],
            "release": release,
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "badge": badge(release)
        })

    return out

def fallback(genre, months):
    try:
        res = sp.search(q=f"{genre} music", type="track", limit=50)
    except:
        return []

    out = []

    for t in res["tracks"]["items"]:

        text = t["name"] + " " + t["artists"][0]["name"]

        if not clean(t["name"]):
            continue

        if not recent(t["album"]["release_date"], months):
            continue

        out.append({
            "name": t["name"],
            "artist": t["artists"][0]["name"],
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

    snapshot = load_json(SNAPSHOT_FILE)
    final = {}

    for genre, months in GENRE_RULES.items():

        playlists = PLAYLISTS.get(genre, [])
        raw = []

        for pid in playlists:
            raw += get_playlist_tracks(pid, months)

        if not raw:
            raw = fallback(genre, months)

        # dedupe
        seen = set()
        tracks = []

        for t in raw:
            key = f"{t['artist']} - {t['name']}"
            if key in seen:
                continue
            seen.add(key)

            # 🎯 APPLY GENRE BOOST
            boost = genre_boost(genre, key)

            t["score_base"] = t["popularity"] * boost

            tracks.append(t)

        # sort with boost
        tracks = sorted(tracks, key=lambda x: x["score_base"], reverse=True)

        tracks = tracks[:TARGET]

        ranked = []

        for i, t in enumerate(tracks):

            key = f"{t['artist']} - {t['name']}"

            prev_rank = snapshot.get(genre, {}).get(key)

            if prev_rank:
                if prev_rank > i + 1:
                    movement = "up"
                elif prev_rank < i + 1:
                    movement = "down"
                else:
                    movement = "same"
            else:
                movement = "new"

            ranked.append({
                "name": t["name"],
                "artist": t["artist"],
                "image": t["image"],
                "badge": t["badge"],
                "rank": i + 1,
                "movement": movement,
                "score": t["score_base"]
            })

        final[genre] = ranked

    # snapshot update
    new_snapshot = {}

    for g, songs in final.items():
        new_snapshot[g] = {}
        for s in songs:
            new_snapshot[g][f"{s['artist']} - {s['name']}"] = s["rank"]

    save_json(CACHE_FILE, yt_cache)
    save_json(SNAPSHOT_FILE, new_snapshot)
    save_json("data/charts.json", final)

# =========================
# RUN
# =========================

if __name__ == "__main__":
    run()
