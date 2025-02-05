from typing import Dict, Optional 
from urllib.parse import urlparse
import re
import os
from googleapiclient.discovery import build
from datetime import datetime
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import pandas as pd
import json
from transformers import AutoTokenizer
from PyPDF2 import PdfReader
import io

load_dotenv()

tokenizer = AutoTokenizer.from_pretrained("gpt2")

# youtube setup stuff
API_KEY = os.getenv("YOUTUBE_API_KEY")
if not API_KEY:
    raise ValueError("YOUTUBE_API_KEY is not set in the environment variables")

youtube = build('youtube', 'v3', developerKey=API_KEY)



# classifying url to one of (youtube, pdf, doi, website)
def classify_url(url:str)-> Optional[Dict]:
    """
    Classify the URL into (youtube, pdf, doi, website) 
    """
    parsed = urlparse(url)
    doi_pattern = r'(10\.\d{4,}/[-._;()/:\w]+)'

    is_pdf = parsed.path.lower().endswith('.pdf') or '.pdf?' in parsed.path.lower()


    if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
        return youtube_handler(url)
    elif is_pdf:
        return pdf_handler(url)
    elif "doi.org" in parsed.netloc or re.search(doi_pattern,url):
        return doi_handler(url)
    else:
        return website_handler(url)


def youtube_handler(url:str) -> Dict:
    # extracing video id    
    patterns = [
        r'youtube\.com/watch\?v=([^&]+)',  # Standard watch URLs
        r'youtu\.be/([^?]+)',              # Shortened URLs
        r'youtube\.com/embed/([^?]+)',      # Embed URLs
    ]
    
    for pattern in patterns:
        if match := re.search(pattern, url):
            video_id = match.group(1)
            break

    if not video_id:
        raise ValueError("Invalid YouTube URL")

    # handling youtube api request
    response = youtube.videos().list(
        part='snippet,contentDetails',
        id=video_id
    ).execute()

    if not response['items']:
        raise ValueError("Video not found on YouTube")
    
    video = response['items'][0]
    snippet = video['snippet']

    upload_date = datetime.fromisoformat(snippet['publishedAt'].replace('Z', '+00:00'))
    formatted_date = upload_date.strftime('%b %d, %Y')

    # Create a short identifier from video title
    prompt = f"""Create a unique 5-8 character URL ending using letters a-z that relates to this content. 
    Return only JSON with a single field 'url_ending'.
    
    Examples of good url endings:
    "MIT Robotics. (21 May, 2023). Agile, robust, and multifunctional micro-aerial-robots" -> "agilerobust"
    "AsapSCIENCE. (19 Nov, 2022). This Is The First LIQUID Robot, And It's Unbelievable via Youtube" -> "liquidrobot"
    
    Content: {snippet['title']}"""
    
    url_ending = parse_reference(message(prompt))['url_ending']
    
    return {
        'title': snippet['title'],
        'author': snippet['channelTitle'],
        'date': formatted_date,
        'source':'YouTube',
        'original_url': url,
        'short_url': f"ve42.co/yt-{url_ending}"
    }


def doi_handler(url: str) -> Dict:
    """Extract metadata from DOI URL"""
    # Extract DOI from URL
    doi_pattern = r'(10\.\d{4,}/[^/]+(?:-\d+)?)'
    if match := re.search(doi_pattern, url):
        doi = match.group(1)
    else:
        raise ValueError("No valid DOI found in URL")
    
    
    # Query CrossRef API
    crossref_url = f"https://api.crossref.org/works/{doi}"
    response = requests.get(crossref_url, headers={'Accept': 'application/json'})
    
    if not response.ok:
        raise ValueError(f"DOI lookup failed: {response.status_code}")
    
    data = response.json()['message']
    
    # Format authors (can be multiple)
    authors = data.get('author', [])
    author_names = [f"{a.get('given', '')} {a.get('family', '')}" for a in authors]
    author_str = ", ".join(author_names) if author_names else "Unknown"

    
    # Get the publication date
    # Try print date first, then online date
    if print_date := data.get('published-print'):
        date_parts = print_date['date-parts'][0]  # Gets [2019, 6, 27]
    elif online_date := data.get('published-online'):
        date_parts = online_date['date-parts'][0]  # Fallback to online date
    else:
        date_parts = []
    
    # Format the date
    if len(date_parts) >= 3:
        # If we have year, month, day
        date_obj = datetime(date_parts[0], date_parts[1], date_parts[2])
        formatted_date = date_obj.strftime('%b %d, %Y')  # "Jun 27, 2019"
    elif len(date_parts) == 2:
        # If we only have year and month
        date_obj = datetime(date_parts[0], date_parts[1], 1)
        formatted_date = date_obj.strftime('%b %Y')  # "Jun 2019"
    elif date_parts:
        # If we only have year
        formatted_date = str(date_parts[0])  # "2019"
    else:
        formatted_date = "No date"
    
    prompt = f"""Create a unique 5-8 character URL ending using letters a-z that relates to this content. 
    Return only JSON with a single field 'url_ending'.
    
    Examples of good url endings:
    "United States Patent Office: US2776232. (Jan 1957) via US patent office" -> "patentb"
    "IEEE Spectrum. (20 May, 2020). RoBeetle: A Micro Robot Powered by Liquid Fuel" -> "robeetlefuel"
    
    Content: {data.get('title', [''])[0]}"""
    
    url_ending = parse_reference(message(prompt))['url_ending']
    
    return {
        'title': data.get('title', [''])[0],
        'author': author_str,
        'date': formatted_date,
        'source': data.get('container-title', [''])[0] or "Academic Paper",
        'original_url': url,
        'short_url': f"ve42.co/doi-{url_ending}"
    }



