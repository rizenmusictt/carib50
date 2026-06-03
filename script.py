import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

# ==========================================
# 1. CORE PIPELINE CONFIGURATION
# ==========================================

TARGET = 25
CHALLENGERS = 5
POOL_SIZE = TARGET + CHALLENGERS # 30

WINDOWS = {
    "soca": 4,         
    "dancehall": 4,     
    "afrobeats": 6,     
    "bouyon": 6         
}

BLACKLIST = ["mix", "dj", "set", "live", "radio", "intro", "roadmix"]
MAINSTREAM_BLACKLIST = ["drake", "don toliver", "chris brown", "justin bieber", "ed sheeran"]

PLAYLIST_QUERIES = {
    "dancehall": ["2026 dancehall", "new dancehall", "top dancehall"],
    "afrobeats": ["2026 afrobeats", "new afrobeats", "top afrobeats"]
}

# ==========================================
# 2. RESTORED USER ASSETS & TARGET ID MAPS
# ==========================================

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

DANCEHALL_ARTISTS = [
    "Vybz Kartel", "Popcaan", "Masicka",
    "Skillibeng", "Shenseea", "Alkaline",
    "Skeng", "Valiant", "RajahWild"
]

AFROBEATS_ARTISTS = [
    "Wizkid", "Burna Boy", "Davido",
    "Rema", "Asake", "Tems",
    "Ayra Starr", "Fireboy DML", "Omah Lay", "Shallipopi", "SeyVez"
]

# ==========================================
# 3. INITIALIZATION & STATE
# ==========================================

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"]
    )
)

STATE_FILE = "data/tracker.json"
CHART_FILE = "data/charts.json"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"history": {}, "rosters": {}}

