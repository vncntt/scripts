from googleapiclient.discovery import build
import pandas as pd
import os
from dotenv import load_dotenv
import html  # Add this import at the top
import re

load_dotenv()

# Get API key from environment variable
API_KEY = os.getenv('YOUTUBE_API_KEY')

# Create YouTube API client
youtube = build('youtube', 'v3', developerKey=API_KEY)

def get_channel_videos():
    # Veritasium's channel ID
    channel_id = 'UCHnyfMqiRRG1u-2MsSQLbXA'
    
    videos = []
    next_page_token = None
    
    while True:
        # Get channel videos
        request = youtube.search().list(
            part='snippet',
            channelId=channel_id,
            maxResults=50,
            order='date',
            type='video',
            pageToken=next_page_token
        )
        response = request.execute()
        
        # Get video durations in batch
        video_ids = [item['id']['videoId'] for item in response['items']]
        videos_details = youtube.videos().list(
            part='contentDetails',
            id=','.join(video_ids)
        ).execute()
        
        # Create duration lookup dictionary
        duration_lookup = {
            item['id']: item['contentDetails']['duration'] 
            for item in videos_details['items']
        }
        
        # Extract video information, excluding shorts
        for item in response['items']:
            video_id = item['id']['videoId']
            duration = duration_lookup.get(video_id, '')
            
            # Convert duration to seconds (PT1M30S -> 90)
            duration_sec = 0
            minutes = re.search(r'(\d+)M', duration)
            seconds = re.search(r'(\d+)S', duration)
            
            if minutes:
                duration_sec += int(minutes.group(1)) * 60
            if seconds:
                duration_sec += int(seconds.group(1))
            
            # Skip if duration is less than 61 seconds (shorts are usually 60 sec or less)
            if duration_sec <= 60:
                continue
                
            video = {
                'title': html.unescape(item['snippet']['title']),
                'video_id': video_id
            }
            videos.append(video)
        
        # Check if there are more pages
        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break
    
    # Create DataFrame and save to CSV
    df = pd.DataFrame(videos)
    df.to_csv('veritasium_videos.csv', index=False)
    print(f"Saved {len(videos)} videos to veritasium_videos.csv")

if __name__ == "__main__":
    get_channel_videos() 