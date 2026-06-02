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
    "soca": ["2026 soca", "top soca", "new soca"],
    "dancehall": ["2026 dancehall", "top dancehall", "new dancehall"],
    "afrobeats": ["2026 afrobeats", "top afrobeats", "new afrobeats"],
    "bouyon": ["bouyon 2026", "top bouyon", "new bouyon"]
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
# GENRE CONFIDENCE (ANTI-BLEED CORE FIX)
# =========================

GENRE_ARTISTS = {
    "soca": ["machel montano", "kes", "skinny fabulous", "voice", "nailah blackman"],
    "dancehall": ["vybz kartel", "popcaan", "shenseea", "masicka", "skillibeng"],
    "afrobeats": ["wizkid", "burna boy", "davido", "rema", "asake"],
    "bouyon": ["bunji garlin", "problem child", "mr killa", "screw", "lyrikal"]
}

def genre_confidence(genre, artist, name):
    text = (artist + " " + name).lower()

    score = 0
    if any(a in text for a in GENRE_ARTISTS.get(genre, [])):
        score += 3
    if genre in text:
        score += 1

    return score

# =========================
# PLAYLIST DISCOVERY
# =========================

def discover_playlists(query):
    try:
        res = sp.search(q=query, type="playlist", limit=5)
        return [p["id"] for p in res["playlists"]["items"]]
    except:
        return []

def get_playlist_tracks(pid, genre):
    try:
        res = sp.playlist_items(pid)
    except:
        return []

    tracks = []

    for item in res.get("items", []):
        t = item.get("track")
        if not t:
            continue

        name = t["name"]
        artist = t["artists"][0]["name"]

        if not clean(name):
            continue

        if not within_window(t["album"]["release_date"], genre):
            continue

        conf = genre_confidence(genre, artist, name)

        if conf < 2:
            continue

        tracks.append({
            "name": name,
            "artist": artist,
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "release": t["album"]["release_date"],
            "preview": t.get("preview_url"),
            "spotify_url": t["external_urls"]["spotify"],
            "popularity": t["popularity"],
            "confidence": conf
        })

    return tracks

# =========================
# ENGINE
# =========================

def run():

    final = {}

    for genre, _ in GENRE_RULES.items():

        raw = []

        # gather playlists dynamically
        for q in PLAYLIST_QUERIES[genre]:
            playlist_ids = discover_playlists(q)

            for pid in playlist_ids:
                raw += get_playlist_tracks(pid, genre)

        # dedupe
        seen = set()
        clean_tracks = []

        for t in raw:
            key = f"{t['artist']} - {t['name']}"
            if key in seen:
                continue
            seen.add(key)
            clean_tracks.append(t)

        # scoring (no display numbers exposed later)
        ranked = sorted(
            clean_tracks,
            key=lambda x: (x["popularity"] * 10 + x["confidence"] * 5),
            reverse=True
        )[:TARGET]

        # final formatting (NO exposed right-side numbers)
        output = []

        for i, t in enumerate(ranked):

            output.append({
                "rank": i + 1,
                "artist": t["artist"],
                "name": t["name"],
                "image": t["image"],
                "preview": t["preview"],
                "spotify_url": t["spotify_url"],
                "badge": "Fresh On De Scene" if t["confidence"] >= 3 else None
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
