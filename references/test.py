
from typing import Dict, Optional 
from urllib.parse import urlparse
import re
import os
from googleapiclient.discovery import build
from datetime import datetime
import isodate
from dotenv import load_dotenv
import requests
from bs4 import BeautifulSoup
import pandas as pd


response = requests.get("http://scihi.org/harry-coover-super-glue-cyanoacrylate/")
soup = BeautifulSoup(response.text, 'html.parser')

with open('output.html', 'w', encoding='utf-8') as f:
    f.write(soup.prettify())

    
from bs4 import BeautifulSoup

test_html = """
<html>
<head>
    <title>Harry Coover and the Invention of Super Glue | SciHi Blog</title>
    <meta property="og:title" content="Harry Coover and the Invention of Super Glue">
</head>
<body>
    <article>
        <h1 class="entry-title" itemprop="name">Harry Coover and the Invention of Super Glue</h1>
        <span class="vcard">
            <a class="url fn" href="http://scihi.org/author/tabea/">
                <i class="fa fa-user"></i>
                <span itemprop="author">Tabea Tietz</span>
            </a>
        </span>
        <time datetime="2022-03-06 06:00:40" itemprop="datePublished">6. March 2022</time>
    </article>
</body>
</html>
"""

soup = BeautifulSoup(test_html, 'html.parser')

# Test title extraction
title = soup.find('h1', class_='entry-title')
print("Title test:", title.text if title else "FAIL")  # Should get the h1 text

# Test author extraction
author_span = soup.find('span', itemprop='author')
print("Author span test:", author_span.text.strip() if author_span else "FAIL")  # Should get "Tabea Tietz"

# Test date extraction
time_tag = soup.find('time', datetime=True)
print("Date test:", time_tag['datetime'] if time_tag else "FAIL")  # Should get "2022-03-06..." 