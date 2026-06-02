import os
import json
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# -----------------------------
# CONFIG
# -----------------------------

GENRES = ["soca", "dancehall", "afrobeats", "bouyon"]

BLACKLIST = [
    "mix", "dj", "megamix", "set", "live", "playlist",
    "intro", "snippet", "radio", "interview"
]

CACHE_FILE = "data/yt_cache.json"
SNAPSHOT_FILE = "data/snapshot.json"

# -----------------------------
# INIT APIS
# -----------------------------

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

# -----------------------------
# LOAD / SAVE HELPERS
# -----------------------------

def load_json(path):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return {}

def save_json(path, data):
    os.makedirs("data", exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2)

yt_cache = load_json(CACHE_FILE)
previous_snapshot = load_json(SNAPSHOT_FILE)

# -----------------------------
# FILTERS
# -----------------------------

def is_valid(title):
    t = title.lower()
    return not any(x in t for x in BLACKLIST)

# -----------------------------
# SPOTIFY DISCOVERY (ONLY)
# -----------------------------

def get_tracks(keyword):
    results = sp.search(q=keyword, type="track", limit=30)

    tracks = []

    for t in results["tracks"]["items"]:
        name = t["name"]
        artist = t["artists"][0]["name"]

        if not is_valid(name):
            continue

        tracks.append({
            "name": name,
            "artist": artist,
            "popularity": t["popularity"],
            "release_date": t["album"]["release_date"]
        })

    # keep top 10 most relevant (reduces YouTube usage)
    tracks.sort(key=lambda x: x["popularity"], reverse=True)
    return tracks[:10]

# -----------------------------
# YOUTUBE LOOKUP (SAFE + CACHED)
# -----------------------------

yt_calls = 0
YT_LIMIT = 40

def get_youtube_data(song_key, query):
    global yt_calls

    # 1. check cache first
    if song_key in yt_cache:
        vid = yt_cache[song_key]

        try:
            stats = youtube.videos().list(
                part="statistics",
                id=vid
            ).execute()

            views = int(stats["items"][0]["statistics"].get("viewCount", 0))

            return {
                "video_id": vid,
                "views": views
            }

        except:
            pass  # fallback to re-search if cache broken

    # 2. quota guard
    if yt_calls >= YT_LIMIT:
        return None  # switch to Spotify-only mode

    try:
        search = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=1
        ).execute()

        if not search["items"]:
            return None

        video_id = search["items"][0]["id"]["videoId"]

        stats = youtube.videos().list(
            part="statistics",
            id=video_id
        ).execute()

        views = int(stats["items"][0]["statistics"].get("viewCount", 0))

        yt_cache[song_key] = video_id
        yt_calls += 1

        return {
            "video_id": video_id,
            "views": views
        }

    except HttpError:
        # quota exceeded → switch off YouTube completely
        return None

# -----------------------------
# SCORING HELPERS
# -----------------------------

def freshness(date):
    try:
        year = int(date.split("-")[0])
        age = 2026 - year
        return max(0, 10 - age * 3)
    except:
        return 0

# -----------------------------
# MAIN ENGINE
# -----------------------------

def run():

    final = {}
    global yt_calls

    for genre in GENRES:

        tracks = get_tracks(genre)
        ranked = []

        for t in tracks:

            key = f"{t['artist']} - {t['name']}"
            yt = get_youtube_data(
                key,
                f"{t['artist']} {t['name']} official audio"
            )

            # fallback mode: Spotify-only ranking
            if yt is None:
                score = (
                    t["popularity"] * 10 +
                    freshness(t["release_date"])
                )

                ranked.append({
                    "name": t["name"],
                    "artist": t["artist"],
                    "youtube_views": None,
                    "weekly_growth": None,
                    "spotify_popularity": t["popularity"],
                    "score": score,
                    "mode": "spotify_only"
                })

                continue

            # normal mode (Spotify + YouTube)
            last_views = previous_snapshot.get(key, {}).get("views", yt["views"])
            growth = yt["views"] - last_views

            score = (
                growth * 0.7 +
                t["popularity"] * 10 * 0.2 +
                freshness(t["release_date"]) * 0.1
            )

            ranked.append({
                "name": t["name"],
                "artist": t["artist"],
                "youtube_views": yt["views"],
                "weekly_growth": growth,
                "spotify_popularity": t["popularity"],
                "score": score,
                "mode": "full"
            })

        ranked.sort(key=lambda x: x["score"], reverse=True)
        final[genre] = ranked[:50]

    # save cache + outputs
    save_json(CACHE_FILE, yt_cache)
    save_json(SNAPSHOT_FILE, {
        f"{t['artist']} - {t['name']}": {
            "views": t.get("youtube_views", 0)
        }
        for g in final.values()
        for t in g
    })

    save_json("data/charts.json", final)

    build_html(final)

# -----------------------------
# HTML OUTPUT
# -----------------------------

def build_html(data):

    html = """
    <html>
    <head>
      <title>Carib50</title>
      <style>
        body { background:#0f0f0f; color:white; font-family:Arial; }
        h2 { color:#ffcc00; margin-top:30px; }
        .song { padding:8px; border-bottom:1px solid #222; }
        .tag { font-size:12px; color:#888; }
      </style>
    </head>
    <body>
    <h1>Carib50 Weekly Charts</h1>
    """

    for genre, songs in data.items():
        html += f"<h2>{genre.upper()}</h2>"

        for i, s in enumerate(songs, 1):

            mode = "🎧 Spotify Only" if s.get("mode") == "spotify_only" else "▶ YouTube"

            html += f"""
            <div class="song">
              #{i} {s['artist']} - {s['name']}
              <div class="tag">
                Score: {int(s['score'])} | {mode}
              </div>
            </div>
            """

    html += "</body></html>"

    with open("data/index.html", "w") as f:
        f.write(html)

# -----------------------------
# RUN
# -----------------------------

if __name__ == "__main__":
    run()