def website_handler(url: str) -> Dict:
    """Extract metadata from general websites and Wikipedia"""
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    if 'wikipedia.org' in url:
        return wikipedia_handler(soup, url)

    # Get the parsed data from LLM
    parsed_data = llm_parser(url)
    
    # Convert the date format if possible
    # try:
    #     date_obj = datetime.strptime(parsed_data['date'], '%Y-%m-%d')
    #     formatted_date = date_obj.strftime('%b %d, %Y')
    # except:
    #     formatted_date = parsed_data['date'] or 'No date'

    # Return in the same format as other handlers
    return {
        'title': parsed_data['title'],
        'author': '', # author is always Wikipedia contributors
        'date': '', # wikipedia has no date
        'source': parsed_data['source_organization'] or 'Website',
        'original_url': url,
        'short_url': f"ve42.co/web-{parsed_data.get('url_ending', urlparse(url).netloc)}"
    }

def parse_reference(text):
    # Find the JSON content between the triple backticks
    json_start = text.find('```json\n') + 8  # Skip past ```json\n
    json_end = text.find('```', json_start)
    json_str = text[json_start:json_end].strip()
    
    # Parse the JSON string into a Python dictionary
    return json.loads(json_str)


def message(text):
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            },
            data=json.dumps({
                "model": "minimax/minimax-01",
                "messages": [
                    {
                        "role": "system",
                        "content": "You are a JSON-only response bot. Always wrap your JSON in ```json\n and \n``` tags. Never include any other text."
                    },
                    {
                        "role": "user",
                        "content": (text)
                    }
                ]
            })
        )
        if response.status_code == 200:
            data = response.json()
            response_text = data['choices'][0]['message']['content']
            
            # Log the response to a file
            with open('llm_responses.txt', 'a', encoding='utf-8') as f:
                f.write(f"\n\n=== {datetime.now().isoformat()} ===\nPrompt:\n{text}\n\nResponse:\n{response_text}\n")
            
            print(f"{len(tokenizer.encode(text))} tokens")
            print(f"cost is {0.02*len(tokenizer.encode(text))/1000000} USD")
            return response_text
        else:
            print(f"Error: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")


