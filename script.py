import os
import json
from datetime import datetime, timedelta
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import urllib.request, urllib.parse

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

BLACKLIST = ["mix", "dj", "set", "live", "radio", "intro"]

# ==================================================
# STRICT GENRE LOCK SYSTEM
# ==================================================

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

# ==================================================
# SPOTIFY INIT
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
        return True  # SAFE fallback (prevents empty charts)
    return d >= datetime.utcnow() - timedelta(days=WINDOWS[genre] * 30)


def safe(t, key, fallback):
    return t.get(key) if t.get(key) is not None else fallback


# ==================================================
# YOUTUBE (SAFE OPTIONAL LAYER)
# ==================================================

def get_youtube_views(track, artist):
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
# SPOTIFY DATA
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
            "artist_id": t["artists"][0]["id"] if t["artists"] else "",
            "release": t["album"]["release_date"],
            "image": safe(t["album"]["images"][0] if t["album"]["images"] else {}, "url", ""),
            "preview": t.get("preview_url"),
            "spotify_url": t["external_urls"]["spotify"],
            "popularity": t.get("popularity", 0)
        })

    return out


# ==================================================
# LOAD HISTORY
# ==================================================

def load_history():
    if os.path.exists("data/history.json"):
        with open("data/history.json", "r") as f:
            return json.load(f)
    return {"charts": {}}


# ==================================================
# GENRE FILTERS (HARD LOCK SYSTEM)
# ==================================================

def genre_allowed(genre, t):

    blob = (t["artist"] + " " + t.get("artist_id", "")).lower()

    if genre == "soca":
        return not any(a.lower() in blob for a in ["bouyon"])

    if genre == "bouyon":
        return t.get("artist_id", "") in BOUYON_ARTIST_IDS

    if genre == "dancehall":
        return True

    if genre == "afrobeats":
        return True

    return False


# ==================================================
# SCORING ENGINE
# ==================================================

def score_track(t, history):

    yt_now = get_youtube_views(t["name"], t["artist"])
    yt_prev = history.get(t["id"], {}).get("views", yt_now or 0)

    yt_gain = max(0, (yt_now or 0) - yt_prev)

    yt_score = min(100, yt_gain / 1000)
    sp_score = t["popularity"]

    return (0.8 * yt_score) + (0.2 * sp_score), yt_now


# ==================================================
# CORE PROCESSOR
# ==================================================

def process_genre(genre, history):

    raw = []

    # --- discovery (minimal safe version) ---
    search = sp.search(q=genre, type="track", limit=50)
    for t in search["tracks"]["items"]:
        raw.append({
            "id": t["id"],
            "name": t["name"],
            "artist": t["artists"][0]["name"],
            "artist_id": t["artists"][0]["id"],
            "release": t["album"]["release_date"],
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "preview": t.get("preview_url"),
            "spotify_url": t["external_urls"]["spotify"],
            "popularity": t.get("popularity", 0)
        })

    # --- FILTER ---
    filtered = []
    for t in raw:

        if not clean(t["name"]):
            continue

        if not within_window(t["release"], genre):
            continue

        if not genre_allowed(genre, t):
            continue

        filtered.append(t)

    # --- SCORE ---
    scored = []
    for t in filtered:
        score, yt_now = score_track(t, history)

        t["score"] = score
        t["views"] = yt_now or 0
        scored.append(t)

    # --- SORT ---
    scored = sorted(scored, key=lambda x: x["score"], reverse=True)

    prev = history.get("charts", {}).get(genre, [])

    final = []
    swaps = 0

    prev_map = {x["id"]: x for x in prev}

    # --- SWAP LOGIC ---
    for t in scored:

        if len(final) < TARGET:
            final.append(t)
            continue

        lowest = min(final, key=lambda x: x["score"])

        if swaps < MAX_SWAPS and t["score"] > lowest["score"]:
            final.remove(lowest)
            final.append(t)
            swaps += 1

    # --- FILL TO 25 ---
    for t in scored:
        if len(final) >= TARGET:
            break
        if t not in final:
            final.append(t)

    # --- ANNOTATE ---
    output = []
    for i, t in enumerate(final):

        prev_entry = prev_map.get(t["id"])

        output.append({
            "rank": i + 1,
            "name": t["name"],
            "artist": t["artist"],
            "image": t["image"] or "https://placehold.co/300",
            "preview": t["preview"],
            "spotify_url": t["spotify_url"],
            "history": "New" if not prev_entry else f"Last Spot: #{prev_entry.get('rank', '?')}",
            "badge": "Fresh On De Scene" if not prev_entry else None
        })

    return output


# ==================================================
# RUN
# ==================================================

def run():

    history = load_history()
    new = {}

    for genre in ["soca", "dancehall", "afrobeats", "bouyon"]:
        print("Processing:", genre)
        new[genre] = process_genre(genre, history)

    os.makedirs("data", exist_ok=True)

    with open("data/charts.json", "w") as f:
        json.dump(new, f, indent=2)

    history["charts"] = new

    with open("data/history.json", "w") as f:
        json.dump(history, f, indent=2)


if __name__ == "__main__":
    run()
