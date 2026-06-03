import os
import json
import urllib.request
import urllib.parse
import re
from datetime import datetime, timedelta

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ==================================================
# CONFIG
# ==================================================

TARGET = 25
DATA_DIR = "data"
HISTORY_FILE = f"{DATA_DIR}/history.json"

GENRES = ["soca", "dancehall", "afrobeats", "bouyon"]

GENRE_WINDOWS = {
    "soca": 4,
    "dancehall": 4,
    "afrobeats": 6,
    "bouyon": 6
}

BLACKLIST = ["mix", "dj", "set", "live", "radio", "intro", "edit"]

SOCA_PLAYLISTS_PRIORITY = [
    "1FvkIodyAGsGy0MSMjSnAr",  # DJ Jel
    "3ugx3RitHXhWDiGTh7UUu2",  # DJ Jel
    "4brkOclzIpXABVHLnesMJt"   # Rizen Music
]

SOCA_ARTISTS = [
    "Machel Montano", "Kes", "Nailah Blackman",
    "Voice", "Patrice Roberts", "Skinny Fabulous"
]

DANCEHALL_ARTISTS = [
    "Vybz Kartel", "Popcaan", "Masicka",
    "Skillibeng", "Shenseea", "Alkaline", "Skeng", "Valiant"
]

AFROBEATS_ARTISTS = [
    "Wizkid", "Burna Boy", "Davido",
    "Rema", "Asake", "Tems", "Ayra Starr"
]

BOUYON_ARTISTS = [
    "1T1", "Miimii KDS", "Blackboy",
    "Ridge", "Quan", "Jessie", "Reo", "Triple Kay"
]

# ==================================================
# INIT
# ==================================================

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"]
    )
)

# ==================================================
# HISTORY
# ==================================================

def load_history():
    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f)
    except:
        return {}

def save_history(data):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(data, f, indent=2)

# ==================================================
# HELPERS
# ==================================================

def clean_track(name):
    n = name.lower()
    return not any(b in n for b in BLACKLIST)

def parse_date(d):
    if not d:
        return None
    try:
        if len(d) == 4:
            return datetime(int(d), 1, 1)
        if len(d) == 7:
            return datetime.strptime(d, "%Y-%m")
        return datetime.strptime(d, "%Y-%m-%d")
    except:
        return None

def within_window(date_str, genre):
    d = parse_date(date_str)
    if not d:
        return False
    limit = GENRE_WINDOWS[genre]
    return d >= datetime.utcnow() - timedelta(days=30 * limit)

def genre_match(genre, text):
    t = text.lower()

    if genre == "soca":
        return any(a.lower() in t for a in SOCA_ARTISTS)
    if genre == "dancehall":
        return any(a.lower() in t for a in DANCEHALL_ARTISTS)
    if genre == "afrobeats":
        return any(a.lower() in t for a in AFROBEATS_ARTISTS)
    if genre == "bouyon":
        return any(a.lower() in t for a in BOUYON_ARTISTS)

    return False

def yt_views(query, api_key):
    if not api_key:
        return None

    try:
        q = urllib.parse.quote(query)
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={q}&type=video&maxResults=1&key={api_key}"

        with urllib.request.urlopen(url, timeout=4) as r:
            data = json.loads(r.read().decode())

        items = data.get("items", [])
        if not items:
            return 0

        vid = items[0]["id"]["videoId"]

        stats_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={vid}&key={api_key}"

        with urllib.request.urlopen(stats_url, timeout=4) as r:
            stats = json.loads(r.read().decode())

        vids = stats.get("items", [])
        if vids:
            return int(vids[0]["statistics"].get("viewCount", 0))

        return 0

    except:
        return None

# ==================================================
# DISCOVERY
# ==================================================

def search_playlists(q):
    try:
        res = sp.search(q=q, type="playlist", limit=5)
        return [p["id"] for p in res["playlists"]["items"] if p]
    except:
        return []

def playlist_tracks(pid):
    try:
        res = sp.playlist_items(pid)
    except:
        return []

    out = []

    for item in res.get("items", []):
        t = item.get("track")
        if not t or not t.get("name"):
            continue

        name = t["name"]
        artist = t["artists"][0]["name"] if t["artists"] else "Unknown"

        if not clean_track(name):
            continue

        out.append({
            "id": t["id"],
            "name": name,
            "artist": artist,
            "artists_all": ", ".join([a["name"] for a in t["artists"]]),
            "release": t["album"]["release_date"],
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "spotify_url": t["external_urls"]["spotify"],
            "popularity": t["popularity"]
        })

    return out

