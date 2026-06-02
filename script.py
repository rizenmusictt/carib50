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

MAX_TRACKS = 25
YT_LIMIT = 40

GENRE_RULES = {
    "soca": 4,
    "dancehall": 4,
    "afrobeats": 6,
    "bouyon": 6
}

PLAYLISTS = {
    "soca": [
        "37i9dQZF1DXdPec7aLTmlC"
    ],
    "dancehall": [
        "37i9dQZF1DXan38dNVDdl4"
    ],
    "afrobeats": [
        "37i9dQZF1DX10zKzsJ2jva"
    ],
    "bouyon": [
        # add curated playlist IDs here
    ]
}

BLACKLIST = [
    "mix", "dj", "megamix", "set", "live",
    "playlist", "intro", "snippet", "radio"
]

CACHE_FILE = "data/yt_cache.json"
SNAPSHOT_FILE = "data/snapshot.json"

# =========================
# INIT APIS
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
# LOAD DATA
# =========================

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
previous = load_json(SNAPSHOT_FILE)

yt_calls = 0

# =========================
# HELPERS
# =========================

def clean(title):
    t = title.lower()
    return not any(x in t for x in BLACKLIST)

def parse_date(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except:
        try:
            return datetime.strptime(d, "%Y-%m")
        except:
            return None

def is_recent(date_str, months):
    d = parse_date(date_str)
    if not d:
        return False
    cutoff = datetime.utcnow() - timedelta(days=months * 30)
    return d >= cutoff

# =========================
# BADGES
# =========================

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
# SPOTIFY PLAYLIST FETCH
# =========================

def get_tracks_from_playlist(pid, months):
    res = sp.playlist_items(pid)

    tracks = []

    for item in res["items"]:
        t = item.get("track")
        if not t:
            continue

        name = t["name"]
        artist = t["artists"][0]["name"]
        release = t["album"]["release_date"]

        if not clean(name):
            continue

        if not is_recent(release, months):
            continue

        tracks.append({
            "name": name,
            "artist": artist,
            "popularity": t["popularity"],
            "release_date": release,
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "badge": badge(release)
        })

    return tracks

# =========================
# YOUTUBE LOOKUP (SAFE)
# =========================

def yt_lookup(key, query):
    global yt_calls

    if yt_calls >= YT_LIMIT:
        return None

    if key in yt_cache:
        vid = yt_cache[key]
        try:
            stats = youtube.videos().list(
                part="statistics",
                id=vid
            ).execute()

            views = int(stats["items"][0]["statistics"].get("viewCount", 0))

            return {"video_id": vid, "views": views}

        except:
            pass

    try:
        search = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=1
        ).execute()

        if not search["items"]:
            return None

        vid = search["items"][0]["id"]["videoId"]

        stats = youtube.videos().list(
            part="statistics",
            id=vid
        ).execute()

        views = int(stats["items"][0]["statistics"].get("viewCount", 0))

        yt_cache[key] = vid
        yt_calls += 1

        return {"video_id": vid, "views": views}

    except HttpError:
        return None

# =========================
# ENGINE
# =========================

def run():
    final = {}

    for genre, months in GENRE_RULES.items():

        playlists = PLAYLISTS.get(genre, [])
        raw = []

        for pid in playlists:
            raw += get_tracks_from_playlist(pid, months)

        # dedupe
        seen = set()
        tracks = []

        for t in raw:
            key = f"{t['artist']} - {t['name']}"
            if key in seen:
                continue
            seen.add(key)
            tracks.append(t)

        tracks = sorted(tracks, key=lambda x: x["popularity"], reverse=True)[:MAX_TRACKS]

        ranked = []

        for t in tracks:

            key = f"{t['artist']} - {t['name']}"

            yt = yt_lookup(
                key,
                f"{t['artist']} {t['name']} official audio"
            )

            if yt:
                last = previous.get(key, {}).get("views", yt["views"])
                growth = yt["views"] - last

                score = (
                    growth * 0.7 +
                    t["popularity"] * 10 * 0.2 +
                    (10 if t["badge"] else 0)
                )

                mode = "full"
                views = yt["views"]

            else:
                score = t["popularity"] * 10
                growth = None
                views = None
                mode = "spotify_only"

            ranked.append({
                "name": t["name"],
                "artist": t["artist"],
                "image": t["image"],
                "release_date": t["release_date"],
                "badge": t["badge"],
                "youtube_views": views,
                "weekly_growth": growth,
                "score": score,
                "mode": mode
            })

        ranked.sort(key=lambda x: x["score"], reverse=True)
        final[genre] = ranked[:MAX_TRACKS]

    save_json(CACHE_FILE, yt_cache)
    save_json(SNAPSHOT_FILE, {})
    save_json("data/charts.json", final)

    build_html(final)

# =========================
# HTML
# =========================

def build_html(data):

    html = """
    <html>
    <head>
      <title>Carib25</title>
      <style>
        body { background:#0f0f0f; color:white; font-family:Arial; }
        h1 { color:#ffcc00; text-align:center; }
        .btn { margin:5px; padding:8px; cursor:pointer; }
        .song { display:flex; gap:10px; padding:10px; border-bottom:1px solid #222; align-items:center; }
        img { width:50px; height:50px; border-radius:4px; }
        .badge { font-size:11px; color:#ffcc00; }
        .score { margin-left:auto; color:#00ff99; }
      </style>
    </head>

    <body>
    <h1>Carib25</h1>

    <div style="text-align:center;">
      <button class="btn" onclick="show('soca')">Soca</button>
      <button class="btn" onclick="show('dancehall')">Dancehall</button>
      <button class="btn" onclick="show('afrobeats')">Afrobeats</button>
      <button class="btn" onclick="show('bouyon')">Bouyon</button>
    </div>

    <div id="app"></div>

    <script>
    const data = """ + json.dumps(data) + """;

    function show(g) {
      const app = document.getElementById("app");
      app.innerHTML = "";

      data[g].forEach((s, i) => {
        app.innerHTML += `
          <div class="song">
            <img src="${s.image}">
            <div>
              #${i+1} ${s.artist} - ${s.name}
              <div class="badge">${s.badge || ""}</div>
            </div>
            <div class="score">${Math.round(s.score)}</div>
          </div>
        `;
      });
    }

    show('soca');
    </script>

    </body>
    </html>
    """

    with open("data/index.html", "w") as f:
        f.write(html)

# =========================
# RUN
# =========================

if __name__ == "__main__":
    run()
