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
    "soca": 4,         # Strict 4-month limit
    "dancehall": 4,     # Strict 4-month limit (UNTOUCHED)
    "afrobeats": 6,     # Strict 6-month limit
    "bouyon": 6         # Strict 6-month limit
}

# Explicitly mapping your high-value curated Soca playlists directly by ID
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

# Hard blacklists to prevent global Hip-Hop/Pop stars from hijacking genre charts
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
    "Triple Kay", "Reo"
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

def parse_date(d):
    try:
        return datetime.strptime(d, "%Y-%m-%d")
    except:
        try:
            return datetime.strptime(d, "%Y-%m")
        except:
            try:
                return datetime.strptime(d, "%Y")
            except:
                return None

def within_window(date_str, genre):
    d = parse_date(date_str)
    if not d:
        return False

    limit_months = GENRE_RULES.get(genre, 4)
    return d >= datetime.utcnow() - timedelta(days=limit_months * 30)

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
    
    # We enforce a strict ordered execution sequence: Soca first, then Bouyon to eliminate bleeding
    ordered_genres = ["soca", "dancehall", "afrobeats", "bouyon"]
    soca_locked_track_keys = set()

    for genre in ordered_genres:
        raw = []

        # STEP 1: Custom Harvesting Router
        if genre == "soca":
            # Direct insertion from your precise curation links
            for pid in SOCA_DIRECT_PLAYLISTS:
                raw += get_playlist_tracks(pid)
        else:
            # Traditional discovery pool for other genres
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

        # STEP 4: Advanced Cross-Genre Bleed & Blacklist Filtering
        candidates = []
        for t in tracks:
            # BLEED FIX: If processing Bouyon, block it instantly if it exists inside the verified Soca data keys
            if genre == "bouyon":
                match_key = f"{t['artist']} - {t['name']}".lower()
                if match_key in soca_locked_track_keys:
                    continue

            # HIP HOP FILTER: Stop top 40 American giants from taking over Afrobeats
            if genre == "afrobeats":
                artist_lower = t["artist"].lower()
                all_artists_lower = t["all_artists"].lower()
                
                if any(bl in artist_lower for bl in AFROBEATS_ARTIST_BLACKLIST):
                    # BYPASS RULE: If a pure Afrobeats heavyweight is explicitly featured on the song, save it!
                    if not any(real_afro.lower() in all_artists_lower for real_afro in AFROBEATS_ARTISTS):
                        continue

            s = score_genre(genre, t["artist"], t["name"], t["all_artists"])
            t["base_score"] = t["popularity"] * 10 + s * 5
            candidates.append(t)

        # Limit YouTube lookups to protect resource allocations
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

        # STEP 6: Sorting & Compilation Trim
        scored = sorted(scored, key=lambda x: x["score"], reverse=True)
        final_selection = scored[:TARGET]

        # LOGGING SELECTION: If it's Soca, save names to protect Bouyon during its loop
        if genre == "soca":
            for track in final_selection:
                soca_locked_track_keys.add(f"{track['artist']} - {track['name']}".lower())

        # STEP 7: Map Response Payload Format
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
