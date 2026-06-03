import os
import json
from datetime import datetime, timedelta

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ==================================================
# CONFIG
# ==================================================

TARGET = 25
MAX_SWAPS = 5

WINDOWS = {
    "soca": 4,
    "dancehall": 4,
    "afrobeats": 6,
    "bouyon": 6
}

# ==================================================
# DATA SOURCES
# ==================================================

SOCA_PLAYLISTS = [
    "1FvkIodyAGsGy0MSMjSnAr",
    "3ugx3RitHXhWDiGTh7UUu2",
    "4brkOclzIpXABVHLnesMJt"
]

SOCA_EXTRA_PLAYLISTS = [
    "5kCjHM5mKmf7axrWecdkuz",
    "1IfKtQ9akjh4oO0W3bQ11D",
    "11unAoPberMGyLiE5yVPER"
]

BOUYON_PLAYLISTS = [
    "4aZHZCd0KPtoxAGR8SPqtj",
    "1DCCA3EVmxIXA4f68vaINS",
    "27J36rBvTtvAcgeJMoqUrN"
]

BOUYON_ARTIST_IDS = [
    "2eIEzwxBh1vDSSbUfZkeLL",
    "3Oc7o3kzzpLium0YxZPVri",
    "29DEO5ubNTmLbFSEZDP2we",
    "0mpZpEH8VcL0tYoGLhR8sd",
    "390GislU2lqdtKcuFMIvjK",
    "6bEej9F7Pkkto542i9mran",
    "1DpASCaDoS1AAKFHb6uldr",
    "5Zjgfa0fywmVbwc5dPlScR",
    "1DaLT7Mgy04h833FKXKGO0"
]

SOCA_ARTISTS = [
    "Machel Montano", "Kes", "Nailah Blackman",
    "Voice", "Patrice Roberts", "Skinny Fabulous"
]

DANCEHALL_ARTISTS = [
    "Vybz Kartel", "Popcaan", "Masicka",
    "Skillibeng", "Shenseea", "Alkaline"
]

AFROBEATS_ARTISTS = [
    "Wizkid", "Burna Boy", "Davido",
    "Rema", "Asake", "Tems", "Ayra Starr"
]

BLACKLIST = ["mix", "dj", "set", "live", "radio", "intro"]

# ==================================================
# INIT SPOTIFY
# ==================================================

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"]
    )
)

# ==================================================
# HELPERS
# ==================================================

def clean(name):
    return not any(x in name.lower() for x in BLACKLIST)


def parse_date(d):
    if not d:
        return None
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
    return d >= datetime.utcnow() - timedelta(days=WINDOWS[genre] * 30)


def normalize(x, max_val=100):
    return min(max_val, x / 1000)


# ==================================================
# YOUTUBE (OPTIONAL FALLBACK SAFE)
# ==================================================

def get_youtube_views(track, artist):
    import urllib.request, urllib.parse

    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return None

    try:
        q = urllib.parse.quote(f"{artist} {track} official audio")
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={q}&type=video&maxResults=1&key={api_key}"

        with urllib.request.urlopen(url, timeout=4) as r:
            res = json.loads(r.read().decode())

        items = res.get("items", [])
        if not items:
            return 0

        vid = items[0]["id"]["videoId"]

        stats_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={vid}&key={api_key}"

        with urllib.request.urlopen(stats_url, timeout=4) as r:
            stats = json.loads(r.read().decode())

        return int(stats["items"][0]["statistics"].get("viewCount", 0))

    except:
        return None


# ==================================================
# SPOTIFY DISCOVERY
# ==================================================

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

        out.append({
            "id": t["id"],
            "name": t["name"],
            "artist": t["artists"][0]["name"],
            "release": t["album"]["release_date"],
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "spotify_url": t["external_urls"]["spotify"],
            "popularity": t["popularity"]
        })

    return out


