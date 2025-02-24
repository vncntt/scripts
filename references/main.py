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

# Clear llm_responses.txt at startup
with open('llm_responses.txt', 'w', encoding='utf-8') as f:
    f.write(f"=== New Run Starting {datetime.now().isoformat()} ===\n")

tokenizer = AutoTokenizer.from_pretrained("gpt2")

# youtube setup stuff
API_KEY = os.getenv("YOUTUBE_API_KEY")
if not API_KEY:
    raise ValueError("YOUTUBE_API_KEY is not set in the environment variables")

youtube = build('youtube', 'v3', developerKey=API_KEY)

def classify_url(url:str)-> Optional[Dict]:
    """
    Classify the URL into (youtube, pdf, doi, website) 
    """
    parsed = urlparse(url)
    doi_pattern = r'(10\.\d{4,}/[-._;()/:\w]+)'

    is_pdf = parsed.path.lower().endswith('.pdf') or '.pdf?' in parsed.path.lower()

    is_wikipedia = "wikipedia.org" in parsed.netloc


    if "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc:
        return youtube_handler(url)
    elif is_pdf:
        return pdf_handler(url)
    elif "doi.org" in parsed.netloc or re.search(doi_pattern,url):
        return doi_handler(url)
    elif is_wikipedia:
        return wikipedia_handler(url)
    else:
        return website_handler(url) # classifies into wikipedia, website or after

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

    url_ending = ''.join(c for c in snippet['title'].lower() if c.isalnum())[:8] 
   
    return {
        'source_type': 'youtube',
        'title': snippet['title'],
        'author': snippet['channelTitle'],
        'date': formatted_date,
        'source':'YouTube',
        'original_url': url,
        'short_url': f"ve42.co/{url_ending}"
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
    
    # Add defensive handling for title
    title = data.get('title', [])
    if isinstance(title, list):
        title = title[0] if title else "UNKNOWN"
    
    # Format authors (can be multiple)
    authors = data.get('author', [])
    if isinstance(authors, list):
        author_names = [f"{a.get('given', '')} {a.get('family', '')}" for a in authors]
        author_str = ", ".join(author_names) if author_names else "UNKNOWN"
    else:
        author_str = "UNKNOWN"

    
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

   
    
    container_title = data.get('container-title', [''])
    source = container_title[0] if container_title else "SOURCE NOT FOUND"
    
    url_ending = ''.join(c for c in data.get('title', [''])[0].lower() if c.isalnum())[:8]

    return {
        'source_type': 'doi',
        'title': title,
        'author': author_str,
        'date': formatted_date,
        'source': source,
        'original_url': url,
        'short_url': f"ve42.co/{url_ending}"
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
    for i in range(min(5,len(pdf_reader.pages))):
        text_content += pdf_reader.pages[i].extract_text()

    prompt = f"""Analyze this PDF content snippet and return JSON with:
    - title (most prominent heading)
    - author (personal or organizational)
    - date (prioritize publication dates in YYYY-MM-DD format)
    - source_organization (publisher/site owner)
    
    RESPOND WITH ONLY THE JSON AND NOTHING ELSE. 

    Examples of good responses:
    ```json
    {{
        "title": "The Development of the Electron Microscope and of Electron Microscopy",
        "author": "Ernst Ruska",
        "date": "1986-12-08",
        "source_organization": "Nobel Foundation"
    }}
    ```
    ```json
    {{
        "title": "Scherzer's Theorem",
        "author": "CEOS GmbH",
        "date": "2023-10-04",
        "source_organization": "CEOS GmbH"
    }}
    ```
    END OF EXAMPLES

    Content: {text_content}
    """
    parsed_data = parse_reference(message(prompt))

    if parsed_data is None:
        return {
            'source_type': 'pdf',
            'title': 'Failed to parse PDF',
            'author': 'Unknown',
            'date': '',
            'source': 'Unknown',
            'original_url': url,
            'short_url': f"ve42.co/error"
        }

    try:
        date_obj = datetime.strptime(parsed_data['date'], '%Y-%m-%d')
        formatted_date = date_obj.strftime('%b %d, %Y')
    except:
        formatted_date = parsed_data['date'] or 'No date'
    
    # Generate a filename-based identifier for the short URL
    pdf_name = os.path.basename(urlparse(url).path)
    pdf_id = pdf_name.replace('.pdf', '').replace(' ', '-')
    

    return {
        'source_type': 'pdf',
        'title': parsed_data['title'],
        'author': parsed_data['author'] or 'Unknown',
        'date': formatted_date,
        'source': parsed_data['source_organization'] or 'PDF Document',
        'original_url': url,
        'short_url': f"ve42.co/{pdf_id}"
    }

def wikipedia_handler(url: str) -> Dict:
    """Special handler for Wikipedia articles"""
    response = requests.get(url)
    soup = BeautifulSoup(response.text, 'html.parser')
    title = soup.find('h1', {'id': 'firstHeading'}).text
    
    url_ending = ''.join(c for c in title.lower() if c.isalnum())[:8]
    
    return {
        'source_type': 'wikipedia',
        'title': title,
        'author': '',
        'date': '',
        'source': 'Wikipedia',
        'original_url': url,
        'short_url': f"ve42.co/{url_ending}"
    }

def filter_content(html_content):
    # First remove CSS/styling content
    css_pattern = r'<style[^>]*>[\s\S]*?</style>'
    filtered_content = re.sub(css_pattern, '', html_content)
    
    # Extract text from HTML tags while preserving important content
    soup = BeautifulSoup(filtered_content, 'html.parser')
    
    # Convert HTML to plain text while preserving structure
    for tag in soup.find_all(['em', 'strong']):
        # Replace italics/bold tags with their text
        tag.unwrap()
        
    # Remove any remaining HTML tags but keep their text content
    text_content = soup.get_text(separator=' ', strip=True)
    
    # Clean up extra whitespace
    text_content = re.sub(r'\s+', ' ', text_content)
    
    return text_content.strip()

def website_handler(url: str) -> Dict:
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    response = requests.get(url, headers=headers)
    html_content = response.text
    filtered_content = filter_content(html_content)
    soup = BeautifulSoup(filtered_content, 'html.parser')
    prompt = f"""Return ONLY a JSON object wrapped in ```json tags. The JSON must contain:
    {{
        "title": "string - most prominent heading",
        "author": "string - personal or organizational", 
        "date": "string - YYYY-MM-DD format",
        "source_organization": "string - publisher/site owner",
    }}

    RESPOND WITH ONLY THE JSON AND NOTHING ELSE. If you don't find one of the fields, return NOT_FOUND as the value.
    
    Content: {soup.prettify()}"""
    answer = message(prompt)
    print(answer)
    parsed_data = parse_reference(answer)
    
    # Add error handling for None response
    if parsed_data is None:
        return {
            'source_type': 'website',
            'title': 'Failed to parse webpage',
            'author': 'Unknown',
            'date': '',
            'source': 'Unknown',
            'original_url': url,
            'short_url': f"ve42.co/error"
        }
        
    url_ending = ''.join(c for c in parsed_data['title'].lower() if c.isalnum())[:8]
    return {
        'source_type': 'website',
        'title': parsed_data['title'],
        'author': parsed_data['author'],
        'date': parsed_data['date'],
        'source': parsed_data['source_organization'],
        'original_url': url,
        'short_url': f"ve42.co/{url_ending}"
    }
    


def parse_reference(text):
    # Find the JSON content between the triple backticks
    json_start = text.find('```json')
    json_end = text.find('```', json_start + 7)
    
    if json_start != -1 and json_end != -1:
        try:
            # Clean up the text before parsing
            json_text = text[json_start + 7:json_end].strip()
            return json.loads(json_text)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON: {json_text}")
            return None
    return None


def message(text:str)->str:
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            },
            data=json.dumps({
                "model": "qwen/qwen-turbo",
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
            
            # Validate we got a non-empty response
            if not response_text or response_text.isspace():
                print("Warning: Received empty response from LLM")
                return None
                
            with open('llm_responses.txt', 'a', encoding='utf-8') as f:
                f.write(f"\n\n=== {datetime.now().isoformat()} ===\nPrompt:\n{text}\n\nResponse:\n{response_text}\n")
            
            print(f"{len(tokenizer.encode(text))} tokens")
            print(f"cost is {0.02*len(tokenizer.encode(text))/1000000} USD")
 
            return response_text
        else:
            print(f"Error: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")
        
def final_check(text:str)->str:
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENROUTER_API_KEY')}",
            },
            data=json.dumps({
                "model": "anthropic/claude-3.5-sonnet",
                "messages": [
                    {
                        "role": "system",
                        "content": """You are a reference formatting assistant. 
                                - Fix any text that is in ALL CAPS to use proper capitalization (title case for titles, sentence case for other text). 
                                - Do not uncapitalize UNKNOWN or SOURCE NOT FOUND.
                                - If a term should legitimately be in all caps (like acronyms), leave it unchanged.

                                - For sources with more than three authors rather than list them all after the first author put et al.
                                - For example:
                                "Jay J. Meyers, Anthony Herrel, James Birch" should be "Jay J. Meyers et al."

                                - If there is overlapping punctuation like "?.", then remove the period.

                                - If a url ending is messy like ve42.co/Meyers%20et%20al%202002%20Topics, then clean up it to be something like ve42.co/meyers20topics
                                - The url endings are only supposed to have lower case letters and numbers. If there are any other characters, clean it up.

                                
                                Do not change anything else.
                                Do not make any changes that are not in one of the categories above. 
                                Respond with ONLY the corrected text and nothing else.
                                """
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
            
            print(response_text)
            print(f"{len(tokenizer.encode(text))} tokens")
            print(f"cost is {0.02*len(tokenizer.encode(text))/1000000} USD")

            with open('llm_responses.txt', 'a', encoding='utf-8') as f:
                f.write(f"\n\n=== {datetime.now().isoformat()} ===\nPrompt:\n{text}\n\nResponse:\n{response_text}\n")
 
            return response_text
        else:
            print(f"Error: {response.status_code}")
    except Exception as e:
        print(f"Error: {e}")
 

def format_references(csv_file: str, output_file: str):
    """Format references from CSV into a text file."""
    # Read CSV with empty strings instead of NaN
    df = pd.read_csv(csv_file, na_values=[], keep_default_na=False)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write("References:\n\n")
        
        for _, row in df.iterrows():
            ref = "" 
            if row['source_type'] == 'youtube':
                ref = f"{row['title']}. {row['author']}. {row['original_url']}\n"
            elif row['source_type'] == 'wikipedia':
                ref = f"{row['title']}. {row['original_url']}\n"
            elif row['source_type'] == 'website':
                ref = f"{row['title']}. {row['short_url']}\n"
            elif row['source_type'] == 'pdf' or 'doi':
                ref = f"{row['author']} ({row['date']}). {row['title']}. {row['source']} - {row['short_url']}\n"

            ref = final_check(ref)
            f.write(ref + "\n")


if __name__ == "__main__":
    # Read links from file
    with open("urls.txt","r") as f:
        links = [line.strip() for line in f if line.strip()]

    results = []
    
    for url in links:
        try:
            print(f"Processing: {url}")
            result = classify_url(url)
            results.append(result)
            print(result)
        except Exception as e:
            print(f"Error processing {url}: {e}")
            results.append({
                'source_type': 'ERROR',
                'title': 'ERROR',
                'author': str(e),
                'date': '',
                'source': '',
                'original_url': url,
                'short_url': ''
            })
    
    # Store results
    df = pd.DataFrame(results)
    df.to_csv('references.csv', index=False)
    print(f"\nSaved {len(results)} results to references.csv")

    format_references('references.csv', 'references.txt')
    print("Saved references to references.txt")
    