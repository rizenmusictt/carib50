import os
import json
import urllib.request
import urllib.parse
import re
from datetime import datetime, timedelta

API_KEY = os.environ.get("YOUTUBE_API_KEY")

if not API_KEY:
    print("Error: YOUTUBE_API_KEY missing.")
    exit(1)

today = datetime.utcnow()
four_months_ago = today - timedelta(days=120)
published_after = four_months_ago.strftime('%Y-%m-%dT%H:%M:%SZ')
current_year = today.year

# Added Chutney as its own official genre
genres = ["soca", "chutney", "dancehall", "reggae", "bouyon", "afrobeats"]
history = {}
is_first_run = True

def get_duration_seconds(duration_str):
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', duration_str)
    if not match:
        return 0
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    seconds = int(match.group(3)) if match.group(3) else 0
    return (hours * 3600) + (minutes * 60) + seconds

# Load history
try:
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
            if "charts" in old_data and "all_genres" in old_data["charts"]:
                for track in old_data["charts"]["all_genres"]:
                    history[track["id"]] = track["lifetime_views"]
        is_first_run = False
except Exception:
    print("Running as Week 1 Baseline.")

final_charts = {}
all_tracks_master = []
global_claimed_ids = set() # To prevent duplicates completely across ALL charts

# Search and process each genre
for genre in genres:
    print(f"Fetching pages for {genre.upper()}...")
    genre_tracks = []
    video_ids = []
    video_snippets = {}
    
    search_query = f"{genre} {current_year}"
    next_page_token = None
    
    for page in range(3):
        search_query_params = {
            "part": "snippet", "q": search_query, "type": "video",
            "order": "viewCount", "publishedAfter": published_after,
            "maxResults": 50, "key": API_KEY
        }
        if next_page_token:
            search_query_params["pageToken"] = next_page_token
            
        search_params = urllib.parse.urlencode(search_query_params)
        search_url = f"https://www.googleapis.com/youtube/v3/search?{search_params}"
        
        try:
            with urllib.request.urlopen(search_url) as response:
                search_data = json.loads(response.read().decode())
                
                for item in search_data.get("items", []):
                    vid = item["id"]["videoId"]
                    video_ids.append(vid)
                    video_snippets[vid] = {
                        "id": vid,
                        "title": item["snippet"]["title"],
                        "channel": item["snippet"]["channelTitle"],
                        "genre": genre,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]
                    }
                
                next_page_token = search_data.get("nextPageToken")
                if not next_page_token:
                    break
        except Exception as e:
            print(f"Search error: {e}")
            break

    if not video_ids:
        continue

    # Process details and filter
    chunk_size = 50
    chunks = [video_ids[i:i + chunk_size] for i in range(0, len(video_ids), chunk_size)]

    for chunk in chunks:
        stats_params = urllib.parse.urlencode({
            "part": "statistics,contentDetails", "id": ",".join(chunk), "key": API_KEY
        })
        stats_url = f"https://www.googleapis.com/youtube/v3/videos?{stats_params}"
        
        try:
            with urllib.request.urlopen(stats_url) as stats_response:
                stats_data = json.loads(stats_response.read().decode())
                
                for item in stats_data.get("items", []):
                    vid = item["id"]
                    track = video_snippets[vid]
                    title_lower = track["title"].lower()
                    channel_lower = track["channel"].lower()
                    
                    # 1. DUPES FILTER: If another genre claimed it already, skip it
                    if vid in global_claimed_ids:
                        continue

                    # 2. FLUFF FILTER: Block instrumentals, riddim versions, and edits
                    if any(bad_word in title_lower for bad_word in ["instrumental", "version", "edit"]):
                        continue
                        
                    # 3. CHUTNEY FILTER: Route chutney away from soca completely
                    if "chutney" in title_lower or "chutney" in channel_lower:
                        if genre != "chutney":
                            continue # Ignore here; let the chutney loop pick it up naturally

                    # 4. ANTI-BLEEDING FILTERS: Strict crossover protection
                    if genre == "soca" and "dancehall" in title_lower and "soca" not in title_lower:
                        continue
                    if genre == "reggae" and "dancehall" in title_lower and "reggae" not in title_lower:
                        continue
                    if genre == "soca" and "reggae" in title_lower and "soca" not in title_lower:
                        continue
                    
                    # 5. DURATION FILTER (90s to 5 mins)
                    duration_raw = item["contentDetails"].get("duration", "")
                    duration_seconds = get_duration_seconds(duration_raw)
                    if duration_seconds < 90 or duration_seconds > 300:
                        continue
                        
                    # Calculate weekly view parameters
                    current_views = int(item["statistics"].get("viewCount", 0))
                    track["lifetime_views"] = current_views
                    
                    if is_first_run:
                        weekly_views = current_views
                    else:
                        weekly_views = max(0, current_views - history.get(vid, 0))
                        
                    track["weekly_views"] = weekly_views
                    genre_tracks.append(track)
                    global_claimed_ids.add(vid)
                    
        except Exception as e:
            print(f"Stats chunk processing error: {e}")
                    
    genre_tracks.sort(key=lambda x: x["weekly_views"], reverse=True)
    final_charts[genre] = genre_tracks[:50]
    print(f"Cleaned and secured {len(final_charts[genre])} tracks for {genre.upper()}.")

# Build the global master chart from all unique tracks caught
for genre_key in genres:
    for t in final_charts.get(genre_key, []):
        if t not in all_tracks_master:
            all_tracks_master.append(t)

all_tracks_master.sort(key=lambda x: x["weekly_views"], reverse=True)
final_charts["all_genres"] = all_tracks_master[:50]

final_output = {
    "last_updated": today.strftime('%Y-%m-%d'),
    "charts": final_charts
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(final_output, f, indent=4)

print("Carib50 Core Engine Successfully updated!")
