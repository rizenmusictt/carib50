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
    "soca": ["2026 soca", "top soca", "new soca", "soca hits"],
    "dancehall": ["2026 dancehall", "top dancehall", "new dancehall"],
    "afrobeats": ["2026 afrobeats", "top afrobeats", "new afrobeats"],
    "bouyon": ["bouyon 2026", "new bouyon", "top bouyon"]
}

# -------------------------
# FIXED GENRE IDENTITY MAPS
# -------------------------

SOCA_ARTISTS = [
    "Machel Montano", "Kes", "Skinny Fabulous",
    "Voice", "Nailah Blackman", "Fay-Ann Lyons"
]

DANCEHALL_ARTISTS = [
    "Vybz Kartel", "Popcaan", "Shenseea", "Masicka",
    "Skillibeng", "Alkaline", "Spice"
]

AFROBEATS_ARTISTS = [
    "Wizkid", "Burna Boy", "Davido", "Rema",
    "Asake", "Tems", "Ayra Starr"
]

BOUYON_ARTISTS = [
    "1T1", "Miimii KDS", "Blackboy", "Ridge",
    "Quan", "Jessie", "Reo", "Triple Kay"
]

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
# STRICT GENRE CLASSIFIER
# =========================

def genre_match(genre, artist, name):

    text = (artist + " " + name).lower()

    if genre == "soca":
        return any(a.lower() in text for a in SOCA_ARTISTS)

    if genre == "dancehall":
        return any(a.lower() in text for a in DANCEHALL_ARTISTS)

    if genre == "afrobeats":
        return any(a.lower() in text for a in AFROBEATS_ARTISTS)

    if genre == "bouyon":
        return any(a.lower() in text for a in BOUYON_ARTISTS)

    return False

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

        if not genre_match(genre, artist, name):
            continue

        tracks.append({
            "name": name,
            "artist": artist,
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "release": t["album"]["release_date"],
            "preview": t.get("preview_url"),
            "spotify_url": t["external_urls"]["spotify"],
            "popularity": t["popularity"]
        })

    return tracks

# =========================
# RESCUE SYSTEM (ENSURES 25)
# =========================

def rescue_fill(genre, tracks):

    if len(tracks) >= TARGET:
        return tracks[:TARGET]

    try:
        res = sp.search(q=f"{genre} music", type="track", limit=50)

        for t in res["tracks"]["items"]:

            if len(tracks) >= TARGET:
                break

            artist = t["artists"][0]["name"]
            name = t["name"]

            if not clean(name):
                continue

            if not genre_match(genre, artist, name):
                continue

            tracks.append({
                "name": name,
                "artist": artist,
                "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
                "release": t["album"]["release_date"],
                "preview": t.get("preview_url"),
                "spotify_url": t["external_urls"]["spotify"],
                "popularity": t["popularity"]
            })

    except:
        pass

    return tracks[:TARGET]

# =========================
# ENGINE
# =========================

def run():

    final = {}

    for genre in GENRE_RULES.keys():

        raw = []

        # 1. playlist discovery
        for q in PLAYLIST_QUERIES[genre]:
            for pid in discover_playlists(q):
                raw += get_playlist_tracks(pid, genre)

        # 2. dedupe
        seen = set()
        clean_tracks = []

        for t in raw:
            key = f"{t['artist']} - {t['name']}"
            if key in seen:
                continue
            seen.add(key)
            clean_tracks.append(t)

        # 3. rank
        ranked = sorted(clean_tracks, key=lambda x: x["popularity"], reverse=True)

        # 4. enforce 25
        ranked = rescue_fill(genre, ranked)

        # 5. format output (NO NUMBERS ON UI SIDE ISSUES)
        output = []

        for i, t in enumerate(ranked):

            output.append({
                "rank": i + 1,
                "name": t["name"],
                "artist": t["artist"],
                "image": t["image"],
                "preview": t.get("preview"),
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
