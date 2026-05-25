import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

API_KEY = os.environ.get("YOUTUBE_API_KEY")

if not API_KEY:
    print("Error: YOUTUBE_API_KEY missing.")
    exit(1)

today = datetime.utcnow()
four_months_ago = today - timedelta(days=120)
published_after = four_months_ago.strftime('%Y-%m-%dT%H:%M:%SZ')
current_year = today.year

genres = ["soca", "dancehall", "reggae", "bouyon", "afrobeats"]
history = {}
is_first_run = True

# Load previous week's data to calculate momentum
try:
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
            # We look at the "all_genres" master list to build our memory
            if "charts" in old_data and "all_genres" in old_data["charts"]:
                for track in old_data["charts"]["all_genres"]:
                    history[track["id"]] = track["lifetime_views"]
        is_first_run = False
except Exception:
    print("Running as Week 1 Baseline.")

final_charts = {}
all_tracks_master = [] # The giant bucket for the combined chart
processed_video_ids = set() # To stop a track from being counted twice if it fits two genres

# Search and process each genre
for genre in genres:
    print(f"Fetching {genre}...")
    genre_tracks = []
    
    search_query = f"{genre} {current_year}"
    search_params = urllib.parse.urlencode({
        "part": "snippet", "q": search_query, "type": "video",
        "order": "viewCount", "publishedAfter": published_after,
        "maxResults": 50, "key": API_KEY
    })
    search_url = f"https://www.googleapis.com/youtube/v3/search?{search_params}"
    
    try:
        with urllib.request.urlopen(search_url) as response:
            search_data = json.loads(response.read().decode())
            video_ids = []
            video_snippets = {}
            
            for item in search_data.get("items", []):
                vid = item["id"]["videoId"]
                video_ids.append(vid)
                video_snippets[vid] = {
                    "id": vid,
                    "title": item["snippet"]["title"],
                    "channel": item["snippet"]["channelTitle"],
                    "genre": genre,
                    "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]
                }
            
            if not video_ids: continue

            # Get exact views
            stats_params = urllib.parse.urlencode({
                "part": "statistics", "id": ",".join(video_ids), "key": API_KEY
            })
            stats_url = f"https://www.googleapis.com/youtube/v3/videos?{stats_params}"
            
            with urllib.request.urlopen(stats_url) as stats_response:
                stats_data = json.loads(stats_response.read().decode())
                
                for item in stats_data.get("items", []):
                    vid = item["id"]
                    current_views = int(item["statistics"].get("viewCount", 0))
                    track = video_snippets[vid]
                    track["lifetime_views"] = current_views
                    
                    if is_first_run:
                        weekly_views = current_views
                    else:
                        weekly_views = max(0, current_views - history.get(vid, 0))
                        
                    track["weekly_views"] = weekly_views
                    genre_tracks.append(track)
                    
                    # Toss it into the giant bucket if it's not in there yet
                    if vid not in processed_video_ids:
                        all_tracks_master.append(track)
                        processed_video_ids.add(vid)
                    
        # Sort this specific genre and grab its Top 100
        genre_tracks.sort(key=lambda x: x["weekly_views"], reverse=True)
        final_charts[genre] = genre_tracks[:100]

    except Exception as e:
        print(f"Error with {genre}: {e}")

# Build the combined "All Genres" Top 100
print("Building the combined Master Chart...")
all_tracks_master.sort(key=lambda x: x["weekly_views"], reverse=True)
final_charts["all_genres"] = all_tracks_master[:100]

# Save the multi-genre file
final_output = {
    "last_updated": today.strftime('%Y-%m-%d'),
    "charts": final_charts
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(final_output, f, indent=4)

print("Script complete!")
