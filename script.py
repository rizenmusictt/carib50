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

PLAYLIST_QUERIES = {
    "soca": ["2026 soca", "dj jel soca", "rizenmusic soca", "new soca", "top soca"],
    "dancehall": ["2026 dancehall", "new dancehall", "top dancehall"],
    "afrobeats": ["2026 afrobeats", "new afrobeats", "top afrobeats"],
    "bouyon": ["bouyon 2026", "new bouyon", "top bouyon"]
}

BLACKLIST = ["mix", "dj", "set", "live", "radio", "intro"]

# =========================
# ARTIST SIGNALS (OPTION B)
# =========================

SOCA_ARTISTS = [
    "Machel Montano", "Kes", "Nailah Blackman",
    "Voice", "Patrice Roberts", "Skinny Fabulous",
    "Farmer Nappy", "Lyrikal", "Olatunji"
]

DANCEHALL_ARTISTS = [
    "Vybz Kartel", "Popcaan", "Masicka",
    "Skillibeng", "Shenseea", "Alkaline",
    "Skeng", "Valiant", "RajahWild"
]

AFROBEATS_ARTISTS = [
    "Wizkid", "Burna Boy", "Davido",
    "Rema", "Asake", "Tems",
    "Ayra Starr", "Fireboy DML"
]

BOUYON_ARTISTS = [
    "1T1", "Miimii KDS", "Blackboy",
    "Ridge", "Quan", "Jessie",
    "Triple Kay", "Reo"
]

# =========================
# INIT
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
    return not any(x in name.lower() for x in BLACKLIST)

def parse_date(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except:
        try:
            return datetime.strptime(d, "%Y-%m")
        except:
            return None

def within_window(date_str, genre):
    d = parse_date(date_str)
    if not d:
        return False

    limit = 4 if genre in ["soca", "dancehall"] else 6
    return d >= datetime.utcnow() - timedelta(days=limit * 30)

# =========================
# CONFIDENCE SCORING (CRITICAL FIX)
# =========================

def score_genre(genre, artist, name):

    text = (artist + " " + name).lower()
    score = 0

    if genre == "soca":
        if any(a.lower() in text for a in SOCA_ARTISTS):
            score += 3

    if genre == "dancehall":
        if any(a.lower() in text for a in DANCEHALL_ARTISTS):
            score += 3

    if genre == "afrobeats":
        if any(a.lower() in text for a in AFROBEATS_ARTISTS):
            score += 3

    if genre == "bouyon":
        if any(a.lower() in text for a in BOUYON_ARTISTS):
            score += 3

    if genre in text:
        score += 1

    return score

# =========================
# DATA COLLECTION (NO HARD FILTERS HERE)
# =========================

def discover_playlists(query):
    try:
        res = sp.search(q=query, type="playlist", limit=5)
        return [p["id"] for p in res["playlists"]["items"]]
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
            "release": t["album"]["release_date"],
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "preview": t.get("preview_url"),
            "spotify_url": t["external_urls"]["spotify"],
            "popularity": t["popularity"]
        })

    return out

# =========================
# ENGINE
# =========================

def run():

    final = {}

    for genre in GENRE_RULES.keys():

        raw = []

        # 1. collect big pool
        for q in PLAYLIST_QUERIES[genre]:
            for pid in discover_playlists(q):
                raw += get_playlist_tracks(pid)

        # 2. dedupe
        seen = set()
        tracks = []

        for t in raw:
            key = f"{t['artist']} - {t['name']}"
            if key in seen:
                continue
            seen.add(key)
            tracks.append(t)

        # 3. apply strict release filter (NOW SAFE)
        tracks = [
            t for t in tracks
            if within_window(t["release"], genre)
        ]

        # 4. score (NO HARD REJECTION)
        scored = []

        for t in tracks:
            s = score_genre(genre, t["artist"], t["name"])

            if s < 2:
                continue

            t["score"] = t["popularity"] * 10 + s * 5
            scored.append(t)

        # 5. rank
        scored = sorted(scored, key=lambda x: x["score"], reverse=True)

        # 6. force 25 (only after full pipeline)
        scored = scored[:TARGET]

        # 7. format
        output = []

        for i, t in enumerate(scored):
            output.append({
                "rank": i + 1,
                "name": t["name"],
                "artist": t["artist"],
                "image": t["image"],
                "preview": t["preview"],
                "spotify_url": t["spotify_url"],
                "badge": "Fresh On De Scene" if i < 5 else None
            })

        final[genre] = output

    os.makedirs("data", exist_ok=True)

    with open("data/charts.json", "w") as f:
        json.dump(final, f, indent=2)

# =========================
# RUN
# =========================

if __name__ == "__main__":
    run()