def save_state(state):
    os.makedirs("data", exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# ==========================================
# 4. ROBUST HELPERS
# ==========================================

def clean(name):
    return not any(x in name.lower() for x in BLACKLIST)

def within_window(date_str, genre):
    if not date_str:
        return False
    try:
        if len(date_str) == 4:
            track_date = datetime(int(date_str), 1, 1)
        else:
            track_date = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except Exception:
        return False

    limit_months = WINDOWS.get(genre, 4)
    cutoff = datetime.utcnow() - timedelta(days=limit_months * 30)
    return track_date >= cutoff

def get_youtube_views(artist, track_name):
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return 0
        
    try:
        query = urllib.parse.quote(f"{artist} {track_name} official")
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&type=video&maxResults=1&key={api_key}"
        
        with urllib.request.urlopen(url, timeout=4) as r:
            res = json.loads(r.read().decode())
            items = res.get("items", [])
            if not items: return 0
            video_id = items[0]["id"]["videoId"]
            
        stats_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={video_id}&key={api_key}"
        with urllib.request.urlopen(stats_url, timeout=4) as r:
            stats = json.loads(r.read().decode())
            return int(stats["items"][0]["statistics"].get("viewCount", 0))
    except Exception:
        return 0

# ==========================================
# 5. DISCOVERY ENGINE (FETCH & FILTER)
# ==========================================

def discover_tracks(genre, global_used_tracks):
    raw_tracks = {}

    # --- BOUYON DISCOVERY ---
    if genre == "bouyon":
        for a_id in BOUYON_ARTIST_IDS:
            try:
                res = sp.artist_top_tracks(a_id)
                for t in res["tracks"]:
                    process_track(t, raw_tracks)
            except Exception:
                pass
        for p_id in BOUYON_PLAYLISTS:
            try:
                p_tracks = sp.playlist_items(p_id)
                for item in p_tracks.get("items", []):
                    if item.get("track"): process_track(item["track"], raw_tracks)
            except Exception:
                pass

    # --- SOCA DISCOVERY ---
    elif genre == "soca":
        all_soca_playlists = SOCA_PLAYLISTS + SOCA_EXTRA_PLAYLISTS
        for p_id in all_soca_playlists:
            try:
                p_tracks = sp.playlist_items(p_id)
                for item in p_tracks.get("items", []):
                    if item.get("track"): process_track(item["track"], raw_tracks)
            except Exception:
                pass

    # --- DANCEHALL DISCOVERY ---
    elif genre == "dancehall":
        for artist in DANCEHALL_ARTISTS:
            try:
                res = sp.search(q=f"artist:{artist}", type="track", limit=15)
                for t in res["tracks"]["items"]:
                    process_track(t, raw_tracks)
            except Exception:
                pass
        for q in PLAYLIST_QUERIES["dancehall"]:
            try:
                res = sp.search(q=q, type="playlist", limit=2)
                for p in res["playlists"]["items"]:
                    if not p: continue
                    p_tracks = sp.playlist_items(p["id"])
                    for item in p_tracks.get("items", []):
                        if item.get("track"): process_track(item["track"], raw_tracks)
            except Exception:
                pass

    # --- AFROBEATS DISCOVERY ---
    elif genre == "afrobeats":
        for artist in AFROBEATS_ARTISTS:
            try:
                res = sp.search(q=f"artist:{artist}", type="track", limit=15)
                for t in res["tracks"]["items"]:
                    process_track(t, raw_tracks)
            except Exception:
                pass
        for q in PLAYLIST_QUERIES["afrobeats"]:
            try:
                res = sp.search(q=q, type="playlist", limit=2)
                for p in res["playlists"]["items"]:
                    if not p: continue
                    p_tracks = sp.playlist_items(p["id"])
                    for item in p_tracks.get("items", []):
                        if item.get("track"): process_track(item["track"], raw_tracks)
            except Exception:
                pass

    # --- PROCESSING AND FILTERING ---
    filtered = []
    for t_id, t in raw_tracks.items():
        if t_id in global_used_tracks:
            continue
            
        if not within_window(t["release"], genre): continue
        if not clean(t["name"]): continue

        all_artists_lower = t["all_artists"].lower()
        
        # RULE: Explicit Bouyon separation filter for Soca protection using ONLY IDs
        if genre == "soca":
            if t["artist_id"] in BOUYON_ARTIST_IDS:
                continue

        # RULE: Afrobeats mainstream filtering blocker
        if genre == "afrobeats":
            if any(m in all_artists_lower for m in MAINSTREAM_BLACKLIST):
                if not any(a.lower() in all_artists_lower for a in AFROBEATS_ARTISTS):
                    continue

        filtered.append(t)

    filtered.sort(key=lambda x: x["popularity"], reverse=True)
    return filtered[:POOL_SIZE]

def process_track(t, storage_dict):
    if not t or not t.get("name") or not t.get("id"): return
    primary_artist = t["artists"][0]["name"] if t["artists"] else "Unknown"
    primary_artist_id = t["artists"][0]["id"] if t["artists"] else ""
    all_artists = ", ".join([a["name"] for a in t["artists"]])
    
    storage_dict[t["id"]] = {
        "id": t["id"],
        "name": t["name"],
        "artist": primary_artist,
        "artist_id": primary_artist_id,
        "all_artists": all_artists,
        "release": t["album"]["release_date"],
        "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
        "preview": t.get("preview_url"),
        "spotify_url": t["external_urls"]["spotify"],
        "popularity": t["popularity"]
    }

# ==========================================
# 6. SCORING & PIPELINE EXECUTION
# ==========================================

def run():
    state = load_state()
    history = state.get("history", {})
    rosters = state.get("rosters", {})
    final_charts = {}
    
    global_used_tracks = set()
    ordered_genres = ["bouyon", "dancehall", "soca", "afrobeats"]

    for genre in ordered_genres:
        print(f"Executing pipeline for: {genre.upper()}")
        
        discovered_top_30 = discover_tracks(genre, global_used_tracks)
        evaluation_pool = []
        current_roster = rosters.get(genre, [])
        
        current_roster = [t for t in current_roster if t["id"] not in global_used_tracks]
        
        if not current_roster:
            evaluation_pool = discovered_top_30
        else:
            evaluation_pool = [t for t in current_roster]
            current_ids = {t["id"] for t in current_roster}
            
            challengers_added = 0
            for dt in discovered_top_30:
                if dt["id"] not in current_ids:
                    evaluation_pool.append(dt)
                    challengers_added += 1
                if challengers_added == CHALLENGERS:
                    break

        for track in evaluation_pool:
            t_id = track["id"]
            current_yt = get_youtube_views(track["artist"], track["name"])
            current_sp = track["popularity"]
            
            past