def llm_parser(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    response = requests.get(url, headers=headers)
    html_content = response.text
    soup = BeautifulSoup(html_content, 'html.parser')
    prompt = f"""Return ONLY a JSON object wrapped in ```json tags. The JSON must contain:
    {{
        "title": "string - most prominent heading",
        "author": "string - personal or organizational", 
        "date": "string - YYYY-MM-DD format",
        "source_organization": "string - publisher/site owner",
        "url_ending": "string - unique 5-8 character ending using a-z"
    }}

    Examples of good url endings:
    "Kodak Eastman In Wikipedia" -> "kodake"
    "Electric Tram 1881 In Wikipedia" -> "tram"
    "Mullis, K. B. (1990). The Unusual Origin of the Polymerase Chain Reaction. Scientific American" -> "Mullis1990"
    "Rediscovering Yellowstone via UW-Madison" -> "Madison2017"

    RESPOND WITH ONLY THE JSON AND NOTHING ELSE
    
    Content: {soup.prettify()}"""
    answer = message(prompt)
    print(answer)
    json_answer = parse_reference(answer)
    return json_answer

def wikipedia_handler(soup: BeautifulSoup, url: str) -> Dict:
    """Special handler for Wikipedia articles"""
    title = soup.find('h1', {'id': 'firstHeading'}).text
    
    # Get last modified date
    # last_modified = soup.find('li', {'id': 'footer-info-lastmod'})
    # if last_modified:
    #     date_str = last_modified.text.replace('This page was last edited on ', '')
    #     try:
    #         date_obj = datetime.strptime(date_str, '%d %B %Y, at %H:%M')
    #         formatted_date = date_obj.strftime('%b %d, %Y')
    #     except:
    #         formatted_date = 'No date'
    # else:
    #     formatted_date = 'No date'
    
    prompt = f"""Create a unique 5-8 character URL ending using letters a-z that relates to this content. 
    Return only JSON with a single field 'url_ending'.
    
    Examples of good url endings:
    "Kodak Eastman In Wikipedia" -> "kodake"
    "Electric Tram 1881 In Wikipedia" -> "tram"
    "Water Quenched Steel In Wikipedia" -> "quench"
    
    Content: {title}"""
    
    url_ending = parse_reference(message(prompt))['url_ending']
    
    return {
        'title': title,
        'author': '',
        'date': '',
        'source': 'Wikipedia',
        'original_url': url,
        'short_url': f"ve42.co/wiki-{url_ending}"
    }


def pdf_handler(url:str) -> Dict:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    }

    response = requests.get(url,headers=headers)
    if not response.ok:
        raise ValueError(f"Failed to download PDF: {response.status_code}")

    pdf_file = io.BytesIO(response.content)
    pdf_reader = PdfReader(pdf_file)
    
    text_content = ""
    for i in range(min(3,len(pdf_reader.pages))):
        text_content += pdf_reader.pages[i].extract_text()
        

    prompt = f"""Analyze this PDF content snippet and return JSON with:
    - title (most prominent heading)
    - author (personal or organizational)
    - date (prioritize publication dates in YYYY-MM-DD format)
    - source_organization (publisher/site owner)
    - url_ending (create a unique 5-8 character ending using letters a-z that relates to the content)

    Examples of good url endings:
    "Overview of materials for Cyanoacrylate Adhesive" -> "matweb"
    "United States Patent Office: US2776232. (Jan 1957) via US patent office" -> "patentb"
    "IEEE Spectrum. (20 May, 2020). RoBeetle: A Micro Robot Powered by Liquid Fuel" -> "robeetlefuel"
    "Rediscovering Yellowstone via UW-Madison" -> "Madison2017"
 
    
    RESPOND WITH ONLY THE JSON AND NOTHING ELSE

    Content: {text_content}
    """

    parsed_data = parse_reference(message(prompt))

    try:
        date_obj = datetime.strptime(parsed_data['date'], '%Y-%m-%d')
        formatted_date = date_obj.strftime('%b %d, %Y')
    except:
        formatted_date = parsed_data['date'] or 'No date'
    
    # Generate a filename-based identifier for the short URL
    pdf_name = os.path.basename(urlparse(url).path)
    pdf_id = pdf_name.replace('.pdf', '').replace(' ', '-')
    
    return {
        'title': parsed_data['title'],
        'author': parsed_data['author'] or 'Unknown',
        'date': formatted_date,
        'source': parsed_data['source_organization'] or 'PDF Document',
        'original_url': url,
        'short_url': f"ve42.co/{parsed_data.get('url_ending', pdf_id)}"
    }

def format_references(csv_file: str, output_file: str):
    """Format references from CSV into a bibliography-style text file."""
    # Read CSV with empty strings instead of NaN
    df = pd.read_csv(csv_file, na_values=[], keep_default_na=False)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("References:\n\n")
        
        for _, row in df.iterrows():
            # Skip entries marked as ERROR
            if row['title'] == 'ERROR':
                continue
                
            # Format the reference line
            if row['author'] and row['date']:
                # Full reference with author and date
                ref = f"{row['author']} ({row['date']}). {row['title']}. "
            else:
                # Simplified reference without author/date
                ref = f"{row['title']} "
            
            # Add source if available
            if row['source'] and row['source'] != 'Website':
                ref += f"{row['source']} - "
                
            # Add URL
            ref += f"{row['short_url']}\n"
            
            f.write(ref)

if __name__ == "__main__":
    # Read links from file
    with open("urls.txt","r") as f:
        links = [line.strip() for line in f if line.strip()]
    
    # Store results
    results = []
    
    # Process each link
    for url in links:
        try:
            print(f"Processing: {url}")
            result = classify_url(url)
            results.append(result)
            print(result)
        except Exception as e:
            print(f"Error processing {url}: {e}")
            # Add failed URLs to results with error message
            results.append({
                'title': 'ERROR',
                'author': str(e),
                'date': '',
                'source': '',
                'original_url': url,
                'short_url': ''
            })
    
    # Convert to DataFrame and save
    df = pd.DataFrame(results)
    df.to_csv('references.csv', index=False)
    print(f"\nSaved {len(results)} results to references.csv")
    
    # After saving the CSV, format the references
    format_references('references.csv', 'formatted_references.txt')
    print("Formatted references saved to formatted_references.txt")

    
