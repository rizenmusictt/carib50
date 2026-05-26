import os
import json
import urllib.request
import urllib.parse
import re
from datetime import datetime, timedelta
import gspread
from google.oauth2.service_account import Credentials

# 1. Configuration
API_KEY = os.environ.get("YOUTUBE_API_KEY")
GOOGLE_CREDS_JSON = os.environ.get("GOOGLE_CREDENTIALS")
SPREADSHEET_ID = os.environ.get("SPREADSHEET_ID")
CURRENT_YEAR = datetime.utcnow().year

genres = ["soca", "dancehall", "bouyon"]
history = {}
is_first_run = True

# Artist/Genre Matrix
SEARCH_QUERIES = {
    "soca": f'("soca {CURRENT_YEAR}" OR "{CURRENT_YEAR} soca") OR "Machel Montano" OR "Bunji Garlin" OR "Kes" OR "Voice" OR "Patrice Roberts"',
    "dancehall": f'("dancehall {CURRENT_YEAR}" OR "{CURRENT_YEAR} dancehall") OR "Shenseea" OR "Skeng" OR "Ayetian" OR "Valiant" OR "Skillibeng" OR "Vybz Kartel" OR "Mavado" OR "Masicka" OR "Popcaan" OR "Teejay"',
    "bouyon": f'("bouyon {CURRENT_YEAR}" OR "{CURRENT_YEAR} bouyon") OR "Triple Kay" OR "Asa Bantan" OR "Ridge" OR "Signal Band"'
}

BLACKLIST = ["mix", "mixtape", "compilation", "dj", "type beat", "instrumental", "version", "edit", "karaoke"]

def get_seconds(d):
    m = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?', d)
    # Safeguard against malformed duration strings or live-stream edge cases
    if not m:
        return 0
    return (int(m.group(1) or 0) * 3600) + (int(m.group(2) or 0) * 60) + (int(m.group(3) or 0))

# 2. Initialization
creds = Credentials.from_service_account_info(json.loads(GOOGLE_CREDS_JSON), scopes=["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"])
sheet = gspread.authorize(creds).open_by_key(SPREADSHEET_ID)

if os.path.exists("data.json"):
    with open("data.json", "r") as f:
        data = json.load(f)
        for g in data.get("charts", {}):
            for t in data["charts"][g]: 
                history[t["id"]] = t.get("lifetime_views", 0)
            is_first_run = False

final_charts = {"charts": {}}
master_list = []

# 3. Processing
for genre in genres:
    genre_tracks = []
    params = {"part": "snippet", "q": SEARCH_QUERIES[genre], "type": "video", "order": "viewCount", "maxResults": 50, "key": API_KEY}
    
    with urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/search?{urllib.parse.urlencode(params)}") as r:
        res = json.loads(r.read().decode())
        ids = [i["id"]["videoId"] for i in res.get("items", [])]

    if not ids:
        final_charts["charts"][genre] = []
        continue

    with urllib.request.urlopen(f"https://www.googleapis.com/youtube/v3/videos?part=statistics,contentDetails&id={','.join(ids)}&key={API_KEY}") as r:
        stats = json.loads(r.read().decode())
        for item in stats.get("items", []):
            dur = get_seconds(item["contentDetails"].get("duration", ""))
            if dur < 60 or dur > 300: continue
            
            t = next(x for x in res["items"] if x["id"]["videoId"] == item["id"])
            if any(b in t["snippet"]["title"].lower() for b in BLACKLIST): continue
            
            views = int(item["statistics"].get("viewCount", 0))
            if views < 5000: continue
            
            track = {
                "id": item["id"], 
                "title": t["snippet"]["title"], 
                "channel": t["snippet"]["channelTitle"],
                "url": f"https://www.youtube.com/watch?v={item['id']}",
                "thumbnail": t["snippet"]["thumbnails"]["high"]["url"],
                "lifetime_views": views,
                "weekly_views": views if is_first_run else max(0, views - history.get(item["id"], 0))
            }
            genre_tracks.append(track)

    genre_tracks.sort(key=lambda x: x["weekly_views"], reverse=True)
    final_charts["charts"][genre] = genre_tracks  
    master_list.extend(genre_tracks)
    
    # Update Sheet (50 rows)
    try:
        ws = sheet.worksheet(genre)
        ws.batch_clear(["A2:G60"])
        if genre_tracks:
            ws.update("A2", [[i+1, t["title"], t["channel"], t["weekly_views"], t["id"], t["url"], t["thumbnail"]] for i, t in enumerate(genre_tracks)])
    except Exception as e:
        print(f"Error updating sheet for {genre}: {e}")

# 4. Master Sort & Save (25 for Website)
unique_master = {t["id"]: t for t in master_list}.values()
sorted_master = sorted(unique_master, key=lambda x: x["weekly_views"], reverse=True)

final_charts["charts"]["all_genres"] = sorted_master[:25]

with open("data.json", "w") as f:
    json.dump(final_charts, f, indent=4)