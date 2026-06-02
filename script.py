import os
import json
from datetime import datetime
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from googleapiclient.discovery import build

# -----------------------------
# CONFIG
# -----------------------------

GENRES = {
    "soca": 120,
    "dancehall": 120,
    "afrobeats": 180,
    "bouyon": 180
}

BLACKLIST = [
    "mix", "dj", "megamix", "set", "live", "playlist",
    "intro", "snippet", "radio", "interview"
]

# -----------------------------
# INIT APIS
# -----------------------------

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"]
    )
)

youtube = build("youtube", "v3", developerKey=os.environ["YOUTUBE_API_KEY"])

# -----------------------------
# HELPERS
# -----------------------------

def clean(title):
    t = title.lower()
    return not any(x in t for x in BLACKLIST)


def yt_search(query):
    res = youtube.search().list(
        q=query,
        part="snippet",
        maxResults=1,
        type="video"
    ).execute()

    if not res["items"]:
        return None

    vid = res["items"][0]["id"]["videoId"]

    stats = youtube.videos().list(
        part="statistics",
        id=vid
    ).execute()

    if not stats["items"]:
        return None

    v = stats["items"][0]["statistics"]

    return {
        "id": vid,
        "views": int(v.get("viewCount", 0))
    }


def spotify_tracks(keyword):
    results = sp.search(q=keyword, type="track", limit=50)

    tracks = []

    for t in results["tracks"]["items"]:
        name = t["name"]
        artist = t["artists"][0]["name"]

        if not clean(name):
            continue

        tracks.append({
            "name": name,
            "artist": artist,
            "popularity": t["popularity"],
            "release_date": t["album"]["release_date"]
        })

    return tracks


def freshness(date):
    try:
        year = int(date.split("-")[0])
        age = 2026 - year

        if age <= 1:
            return 10
        elif age <= 2:
            return 7
        elif age <= 3:
            return 4
        return 1
    except:
        return 0


def load_snapshot():
    try:
        with open("data/snapshot.json", "r") as f:
            return json.load(f)
    except:
        return {}


def save(data):
    import os
    os.makedirs("data", exist_ok=True)

    with open("data/charts.json", "w") as f:
        json.dump(data, f, indent=2)

    with open("data/snapshot.json", "w") as f:
        json.dump(data, f, indent=2)


# -----------------------------
# ENGINE
# -----------------------------

def run():
    previous = load_snapshot()
    final = {}

    for genre in GENRES:

        tracks = spotify_tracks(genre)
        ranked = []

        for t in tracks:

            yt = yt_search(f"{t['artist']} {t['name']} official audio")

            if not yt:
                continue

            last = previous.get(t["name"], {}).get("views", yt["views"])
            growth = yt["views"] - last

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
                "score": score
            })

        ranked.sort(key=lambda x: x["score"], reverse=True)
        final[genre] = ranked[:50]

    save(final)
    build_html(final)


# -----------------------------
# HTML OUTPUT
# -----------------------------

def build_html(data):
    html = """
    <html>
    <head>
        <title>Carib50 Charts</title>
        <style>
            body { font-family: Arial; background: #111; color: white; }
            h2 { color: #ffcc00; }
            .song { padding: 10px; border-bottom: 1px solid #333; }
        </style>
    </head>
    <body>
        <h1>Carib50 Weekly Charts</h1>
    """

    for genre, songs in data.items():
        html += f"<h2>{genre.upper()}</h2>"

        for i, s in enumerate(songs, 1):
            html += f"""
            <div class="song">
                #{i} {s['artist']} - {s['name']}<br>
                Score: {int(s['score'])} | Growth: {s['weekly_growth']}
            </div>
            """

    html += "</body></html>"

    with open("data/index.html", "w") as f:
        f.write(html)


if __name__ == "__main__":
    run()
