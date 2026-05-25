import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta

# 1. Get the hidden API key
API_KEY = os.environ.get("YOUTUBE_API_KEY")

if not API_KEY:
    print("Error: YOUTUBE_API_KEY environment variable is missing.")
    exit(1)

# 2. Set our timeframes
today = datetime.utcnow()
# Limit search to songs uploaded in the last 4 months (approx 120 days)
four_months_ago = today - timedelta(days=120)
published_after = four_months_ago.strftime('%Y-%m-%dT%H:%M:%SZ')

current_year = today.year
genres = ["soca", "dancehall", "reggae", "bouyon", "afrobeats"]

# 3. Load the "Memory" (Last week's data)
history = {}
is_first_run = True

try:
    if os.path.exists("data.json"):
        with open("data.json", "r", encoding="utf-8") as f:
            old_data = json.load(f)
            # Create a dictionary of past views: { "VideoID": 1500000 }
            for track in old_data.get("chart", []):
                history[track["id"]] = track["lifetime_views"]
        is_first_run = False
        print("Loaded previous week's data for velocity tracking.")
except Exception as e:
    print("No previous data found or error loading. Running as Week 1 Initialization.")

all_tracks = []
video_ids = []
video_snippets = {}

# 4. Search YouTube for top tracks from the last 4 months
for genre in genres:
    search_query = f"{genre} {current_year}"
    print(f"Fetching 4-month data for: {search_query}...")
    
    search_params = urllib.parse.urlencode({
        "part": "snippet",
        "q": search_query,
        "type": "video",
        "order": "viewCount",
        "publishedAfter": published_after,
        "maxResults": 50, # Pulling a wider net (50) to make sure we catch fast-rising songs
        "key": API_KEY
    })
    search_url = f"https://www.googleapis.com/youtube/v3/search?{search_params}"
    
    try:
        with urllib.request.urlopen(search_url) as response:
            search_data = json.loads(response.read().decode())
            
            for item in search_data.get("items", []):
                vid = item["id"]["videoId"]
                if vid not in video_ids: # Prevent duplicates if a song hits two genres
                    video_ids.append(vid)
                    video_snippets[vid] = {
                        "id": vid,
                        "title": item["snippet"]["title"],
                        "channel": item["snippet"]["channelTitle"],
                        "genre": genre,
                        "url": f"https://www.youtube.com/watch?v={vid}",
                        "thumbnail": item["snippet"]["thumbnails"]["high"]["url"]
                    }
    except Exception as e:
        print(f"Error fetching search data for {genre}: {e}")

# 5. Chunk the Video IDs (YouTube only lets us ask for 50 specific stats at a time)
chunk_size = 50
chunks = [video_ids[i:i + chunk_size] for i in range(0, len(video_ids), chunk_size)]

for chunk in chunks:
    stats_params = urllib.parse.urlencode({
        "part": "statistics",
        "id": ",".join(chunk),
        "key": API_KEY
    })
    stats_url = f"https://www.googleapis.com/youtube/v3/videos?{stats_params}"
    
    try:
        with urllib.request.urlopen(stats_url) as stats_response:
            stats_data = json.loads(stats_response.read().decode())
            
            for item in stats_data.get("items", []):
                vid = item["id"]
                current_views = int(item["statistics"].get("viewCount", 0))
                
                track_info = video_snippets[vid]
                track_info["lifetime_views"] = current_views
                
                # 6. THE VELOCITY MATH
                if is_first_run:
                    # Week 1: Rank by total views over the last 4 months
                    views_this_week = current_views
                else:
                    # Week 2+: Rank by (Current Views - Last Week's Views)
                    # If the song is brand new to our radar, we count its current views
                    past_views = history.get(vid, 0)
                    views_this_week = current_views - past_views
                    
                    # Prevent negative numbers if YouTube purges bot views
                    if views_this_week < 0:
                        views_this_week = 0

                track_info["weekly_views"] = views_this_week
                # Points are based strictly on this week's momentum
                track_info["points"] = views_this_week * 1.0 
                
                all_tracks.append(track_info)
                
    except Exception as e:
        print(f"Error fetching stats for chunk: {e}")

# 7. Sort by highest momentum (weekly views)
all_tracks.sort(key=lambda x: x["points"], reverse=True)

# 8. Trim to the Top 100
top_100 = all_tracks[:100]

# 9. Save the results (This becomes the memory for next week)
final_output = {
    "last_updated": today.strftime('%Y-%m-%d %H:%M:%S UTC'),
    "chart_type": "Velocity (7-Day)" if not is_first_run else "Initial Baseline (4-Month)",
    "chart": top_100
}

with open("data.json", "w", encoding="utf-8") as f:
    json.dump(final_output, f, indent=4)

print(f"Successfully saved {len(top_100)} tracks to data.json!")
