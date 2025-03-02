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
import time
import streamlit as st
import base64

# For local development
try:
    load_dotenv()
except:
    pass  # Ignore if .env file doesn't exist

# For Streamlit Cloud - access secrets
def get_api_key(key_name):
    if key_name in st.secrets:
        return st.secrets[key_name]
    return os.getenv(key_name)  # Fallback to environment variable

# Set up page configuration
st.set_page_config(
    page_title="Reference Formatter",
    page_icon="📚",
    layout="wide"
)

# Initialize session state variables if they don't exist
if 'results' not in st.session_state:
    st.session_state.results = []
if 'references_text' not in st.session_state:
    st.session_state.references_text = ""
if 'processed' not in st.session_state:
    st.session_state.processed = False

# Store llm responses in memory
if 'llm_responses' not in st.session_state:
    st.session_state.llm_responses = [f"=== New Run Starting {datetime.now().isoformat()} ===\n"]

# Create a file in memory for llm_responses
def update_llm_log(text):
    st.session_state.llm_responses.append(text)

tokenizer = AutoTokenizer.from_pretrained("gpt2")

# youtube setup stuff
@st.cache_resource
def setup_youtube_api():
    API_KEY = get_api_key("YOUTUBE_API_KEY")
    if not API_KEY:
        st.error("YOUTUBE_API_KEY is not set in the environment variables. YouTube references won't work.")
        return None
    return build('youtube', 'v3', developerKey=API_KEY)

youtube = setup_youtube_api()

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
        r'youtube\.com/shorts/([^?]+)',     # Shorts URLs
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
    pdf_id = ''.join(c for c in pdf_name.lower() if c.isalnum())[:8]

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
        api_key = get_api_key('OPENROUTER_API_KEY')
        if not api_key:
            st.error("OpenRouter API key not found. Please add it to your .env file.")
            return None
            
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
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
                st.warning("Received empty response from LLM")
                return None
                
            # Log the response
            log_text = f"\n\n=== {datetime.now().isoformat()} ===\nPrompt:\n{text}\n\nResponse:\n{response_text}\n"
            update_llm_log(log_text)
            
            tokens = len(tokenizer.encode(text))
            cost = 0.02 * tokens / 1000000
            
            return response_text
        else:
            st.error(f"API Error: {response.status_code}")
    except Exception as e:
        st.error(f"Error: {e}")
        
def final_check(text:str)->str:
    try:
        api_key = get_api_key('OPENROUTER_API_KEY')
        if not api_key:
            st.error("OpenRouter API key not found. Please add it to your .env file.")
            return text
            
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
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

                                - If there are excessive hashtags or other irrelavent items in the title, remove them.
                                - Example: "Who Can Jump Bigger Part #2 #viral #horse #jumping #cute #equestrian #dog?" should be "Who Can Jump Bigger"

                                
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
            
            # Log the response
            log_text = f"\n\n=== {datetime.now().isoformat()} ===\nPrompt:\n{text}\n\nResponse:\n{response_text}\n"
            update_llm_log(log_text)
            
            return response_text
        else:
            st.error(f"API Error: {response.status_code}")
            return text
    except Exception as e:
        st.error(f"Error: {e}")
        return text
 

def format_references(results):
    """Format references from results list into text."""
    references_text = "References:\n\n"
    
    for row in results:
        ref = "" 
        if row['source_type'] == 'youtube':
            ref = f"{row['author']}. {row['title']}. {row['original_url']}\n"
        elif row['source_type'] == 'wikipedia':
            ref = f"{row['title']}. {row['original_url']}\n"
        elif row['source_type'] == 'website':
            ref = f"{row['title']}. {row['short_url']}\n"
        elif row['source_type'] == 'pdf' or row['source_type'] == 'doi':
            ref = f"{row['author']} ({row['date']}). {row['title']}. {row['source']} - {row['short_url']}\n"

        ref = final_check(ref)
        references_text += ref + "\n"
    
    return references_text

def process_urls(urls):
    """Process a list of URLs and return results."""
    results = []
    progress_bar = st.progress(0)
    
    for i, url in enumerate(urls):
        try:
            st.write(f"Processing: {url}")
            result = classify_url(url)
            results.append(result)
            # Update progress
            progress_bar.progress((i + 1) / len(urls))
        except Exception as e:
            st.error(f"Error processing {url}: {e}")
            results.append({
                'source_type': 'ERROR',
                'title': 'ERROR',
                'author': str(e),
                'date': '',
                'source': '',
                'original_url': url,
                'short_url': ''
            })
    
    return results

def get_download_link(df, filename, text):
    """Generates a link to download the dataframe as a CSV file."""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    href = f'<a href="data:file/csv;base64,{b64}" download="{filename}">Download {text}</a>'
    return href

def get_text_download_link(text, filename, link_text):
    """Generates a link to download text as a file."""
    b64 = base64.b64encode(text.encode()).decode()
    href = f'<a href="data:file/txt;base64,{b64}" download="{filename}">{link_text}</a>'
    return href

def main():
    st.title("Reference Formatter 📚")
    st.write("Enter URLs (one per line) to generate formatted references.")
    
    # Input area for URLs
    urls_input = st.text_area("Enter URLs (one per line):", height=200)
    
    # Process button
    if st.button("Process URLs"):
        if not urls_input.strip():
            st.warning("Please enter at least one URL.")
        else:
            urls = [url.strip() for url in urls_input.split('\n') if url.strip()]
            
            with st.spinner("Processing URLs..."):
                st.session_state.results = process_urls(urls)
                
                # Format references
                st.session_state.references_text = format_references(st.session_state.results)
                
                # Mark as processed
                st.session_state.processed = True
            
            st.success(f"Processed {len(urls)} URLs!")
    
    # Display results if processed
    if st.session_state.processed and st.session_state.results:
        st.header("Results")
        
        # Convert results to DataFrame
        df = pd.DataFrame(st.session_state.results)
        
        # Display results in a table
        st.dataframe(df)
        
        # Generate download links
        st.markdown(get_download_link(df, "references.csv", "References CSV"), unsafe_allow_html=True)
        
        # Create link_generation.csv
        link_df = pd.DataFrame(st.session_state.results)[['original_url', 'short_url']]
        # Remove 've42.co/' prefix from short_url column only if not error
        link_df.loc[link_df['short_url'] != 've42.co/error', 'short_url'] = \
            link_df.loc[link_df['short_url'] != 've42.co/error', 'short_url'].str.replace('ve42.co/', '')
        
        st.markdown(get_download_link(link_df, "link_generation.csv", "Link Generation CSV"), unsafe_allow_html=True)
        
        # Display formatted references
        st.header("Formatted References")
        st.text_area("References:", st.session_state.references_text, height=300)
        
        st.markdown(get_text_download_link(st.session_state.references_text, "references.txt", "Download References Text"), unsafe_allow_html=True)
        
        # Display LLM API logs if expanded
        with st.expander("View LLM API Logs"):
            st.text("".join(st.session_state.llm_responses))
            st.markdown(get_text_download_link("".join(st.session_state.llm_responses), "llm_responses.txt", 
                                              "Download LLM Logs"), unsafe_allow_html=True)

if __name__ == "__main__":
    main()
    