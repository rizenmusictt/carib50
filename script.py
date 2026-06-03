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
# 2. FIXED ARRAYS & EXCLUSIVE ID MAPS
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

SOCA_ARTIST_IDS = [
    "6wxP7SSzfvi21Cnl8JicdQ",
    "7E6r9S8qCRfZVCjF1A8do6",
    "0crMctn4iXaE3XCHpeBkOt",
    "1K23l3n63BTCtIMm0TyS4c",
    "61buXyJGplh38VDpEaB2ds",
    "6nPHDCN7qmxO86eN1grP54",
    "4nLVEYSAcpANC0BV87P4rd",
    "5WYAHpwcYoSdCz5nXebrKn",
    "10AVFI86WCq4tNhY31g6FL",
    "1lE1SGLNabSpBbJB9A9qtU",
    "56BHYURgbka2nQbBy8XZ3x",
    "1qKzKUnuQsjB83hBZffoq0",
    "3uqI1IbL5XKd3Lf8FVSZWH",
    "27GA6NMM69byd5ankSWsXw",
    "4OD7vSNDpVB2VxTbifT8fG",
    "7ymbjgoFo1FSdcVCKjxQUn",
    "0KnjqOM3FNDO3SUSKWRDLj"
]

DANCEHALL_ARTIST_IDS = [
    "2NUz5P42WqkxilbI8ocN76",
    "1OFOShsIbhy1l5x73yuVyB",
    "1fctva4kpRbg2k3v7kwRuS",
    "08erObvNX7rs7d4pbuaRCQ",
    "2LIAgeQ5NZurwixfoG3CWZ",
    "7dvG18F378r7HRxmiHn3ti",
    "2Gzy8TYJ5xrEMDyUjZuDsK",
    "2v6V75NbousiJwy2HV44VL",
    "62DmErcU7dqZbJaDqwsqzR",
    "4ULg9wVZKb01ORw7AIZBDR",
    "2WyypmYjOdaXg0bXDP67j7",
    "5FrdcC0audM19v7r1GQx4P",
    "3nwYsifpwrKmCIpw4i0HDW",
    "48ZXHIYtqeBiklzhu3lAey",
    "4SGo67MJz6DdsjzaRZ4OD7",
    "5FkUhnHQ0KC63549LHHtst",
    "0eezS9KmhdjGN436RdTIXu",
    "63o6Z7qrOen7eLbmYOx7gt"
]

AFROBEATS_ARTIST_IDS = [
    "5yOvAmpIR7hVxiS6Ls5DPO",
    "3tVQdUvClmAT7URs9V3rsp",
    "3a1tBryiczPAZpgoZN9Rzg",
    "3zaDigUwjHvjOkSn0NDf9x",
    "2hVWBpjLW4Q7fboYz2pVYK",
    "3ZpEKRjHaHANcpk10u6Ntq",
    "5k9IrMHs9Jfpk8A94Ta7nR",
    "1XavfPKBpNjkOfxHINlMHF",
    "3SozjO3Lat463tQICI9LcE",
    "687cZJR45JO7jhk1LHIbgq",
    "46pWGuE3dSwY3bMMXGBvVS"
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

    elif genre == "dancehall":
        for a_id in DANCEHALL_ARTIST_IDS:
            try:
                res = sp.artist_top_tracks(a_id)
                for t in res["tracks"]:
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

    elif genre == "soca":
        for a_id in SOCA_ARTIST_IDS:
            try:
                res = sp.artist_top_tracks(a_id)
                for t in res["tracks"]:
                    process_track(t, raw_tracks)
            except Exception:
                pass
        all_soca_playlists = SOCA_PLAYLISTS + SOCA_EXTRA_PLAYLISTS
        for p_id in all_soca_playlists:
            try:
                p_tracks = sp.playlist_items(p_id)
                for item in p_tracks.get("items", []):
                    if item.get("track"): process_track(item["track"], raw_tracks)
            except Exception:
                pass

    elif genre == "afrobeats":
        for a_id in AFROBEATS_ARTIST_IDS:
            try:
                res = sp.artist_top_tracks(a_id)
                for t in res["tracks"]:
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

    filtered = []
    for t_id, t in raw_tracks.items():
        if t_id in global_used_tracks:
            continue
            
        if not within_window(t["release"], genre): continue
        if not clean(t["name"]): continue

        all_artists_lower = t["all_artists"].lower()
        
        if genre == "soca":
            if t["artist_id"] in BOUYON_ARTIST_IDS:
                continue

        if genre == "afrobeats":
            if any(m in all_artists_lower for m in MAINSTREAM_BLACKLIST):
                if t["artist_id"] not in AFROBEATS_ARTIST_IDS:
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
        "release": t
