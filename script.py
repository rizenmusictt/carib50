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

# EXPANDED: Added requested artists to stabilize identification and boundary lines
BOUYON_ARTISTS = [
    "1T1", "Miimii KDS", "Blackboy",
    "Ridge", "Quan", "Jessie",
    "Triple Kay", "Reo",
    "Maureen", "Lé Will", "Deuspi", 
    "O Banga", "Trixx", "Home Grown Studio"
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

def parse_date(date_str):
    if not date_str:
        return None
    # Strips any trailing whitespace or layout anomalies from Spotify values
    date_str = date_str.strip()
    try:
        return datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        try:
            return datetime.strptime(date_str, "%Y-%m")
        except ValueError:
            try:
                # Fallback for year-only metadata points
                return datetime.strptime(date_str, "%Y")
            except ValueError:
                return None

def within_window(date_str, genre):
    track_date = parse_date(date_str)
    if not track_date:
        return False

    limit_months = GENRE_RULES.get(genre, 4)
    # Strict delta calculation against today's date stamp
    allowed_cutoff = datetime.utcnow() - timedelta(days=limit_months * 30)
    return track_date >= allowed_cutoff

def score_genre(genre, artist, name, all_artists_string=""):
    text = (artist + " " + name + " " + all_artists_string).lower()
    score = 0

    if genre == "soca" and any(a.lower() in text for a in SOCA_ARTISTS): score += 3
    if genre == "dancehall" and any(a.lower() in text for a in DANCEHALL_ARTISTS): score += 3
    if genre == "afrobeats" and any(a.lower() in text for a in AFROBEATS_ARTISTS): score += 3
    if genre == "bouyon" and any(a.lower() in text for a in BOUYON_ARTISTS): score += 3

    if genre in text:
        score += 1

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
        print(f" [API Quota/Network Fallback] Defaulting to Spotify popularity for: {artist} - {track_name}")
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
    
    # Enforced sequential execution order to protect target boundaries
    ordered_genres = ["soca", "dancehall", "afrobeats", "bouyon"]
    soca_locked_track_keys = set()

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

        # STEP 3: Strict Timeframe Window Filtering (Calculated dynamically via calendar dates)
        tracks = [t for t in tracks if within_window(t["release"], genre)]

        # STEP 4: Advanced Cross-Genre Bleed & Blacklist Filtering
        candidates = []
        for t in tracks:
            artist_lower = t["artist"].lower()
            all_artists_lower = t["all_artists"].lower()
            match_key = f"{t['artist']} - {t['name']}".lower()

            # BOUYON PROTECTION SCHEME
            if genre == "bouyon":
                # 1. Stop track from passing if it was already caught on the Soca chart
                if match_key in soca_locked_track_keys:
                    continue
                
                # 2. Prevent Soca artist leakages unless an explicit Bouyon feature exists
                if any(s_art.lower() in all_artists_lower for s_art in SOCA_ARTISTS):
                    if not any(b_art.lower() in all_artists_lower for b_art in BOUYON_ARTISTS):
                        continue

            # AFROBEATS HIP HOP ISOLATION
            if genre == "afrobeats":
                if any(bl in artist_lower for bl in AFROBEATS_ARTIST_BLACKLIST):
                    if not any(real_afro.lower() in all_artists_lower for real_afro in AFROBEATS_ARTISTS):
                        continue

            s = score_genre(genre, t["artist"], t["name"], t["all_artists"])
            t["base_score"] = t["popularity"] * 10 + s * 5
            candidates.append(t)

        candidates = sorted(candidates, key=lambda x: x["base_score"], reverse=True)[:40]

        # STEP 5: Dual Network Check
        scored = []
        for t in candidates:
            s = score_genre(genre, t["artist"], t["name"], t["all_artists"])
            yt_views = get_youtube_views(t["artist"], t["name"])
            
            if yt_views is not None:
                yt_pop_score = min(100, yt_views / 500)
                combined_pop = (t["popularity"] * 0.5) + (yt_pop_score * 0.5)
                t["score"] = combined_pop * 10 + s * 5
            else:
                t["score"] = t["base_score"]
                
            scored.append(t)

        # STEP 6: Final Sorting & Trimming
        scored = sorted(scored, key=lambda x: x["score"], reverse=True)
        final_selection = scored[:TARGET]

        # Update cross-genre verification flags if executing Soca loops
        if genre == "soca":
            for track in final_selection:
                soca_locked_track_keys.add(f"{track['artist']} - {track['name']}".lower())

        # STEP 7: Map Payload Structure
        output = []
        for i, t in enumerate(final_selection):
            output.append({
                "rank": i + 1,
                "name": t["name"],
                "artist": t["artist"],
                "image": t["image"],
                "preview": t["preview"],
                "spotify_url": t["spotify_url"],
                "badge": "Fresh On De Scene" if i < 5 else None
            })

        final[genre] = output
        print(f"[{genre.upper()}] Success: Locked in {len(output)} pristine tracks.")

    os.makedirs("data", exist_ok=True)
    with open("data/charts.json", "w") as f:
        json.dump(final, f, indent=2)

# ==========================================
# 8. PROCESS ENTRYPOINT
# ==========================================

if __name__ == "__main__":
    run()
