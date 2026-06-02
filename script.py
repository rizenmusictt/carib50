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

GENRE_RULES = {
    "soca": 4,         # Strict 4-month limit (~120 days)
    "dancehall": 4,     # Strict 4-month limit (~120 days)
    "afrobeats": 6,     # Strict 6-month limit (~180 days)
    "bouyon": 6         # Strict 6-month limit (~180 days)
}

SOCA_DIRECT_PLAYLISTS = [
    "1FvkIodyAGsGy0MSMjSnAr",  # DJ Jel Playlist 1
    "3ugx3RitHXhWDiGTh7UUu2",  # DJ Jel Playlist 2
    "4brkOclzIpXABVHLnesMJt"   # Rizenmusic Playlist
]

PLAYLIST_QUERIES = {
    "dancehall": ["2026 dancehall", "new dancehall", "top dancehall"],
    "afrobeats": ["2026 afrobeats", "new afrobeats", "top afrobeats"],
    "bouyon": ["bouyon 2026", "new bouyon", "top bouyon"]
}

BLACKLIST = ["mix", "dj", "set", "live", "radio", "intro"]
AFROBEATS_ARTIST_BLACKLIST = ["drake", "don toliver"]

# ==========================================
# 2. GENRE-SPECIFIC WEIGHT SIGNALS
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

BOUYON_ARTISTS = [
    "1T1", "Miimii KDS", "Blackboy",
    "Ridge", "Quan", "Jessie",
    "Triple Kay", "Reo",
    "Maureen", "Lé Will", "Deuspi", 
    "O Banga", "Trixx", "Home Grown Studio", "Tydi S"
]

# ==========================================
# 3. INITIALIZATION
# ==========================================

sp = spotipy.Spotify(
    auth_manager=SpotifyClientCredentials(
        client_id=os.environ["SPOTIFY_CLIENT_ID"],
        client_secret=os.environ["SPOTIFY_CLIENT_SECRET"]
    )
)

# ==========================================
# 4. ROBUST HELPERS & PARSERS
# ==========================================

def clean(name):
    return not any(x in name.lower() for x in BLACKLIST)

def clean_string_signature(val):
    return re.sub(r'[^a-z0-9]', '', val.lower())

def parse_date(date_str):
    if not date_str:
        return None
    date_str = date_str.strip()
    
    if len(date_str) == 4 and date_str.isdigit():
        return datetime(int(date_str), 1, 1)
        
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        try:
            return datetime.strptime(date_str, "%Y-%m")
        except ValueError:
            return None

def within_window(date_str, genre):
    track_date = parse_date(date_str)
    if not track_date:
        return False

    limit_months = GENRE_RULES.get(genre, 4)
    allowed_cutoff = datetime.utcnow() - timedelta(days=limit_months * 30)
    return track_date >= allowed_cutoff

def score_genre(genre, artist, name, all_artists_string=""):
    text = (artist + " " + name + " " + all_artists_string).lower()
    score = 0

    if genre == "soca" and any(a.lower() in text for a in SOCA_ARTISTS): score += 15
    if genre == "dancehall" and any(a.lower() in text for a in DANCEHALL_ARTISTS): score += 15
    if genre == "afrobeats" and any(a.lower() in text for a in AFROBEATS_ARTISTS): score += 15
    if genre == "bouyon" and any(a.lower() in text for a in BOUYON_ARTISTS): score += 15

    if genre in text:
        score += 5

    return score

# ==========================================
# 5. MULTI-PLATFORM POPULARITY SCORING
# ==========================================

def get_youtube_views(artist, track_name):
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return None
        
    try:
        query = urllib.parse.quote(f"{artist} {track_name} official")
        url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&q={query}&type=video&maxResults=1&key={api_key}"
        
        with urllib.request.urlopen(url, timeout=4) as r:
            res = json.loads(r.read().decode())
            items = res.get("items", [])
            if not items:
                return 0
            video_id = items[0]["id"]["videoId"]
            
        stats_url = f"https://www.googleapis.com/youtube/v3/videos?part=statistics&id={video_id}&key={api_key}"
        with urllib.request.urlopen(stats_url, timeout=4) as r:
            stats_res = json.loads(r.read().decode())
            video_items = stats_res.get("items", [])
            if video_items:
                return int(video_items[0]["statistics"].get("viewCount", 0))
        return 0
    except Exception as e:
        return None

# ==========================================
# 6. ENGINE DATA COLLECTOR
# ==========================================

def discover_playlists(query):
    try:
        res = sp.search(q=query, type="playlist", limit=5)
        return [p["id"] for p in res["playlists"]["items"]]
    except:
        return []

def get_playlist_tracks(pid):
    try:
        res = sp.playlist_items(pid)
    except:
        return []

    out = []
    for item in res.get("items", []):
        t = item.get("track")
        if not t or not t.get("name"):
            continue

        name = t["name"]
        primary_artist = t["artists"][0]["name"] if t["artists"] else "Unknown"
        all_artists = ", ".join([a["name"] for a in t["artists"]])

        if not clean(name):
            continue

        out.append({
            "id": t["id"],
            "name": name,
            "artist": primary_artist,
            "all_artists": all_artists,
            "release": t["album"]["release_date"],
            "image": t["album"]["images"][0]["url"] if t["album"]["images"] else "",
            "preview": t.get("preview_url"),
            "spotify_url": t["external_urls"]["spotify"],
            "popularity": t["popularity"]
        })
    return out

# ==========================================
# 7. EXECUTION ENGINE
# ==========================================

