from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import csv
import time
import sys

def scrape_curius(url):
    options = webdriver.ChromeOptions()
    options.add_argument('--headless')
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
    
    try:
        print("Loading initial page...")
        driver.get(url)
        bookmarks = []
        page = 1
        
        while True:
            print(f"\nProcessing page {page}...")
            time.sleep(5)
            
            # Scrape current page
            link_containers = driver.find_elements(By.CLASS_NAME, "css-1so9d0e")
            print(f"Found {len(link_containers)} link containers on page {page}")
            
            for container in link_containers:
                try:
                    # Get title and URL first
                    elements = container.find_elements(By.XPATH, ".//*")
                    url = None
                    title = None
                    for element in elements:
                        if element.tag_name == "a":
                            url = element.get_attribute('href')
                            title = element.text.strip()
                            break
                    
                    if url and title:
                        # Try to get timestamp, but don't fail if we can't find it
                        timestamp = ""
                        relative_time = ""
                        try:
                            parent = container.find_element(By.XPATH, "./ancestor::div[contains(@class, 'css-1eicj7r')]")
                            time_element = parent.find_element(By.TAG_NAME, "time")
                            timestamp = time_element.get_attribute('datetime')
                            relative_time = time_element.text.strip()
                        except Exception as e:
                            print(f"Couldn't find time for entry: {title}")
                        
                        bookmarks.append({
                            'title': title,
                            'url': url,
                            'timestamp': timestamp,
                            'relative_time': relative_time
                        })
                        print(f"Successfully processed: {title} ({relative_time if relative_time else 'no time found'})")
                
                except Exception as e:
                    print(f"Skipping one entry due to: {str(e)}")
                    continue
            
            # Look for next button
            try:
                next_container = driver.find_element(By.CLASS_NAME, "css-gsabod")
                next_span = next_container.find_element(By.XPATH, ".//span[@style='visibility: visible;'][text()='next']")
                
                if next_span.is_displayed():
                    next_span.click()
                    page += 1
                    print(f"Moving to page {page}...")
                    time.sleep(5)
                else:
                    print("Next button not visible - reached last page")
                    break
                    
            except Exception as e:
                print(f"No next button found: {str(e)}")
                break
        
        print(f"\nFinished scraping {page} pages!")
        return bookmarks
    
    finally:
        driver.quit()

def save_to_csv(bookmarks, filename='curius_bookmarks.csv'):
    with open(filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['title', 'url', 'timestamp', 'relative_time'])
        writer.writeheader()
        writer.writerows(bookmarks)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scrape_curius.py curius.app/USERNAME")
        sys.exit(1)
    
    url = sys.argv[1]
    # Strip https:// if provided
    url = url.replace("https://", "")
    url = f"https://{url}"
    
    if not url.startswith("https://curius.app/"):
        print("Error: URL must be in format curius.app/USERNAME")
        sys.exit(1)
        
    bookmarks = scrape_curius(url)
    if bookmarks:
        save_to_csv(bookmarks)
        print(f"\nSuccessfully scraped {len(bookmarks)} bookmarks!")
    else:
        print("No bookmarks found!")
