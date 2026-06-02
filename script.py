import os
import json
from datetime import datetime, timedelta
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# -------------------------
# CONFIG
# -------------------------

GENRE_RULES = {
    "soca": 4,
    "dancehall": 4,
    "afrobeats": 6,
    "bouyon": 6
}

BLACKLIST = ["mix", "dj", "megamix", "set", "live", "playlist", "intro", "snippet"]

MAX_TRACKS = 25
YT_LIMIT = 40

CACHE_FILE = "data/yt_cache.json"
SNAPSHOT_FILE = "data/snapshot.json"

# -------------------------
# INIT APIS
# -------------------------

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

# -------------------------
# HELPERS
# -------------------------

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

def clean(title):
    t = title.lower()
    return not any(x in t for x in BLACKLIST)

def parse_date(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except:
        try:
            return datetime.strptime(date_str, "%Y-%m")
        except:
            return None

def is_recent(date_str, months):
    d = parse_date(date_str)
    if not d:
        return False
    cutoff = datetime.utcnow() - timedelta(days=months * 30)
    return d >= cutoff

# -------------------------
# SPOTIFY DISCOVERY
# -------------------------

def get_tracks(keyword, months):
    results = sp.search(q=keyword, type="track", limit=50)

    tracks = []

    for t in results["tracks"]["items"]:
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
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else ""
        })

    tracks.sort(key=lambda x: x["popularity"], reverse=True)
    return tracks[:MAX_TRACKS]

# -------------------------
# YOUTUBE LOOKUP (SAFE)
# -------------------------

def yt_lookup(key, query):
    global yt_calls

    if key in yt_cache:
        vid = yt_cache[key]
        try:
            stats = youtube.videos().list(part="statistics", id=vid).execute()
            views = int(stats["items"][0]["statistics"].get("viewCount", 0))
            return {"video_id": vid, "views": views}
        except:
            pass

    if yt_calls >= YT_LIMIT:
        return None

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

# -------------------------
# SCORING
# -------------------------

def freshness(date_str):
    d = parse_date(date_str)
    if not d:
        return 0
    age_years = (datetime.utcnow() - d).days / 365
    return max(0, 10 - age_years * 3)

# -------------------------
# MAIN ENGINE
# -------------------------

def run():
    final = {}

    for genre, months in GENRE_RULES.items():

        tracks = get_tracks(genre, months)
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
                    freshness(t["release_date"]) * 0.1
                )

                mode = "full"
                views = yt["views"]

            else:
                score = t["popularity"] * 10 + freshness(t["release_date"])
                growth = None
                views = None
                mode = "spotify_only"

            ranked.append({
                "name": t["name"],
                "artist": t["artist"],
                "image": t["image"],
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

# -------------------------
# HTML OUTPUT
# -------------------------

def build_html(data):

    html = """
    <html>
    <head>
      <title>Carib25</title>
      <style>
        body { background:#0f0f0f; color:white; font-family:Arial; }
        .btn { margin:5px; padding:8px; cursor:pointer; }
        .song { display:flex; gap:10px; padding:10px; border-bottom:1px solid #222; }
        img { width:50px; height:50px; }
        .score { color:#00ff99; }
      </style>
    </head>
    <body>

    <h1>Carib25</h1>

    <div>
      <button class="btn" onclick="show('soca')">Soca</button>
      <button class="btn" onclick="show('dancehall')">Dancehall</button>
      <button class="btn" onclick="show('afrobeats')">Afrobeats</button>
      <button class="btn" onclick="show('bouyon')">Bouyon</button>
    </div>

    <div id="app"></div>

    <script>
    const data = """ + json.dumps(data) + """;

    function show(g) {
      const app = document.getElementById('app');
      app.innerHTML = '';

      data[g].forEach((s, i) => {
        app.innerHTML += `
          <div class="song">
            <img src="${s.image}">
            <div>
              #${i+1} ${s.artist} - ${s.name}<br>
              <span class="score">${Math.round(s.score)}</span>
            </div>
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

# -------------------------
# RUN
# -------------------------

if __name__ == "__main__":
    run()