def run():
    final = {}
    ordered_genres = ["soca", "dancehall", "afrobeats", "bouyon"]
    soca_locked_titles = set()

    # Pre-load old chart database file before performing state manipulation
    existing_chart_data = {}
    try:
        if os.path.exists("data/charts.json"):
            with open("data/charts.json", "r") as f:
                existing_chart_data = json.load(f)
    except Exception as e:
        print(f"Warning: Map state tracker failed to open old data records: {e}")

    for genre in ordered_genres:
        raw = []

        if genre == "soca":
            for pid in SOCA_DIRECT_PLAYLISTS:
                raw += get_playlist_tracks(pid)
        else:
            for q in PLAYLIST_QUERIES[genre]:
                for pid in discover_playlists(q):
                    raw += get_playlist_tracks(pid)
                
                try:
                    track_search = sp.search(q=q, type="track", limit=50)
                    for item in track_search.get("tracks", {}).get("items", []):
                        if not item or not item.get("name"): continue
                        name = item["name"]
                        primary_artist = item["artists"][0]["name"] if item["artists"] else "Unknown"
                        all_artists = ", ".join([a["name"] for a in item["artists"]])
                        
                        if not clean(name): continue
                        raw.append({
                            "id": item["id"],
                            "name": name,
                            "artist": primary_artist,
                            "all_artists": all_artists,
                            "release": item["album"]["release_date"],
                            "image": item["album"]["images"][0]["url"] if item["album"]["images"] else "",
                            "preview": item.get("preview_url"),
                            "spotify_url": item["external_urls"]["spotify"],
                            "popularity": item["popularity"]
                        })
                except Exception as e:
                    print(f"Direct search lookup skipping for query '{q}': {e}")

        # STEP 2: Deduplication
        seen = set()
        tracks = []
        for t in raw:
            key = f"{t['artist']} - {t['name']}".lower()
            if key in seen:
                continue
            seen.add(key)
            tracks.append(t)

        # STEP 3: Timeframe Window Filtering
        tracks = [t for t in tracks if within_window(t["release"], genre)]

        # STEP 4: Scoring and Isolation Logic
        candidates = []
        for t in tracks:
            artist_lower = t["artist"].lower()
            all_artists_lower = t["all_artists"].lower()
            title_sig = clean_string_signature(t["name"])

            # HARD BLOCK BOUYON LEAKAGE FROM ENTERING SOCA LISTS
            if genre == "soca":
                if any(b_art.lower() in all_artists_lower for b_art in BOUYON_ARTISTS):
                    continue  

            # BOUYON EXCLUSION LOGIC
            if genre == "bouyon":
                if title_sig in soca_locked_titles:
                    continue
                if any(s_art.lower() in all_artists_lower for s_art in SOCA_ARTISTS):
                    if not any(b_art.lower() in all_artists_lower for b_art in BOUYON_ARTISTS):
                        continue

            # AFROBEATS STAR FILTERING
            if genre == "afrobeats":
                if any(bl in artist_lower for bl in AFROBEATS_ARTIST_BLACKLIST):
                    if not any(real_afro.lower() in all_artists_lower for real_afro in AFROBEATS_ARTISTS):
                        continue

            # Normalized Popularity-First Scoring Math Engine
            s = score_genre(genre, t["artist"], t["name"], t["all_artists"])
            yt_views = get_youtube_views(t["artist"], t["name"])
            
            if yt_views is not None:
                yt_pop_score = min(100, yt_views / 500)
                combined_popularity = (t["popularity"] * 0.5) + (yt_pop_score * 0.5)
            else:
                combined_popularity = t["popularity"]

            # Pure play metrics drive the base sorting entirely
            t["final_score"] = combined_popularity + s
            candidates.append(t)

        # STEP 5: Sorting & Evaluation Trim
        final_sorted = sorted(candidates, key=lambda x: x["final_score"], reverse=True)
        final_selection = final_sorted[:TARGET]

        if genre == "soca":
            for track in final_selection:
                soca_locked_titles.add(clean_string_signature(track["name"]))

        # STEP 6: History Mapping Pipeline Comparison Setup
        prev_history = {}
        if genre in existing_chart_data:
            for past_track in existing_chart_data[genre]:
                past_key = f"{past_track['artist'].lower()} - {past_track['name'].lower()}"
                prev_history[past_key] = past_track.get("rank")

        # STEP 7: Format Final Response JSON Array Payload Structure
        output = []
        for i, t in enumerate(final_selection):
            current_rank = i + 1
            lookup_key = f"{t['artist'].lower()} - {t['name'].lower()}"
            
            # Resolve history delta tracking flags
            old_rank = prev_history.get(lookup_key)
            if old_rank:
                history_display = f"Last Spot: #{old_rank}"
            else:
                history_display = "New"

            output.append({
                "rank": current_rank,            # Number 1-25 explicitly managed on left side
                "name": t["name"],
                "artist": t["artist"],
                "image": t["image"],
                "preview": t["preview"],          # Direct link mapping for on-site HTML5 media streaming
                "spotify_url": t["spotify_url"],
                "history": history_display,       # Right side position indicator mapping
                "badge": "Fresh On De Scene" if i < 5 else None
            })

        final[genre] = output
        print(f"[{genre.upper()}] Success: Locked in {len(output)} processed tracks.")

    os.makedirs("data", exist_ok=True)
    with open("data/charts.json", "w") as f:
        json.dump(final, f, indent=2)

if __name__ == "__main__":
    run()