def artist_tracks(artist_id):
    out = []
    try:
        albums = sp.artist_albums(artist_id, limit=20)
        for a in albums["items"]:
            tracks = sp.album_tracks(a["id"])
            for t in tracks["items"]:
                out.append({
                    "id": t["id"],
                    "name": t["name"],
                    "artist": t["artists"][0]["name"],
                    "release": a["release_date"],
                    "image": "",
                    "spotify_url": "",
                    "popularity": 0
                })
    except:
        pass
    return out


# ==================================================
# LOAD HISTORY
# ==================================================

def load_json(path):
    if os.path.exists(path):
        with open(path, "r") as f:
            return json.load(f)
    return {}


# ==================================================
# MAIN ENGINE
# ==================================================

def process_genre(genre, history):

    candidates = []
    swaps = 0

    # --------------------------
    # DISCOVERY LAYER
    # --------------------------

    if genre == "soca":
        for pid in SOCA_PLAYLISTS + SOCA_EXTRA_PLAYLISTS:
            candidates += playlist_tracks(pid)

    elif genre == "bouyon":
        for pid in BOUYON_PLAYLISTS:
            candidates += playlist_tracks(pid)

        for aid in BOUYON_ARTIST_IDS:
            candidates += artist_tracks(aid)

    else:
        # simplified for now (dancehall + afrobeats stable)
        results = sp.search(q=genre, type="track", limit=50)
        for t in results["tracks"]["items"]:
            candidates.append({
                "id": t["id"],
                "name": t["name"],
                "artist": t["artists"][0]["name"],
                "release": t["album"]["release_date"],
                "image": t["album"]["images"][0]["url"],
                "spotify_url": t["external_urls"]["spotify"],
                "popularity": t["popularity"]
            })

    # --------------------------
    # FILTERING
    # --------------------------

    filtered = []

    for t in candidates:

        if not clean(t["name"]):
            continue

        if not within_window(t["release"], genre):
            continue

        filtered.append(t)

    # --------------------------
    # SCORING
    # --------------------------

    scored = []

    for t in filtered:

        yt_now = get_youtube_views(t["name"], t["artist"])
        yt_prev = history.get(t["id"], {}).get("views", yt_now or 0)

        yt_gain = max(0, (yt_now or 0) - yt_prev)

        yt_score = normalize(yt_gain)
        sp_score = t["popularity"]

        score = (0.8 * yt_score) + (0.2 * sp_score)

        t["score"] = score
        t["current_views"] = yt_now

        scored.append(t)

    # --------------------------
    # LOAD PREVIOUS TOP 25
    # --------------------------

    prev = history.get("charts", {}).get(genre, [])

    combined = prev + scored
    combined = sorted(combined, key=lambda x: x["score"], reverse=True)

    # --------------------------
    # SWAP LOGIC (MAX 5)
    # --------------------------

    final = prev.copy()

    for t in combined:

        if swaps >= MAX_SWAPS:
            break

        if any(x["id"] == t["id"] for x in final):
            continue

        if len(final) < TARGET:
            final.append(t)
            swaps += 1
        else:
            lowest = min(final, key=lambda x: x["score"])

            if t["score"] > lowest["score"]:
                final.remove(lowest)
                final.append(t)
                swaps += 1

    # --------------------------
    # ENSURE 25
    # --------------------------

    for t in combined:
        if len(final) >= TARGET:
            break
        if t not in final:
            final.append(t)

    # --------------------------
    # FRESH TAG
    # --------------------------

    prev_ids = {x["id"] for x in prev}

    for t in final:
        if t["id"] not in prev_ids:
            t["badge"] = "Fresh On De Scene"

    return final


# ==================================================
# RUN
# ==================================================

def run():

    history = load_json("data/history.json")
    old_charts = history.get("charts", {})

    new_charts = {}

    for genre in ["soca", "dancehall", "afrobeats", "bouyon"]:
        print(f"Processing {genre}...")
        new_charts[genre] = process_genre(genre, history)

    os.makedirs("data", exist_ok=True)

    # save charts
    with open("data/charts.json", "w") as f:
        json.dump(new_charts, f, indent=2)

    # update history
    history["charts"] = new_charts

    with open("data/history.json", "w") as f:
        json.dump(history, f, indent=2)


if __name__ == "__main__":
    run()
