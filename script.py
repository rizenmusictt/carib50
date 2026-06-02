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

TARGET = 25

GENRE_RULES = {
    "soca": 4,
    "dancehall": 4,
    "afrobeats": 6,
    "bouyon": 6
}

PLAYLISTS = {
    "soca": ["37i9dQZF1DX0b1h0H4H1vJ"],
    "dancehall": ["37i9dQZF1DXan38dNVDdl4"],
    "afrobeats": ["37i9dQZF1DX10zKzsJ2jva"],
    "bouyon": []
}

BLACKLIST = ["mix", "dj", "set", "live", "intro", "radio"]

CACHE_FILE = "data/yt_cache.json"
SNAPSHOT_FILE = "data/snapshot.json"

# =========================
# INIT
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
# STATE
# =========================

def load_json(p):
    try:
        return json.load(open(p))
    except:
        return {}

def save_json(p, d):
    os.makedirs("data", exist_ok=True)
    with open(p, "w") as f:
        json.dump(d, f, indent=2)

yt_cache = load_json(CACHE_FILE)
previous = load_json(SNAPSHOT_FILE)

yt_calls = 0

# =========================
# HELPERS
# =========================

def clean(t):
    t = t.lower()
    return not any(x in t for x in BLACKLIST)

def parse(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except:
        try:
            return datetime.strptime(d, "%Y-%m")
        except:
            return None

def recent(d, months):
    d = parse(d)
    if not d:
        return False
    return d >= datetime.utcnow() - timedelta(days=months * 30)

def badge(d):
    d = parse(d)
    if not d:
        return None
    age = (datetime.utcnow() - d).days
    if age <= 30:
        return "Fresh On De Scene"
    if age <= 60:
        return "New Heat"
    return None

# =========================
# SPOTIFY
# =========================

def get_playlist_tracks(pid, months):
    try:
        res = sp.playlist_items(pid)
    except:
        return []

    out = []

    for i in res.get("items", []):
        t = i.get("track")
        if not t:
            continue

        name = t["name"]
        artist = t["artists"][0]["name"]
        release = t["album"]["release_date"]

        if not clean(name):
            continue

        if not recent(release, months):
            continue

        out.append({
            "name": name,
            "artist": artist,
            "popularity": t["popularity"],
            "release": release,
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "badge": badge(release)
        })

    return out

def fallback(genre, months):
    try:
        res = sp.search(q=genre, type="track", limit=30)
    except:
        return []

    out = []

    for t in res["tracks"]["items"]:
        if not clean(t["name"]):
            continue

        if not recent(t["album"]["release_date"], months):
            continue

        out.append({
            "name": t["name"],
            "artist": t["artists"][0]["name"],
            "popularity": t["popularity"],
            "release": t["album"]["release_date"],
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "badge": badge(t["album"]["release_date"])
        })

    return out

# =========================
# YOUTUBE (hidden)
# =========================

def yt_lookup(key, query):
    global yt_calls

    if yt_calls >= 40:
        return None

    if key in yt_cache:
        return None

    try:
        search = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=1
        ).execute()

        if not search.get("items"):
            return None

        vid = search["items"][0]["id"]["videoId"]

        yt_cache[key] = vid
        yt_calls += 1

        return vid

    except HttpError:
        return None

# =========================
# ENGINE
# =========================

def run():

    snapshot = load_json(SNAPSHOT_FILE)
    final = {}

    for genre, months in GENRE_RULES.items():

        playlists = PLAYLISTS.get(genre, [])
        raw = []

        for pid in playlists:
            raw += get_playlist_tracks(pid, months)

        if not raw:
            raw = fallback(genre, months)

        # dedupe
        seen = set()
        tracks = []

        for t in raw:
            k = f"{t['artist']} - {t['name']}"
            if k in seen:
                continue
            seen.add(k)
            tracks.append(t)

        tracks = sorted(tracks, key=lambda x: x["popularity"], reverse=True)

        # GUARANTEE EXACT 25
        tracks = tracks[:TARGET]

        ranked = []

        for i, t in enumerate(tracks):

            key = f"{t['artist']} - {t['name']}"

            prev_rank = snapshot.get(genre, {}).get(key, None)
            current_rank = i + 1

            movement = "new"

            if prev_rank:
                if prev_rank > current_rank:
                    movement = "up"
                elif prev_rank < current_rank:
                    movement = "down"
                else:
                    movement = "same"

            yt_lookup(key, f"{t['artist']} {t['name']} official audio")

            score = t["popularity"] * 10

            ranked.append({
                "name": t["name"],
                "artist": t["artist"],
                "image": t["image"],
                "badge": t["badge"],
                "rank": current_rank,
                "movement": movement,
                "score": score
            })

        final[genre] = ranked

    # build snapshot (for next week movement tracking)
    new_snapshot = {}

    for g, songs in final.items():
        new_snapshot[g] = {}
        for s in songs:
            new_snapshot[g][f"{s['artist']} - {s['name']}"] = s["rank"]

    save_json(CACHE_FILE, yt_cache)
    save_json(SNAPSHOT_FILE, new_snapshot)
    save_json("data/charts.json", final)

    build_html(final)

# =========================
# HTML (FIXED - NO RAW CODE BUG)
# =========================

def build_html(data):

    json_data = json.dumps(data)

    html = f"""
    <html>
    <head>
      <title>Carib25</title>
      <style>
        body {{ background:#0f0f0f; color:white; font-family:Arial; }}
        h1 {{ text-align:center; color:#ffcc00; }}
        .song {{ display:flex; gap:10px; padding:10px; border-bottom:1px solid #222; align-items:center; }}
        img {{ width:50px; height:50px; border-radius:4px; }}
        .badge {{ font-size:11px; color:#ffcc00; }}
        .up {{ color:#00ff99; }}
        .down {{ color:#ff4d4d; }}
        .new {{ color:#4da6ff; }}
        .score {{ margin-left:auto; color:#00ff99; }}
        button {{ margin:5px; padding:8px; background:#222; color:white; border:1px solid #333; }}
      </style>
    </head>

    <body>

    <h1>Carib25</h1>

    <div style="text-align:center;">
      <button onclick="show('soca')">Soca</button>
      <button onclick="show('dancehall')">Dancehall</button>
      <button onclick="show('afrobeats')">Afrobeats</button>
      <button onclick="show('bouyon')">Bouyon</button>
    </div>

    <div id="app"></div>

    <script>
    const data = {json_data};

    function show(g) {{
      const app = document.getElementById("app");
      app.innerHTML = "";

      data[g].forEach(s => {{

        app.innerHTML += `
          <div class="song">

            <img src="${{s.image || ''}}">

            <div>
              #${{s.rank}} ${{s.artist}} - ${{s.name}}

              <div class="${{s.movement}}">
                ${{s.movement === "up" ? "⬆ Rising"
                  : s.movement === "down" ? "⬇ Falling"
                  : "🆕 New"}}
              </div>

              <div class="badge">${{s.badge || ""}}</div>
            </div>

            <div class="score">
              ${{Math.round(s.score)}}
            </div>

          </div>
        `;
      }});
    }}

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
