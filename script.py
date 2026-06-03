import os
import json
import urllib.request
import urllib.parse
import re
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

# Genre specific queries
PLAYLIST_QUERIES = {
    "dancehall": ["2026 dancehall", "new dancehall", "top dancehall"],
    "afrobeats": ["2026 afrobeats", "new afrobeats", "top afrobeats"],
    "bouyon": ["bouyon 2026", "new bouyon", "top bouyon"],
    "soca": ["2026 soca", "new soca", "top soca"]
}

# ==========================================
# 2. STRICT GENRE LISTS (FOR DISCOVERY)
# ==========================================

SOCA_ARTISTS = [
    "Machel Montano", "Kes", "Nailah Blackman",
    "Voice", "Patrice Roberts", "Skinny Fabulous",
    "Farmer Nappy", "Lyrikal", "Olatunji"
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

# Explicitly mapping specific artists to Bouyon to prevent Soca bleed
BOUYON_ARTISTS = [
    "1T1", "Miimii KDS", "Blackboy",
    "Ridge", "Quan", "Jessie",
    "Triple Kay", "Reo",
    "Maureen", "Lé Will", "Deuspi", 
    "O Banga", "Trixx", "Home Grown Studio", "Tydi S"
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

def discover_tracks(genre, global_bouyon_cache):
    raw_tracks = {}

    # 1. Search by Core Artists
    artist_list = []
    if genre == "bouyon": artist_list = BOUYON_ARTISTS
    elif genre == "soca": artist_list = SOCA_ARTISTS
    elif genre == "dancehall": artist_list = DANCEHALL_ARTISTS
    elif genre == "afrobeats": artist_list = AFROBEATS_ARTISTS

    for artist in artist_list:
        try:
            res = sp.search(q=f"artist:{artist}", type="track", limit=20)
            for t in res["tracks"]["items"]:
                process_track(t, raw_tracks)
        except Exception:
            pass

    # 2. Search by Playlists
    for q in PLAYLIST_QUERIES.get(genre, []):
        try:
            res = sp.search(q=q, type="playlist", limit=3)
            for p in res["playlists"]["items"]:
                if not p: continue
                p_tracks = sp.playlist_items(p["id"])
                for item in p_tracks.get("items", []):
                    if item.get("track"): process_track(item["track"], raw_tracks)
        except Exception:
            pass

    # 3. Filter by Time Window and Genre Rules
    filtered = []
    for t_id, t in raw_tracks.items():
        if not within_window(t["release"], genre): continue
        if not clean(t["name"]): continue

        all_artists_lower = t["all_artists"].lower()
        
        # RULE: No Bouyon tracks/artists in Soca
        if genre == "soca":
            if t_id in global_bouyon_cache or any(b.lower() in all_artists_lower for b in BOUYON_ARTISTS):
                continue

        # RULE: Afrobeats mainstream block (Unless Afrobeats artist is featured)
        if genre == "afrobeats":
            if any(m in all_artists_lower for m in MAINSTREAM_BLACKLIST):
                if not any(a.lower() in all_artists_lower for a in AFROBEATS_ARTISTS):
                    continue

        filtered.append(t)

    # 4. Return Top 30 by Raw Spotify Popularity for the Discovery Pool
    filtered.sort(key=lambda x: x["popularity"], reverse=True)
    return filtered[:POOL_SIZE]

def process_track(t, storage_dict):
    if not t or not t.get("name"): return
    primary_artist = t["artists"][0]["name"] if t["artists"] else "Unknown"
    all_artists = ", ".join([a["name"] for a in t["artists"]])
    
    storage_dict[t["id"]] = {
        "id": t["id"],
        "name": t["name"],
        "artist": primary_artist,
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
    
    global_bouyon_cache = set()

    ordered_genres = ["bouyon", "soca", "dancehall", "afrobeats"]

    for genre in ordered_genres:
        print(f"Executing pipeline for: {genre.upper()}")
        
        # 1. Discover the Top 30 recent tracks
        discovered_top_30 = discover_tracks(genre, global_bouyon_cache)
        
        if genre == "bouyon":
            global_bouyon_cache = {t["id"] for t in discovered_top_30}

        # 2. Build the Evaluation Pool
        evaluation_pool = []
        current_roster = rosters.get(genre, [])
        
        if not current_roster:
            # WEEK 1: Evaluate all 30 discovered tracks
            evaluation_pool = discovered_top_30
        else:
            # MOVING FORWARD: Keep the 25 current tracks
            evaluation_pool = [t for t in current_roster]
            current_ids = {t["id"] for t in current_roster}
            
            # Find the top 5 NEW tracks from discovery to challenge them
            challengers_added = 0
            for dt in discovered_top_30:
                if dt["id"] not in current_ids:
                    evaluation_pool.append(dt)
                    challengers_added += 1
                if challengers_added == CHALLENGERS:
                    break

        # 3. Capture Current Views and Calculate Deltas
        for track in evaluation_pool:
            t_id = track["id"]
            current_yt = get_youtube_views(track["artist"], track["name"])
            current_sp = track["popularity"]
            
            # Fetch past data, default to current if it's new (Week 1 or new challenger)
            past_data = history.get(t_id, {"yt": current_yt, "sp": current_sp})
            
            # Calculate Velocity (Delta)
            yt_delta = max(0, current_yt - past_data["yt"])
            sp_delta = max(0, current_sp - past_data["sp"])
            
            # Scale factor to combine 0-100 Spotify popularity with raw YouTube views
            # 80% YT Delta / 20% Spotify Delta
            yt_score = yt_delta * 0.8
            sp_score = (sp_delta * 1000) * 0.2 # Scaled to create meaningful impact
            
            track["final_score"] = yt_score + sp_score
            
            # Update history cache for next week
            history[t_id] = {"yt": current_yt, "sp": current_sp}

        # 4. Sort Pool, Drop Lowest 5, Lock Top 25
        evaluation_pool.sort(key=lambda x: x["final_score"], reverse=True)
        locked_top_25 = evaluation_pool[:TARGET]
        
        # 5. Format Output & Determine Historical Rank
        output = []
        past_roster_map = {t["id"]: i+1 for i, t in enumerate(current_roster)}
        
        for i, track in enumerate(locked_top_25):
            old_rank = past_roster_map.get(track["id"])
            history_display = f"Last Spot: #{old_rank}" if old_rank else "New"
            
            output.append({
                "rank": i + 1,
                "name": track["name"],
                "artist": track["artist"],
                "image": track["image"],
                "preview": track["preview"],
                "spotify_url": track["spotify_url"],
                "history": history_display
            })

        # Save to memory for file writing
        rosters[genre] = locked_top_25
        final_charts[genre] = output
        print(f"[{genre.upper()}] Locked top 25.")

    # 6. Save State and Outputs
    state["history"] = history
    state["rosters"] = rosters
    save_state(state)
    
    with open(CHART_FILE, "w") as f:
        json.dump(final_charts, f, indent=2)
        
    print("Chart pipeline execution complete.")

if __name__ == "__main__":
    run()