# ==================================================
# CORE ENGINE
# ==================================================

def run():

    os.makedirs(DATA_DIR, exist_ok=True)

    history = load_history()
    yt_api = os.environ.get("YOUTUBE_API_KEY")

    final = {}

    for genre in GENRES:

        candidates = []

        # -------------------------
        # SOCA PRIORITY PIPELINE
        # -------------------------
        if genre == "soca":

            for pid in SOCA_PLAYLISTS_PRIORITY:
                candidates += playlist_tracks(pid)

            for q in ["2026 soca", "new soca", "soca hits"]:
                for pid in search_playlists(q):
                    candidates += playlist_tracks(pid)

        # -------------------------
        # BOUYON ARTIST-FIRST
        # -------------------------
        elif genre == "bouyon":

            for a in BOUYON_ARTISTS:
                try:
                    res = sp.search(q=f"artist:{a}", type="track", limit=25)
                    for t in res["tracks"]["items"]:
                        if t:
                            candidates.append({
                                "id": t["id"],
                                "name": t["name"],
                                "artist": t["artists"][0]["name"],
                                "artists_all": ", ".join([x["name"] for x in t["artists"]]),
                                "release": t["album"]["release_date"],
                                "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
                                "spotify_url": t["external_urls"]["spotify"],
                                "popularity": t["popularity"]
                            })
                except:
                    pass

        # -------------------------
        # OTHER GENRES
        # -------------------------
        else:
            for q in [f"2026 {genre}", f"new {genre}", f"top {genre}"]:
                for pid in search_playlists(q):
                    candidates += playlist_tracks(pid)

                try:
                    res = sp.search(q=q, type="track", limit=50)
                    for t in res["tracks"]["items"]:
                        if t:
                            candidates.append({
                                "id": t["id"],
                                "name": t["name"],
                                "artist": t["artists"][0]["name"],
                                "artists_all": ", ".join([x["name"] for x in t["artists"]]),
                                "release": t["album"]["release_date"],
                                "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
                                "spotify_url": t["external_urls"]["spotify"],
                                "popularity": t["popularity"]
                            })
                except:
                    pass

        # -------------------------
        # FILTERING
        # -------------------------
        filtered = []

        seen = set()

        for t in candidates:

            key = (t["artist"] + t["name"]).lower()
            if key in seen:
                continue
            seen.add(key)

            if not within_window(t["release"], genre):
                continue

            if not genre_match(genre, t["artist"] + " " + t["artists_all"]):
                continue

            filtered.append(t)

        # -------------------------
        # SCORING
        # -------------------------

        scored = []

        for t in filtered:

            yt = yt_views(f"{t['artist']} {t['name']} official", yt_api)

            prev = history.get(t["id"], {}).get("views", 0)

            growth = (yt - prev) if yt and prev else 0

            score = (
                (growth * 0.6 if growth else 0) +
                (yt or 0) * 0.25 +
                t["popularity"] * 1000 * 0.15
            )

            t["score"] = score
            t["views"] = yt or 0

            scored.append(t)

        # -------------------------
        # SORT + FILL
        # -------------------------

        scored.sort(key=lambda x: x["score"], reverse=True)

        while len(scored) < TARGET:
            break  # safe fallback (avoid fake data injection)

        top = scored[:TARGET]

        # -------------------------
        # HISTORY + MOVEMENT
        # -------------------------

        output = []
        new_history = {}

        for i, t in enumerate(top):

            prev_rank = history.get(t["id"], {}).get("rank")

            if prev_rank is None:
                movement = "Fresh On De Scene"
            else:
                diff = prev_rank - (i + 1)
                movement = "► Same" if diff == 0 else ("▲ +" + str(diff) if diff > 0 else "▼ " + str(diff))

            output.append({
                "rank": i + 1,
                "name": t["name"],
                "artist": t["artist"],
                "image": t["image"],
                "spotify_url": t["spotify_url"],
                "spotify_id": t["id"],
                "movement": movement,
                "badge": "Fresh On De Scene" if i < 5 else None
            })

            new_history[t["id"]] = {
                "rank": i + 1,
                "views": t["views"]
            }

        final[genre] = output

    save_history(new_history)

    with open("data/charts.json", "w") as f:
        json.dump(final, f, indent=2)

    print("CARIB25 UPDATED SUCCESSFULLY")

if __name__ == "__main__":
    run()