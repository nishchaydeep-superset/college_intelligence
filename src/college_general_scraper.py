#!/usr/bin/env python3
import json
import time
import re
import sys
import os
import argparse
import logging
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlparse

try:
    import undetected_chromedriver as uc
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    sys.exit("Missing dependencies. Run: pip install undetected-chromedriver selenium beautifulsoup4")

try:
    from bs4 import BeautifulSoup, Tag
except ImportError:
    sys.exit("Missing beautifulsoup4. Run: pip install beautifulsoup4")

# Configure logging
os.makedirs("logs", exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/general_scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# Config constants
INPUT_FILE = "data/college_urls.json"
OUTPUT_FILE = "data/college_general_data.json"
PAGE_LOAD_WAIT = 15
SCROLL_PAUSE = 1.5


class CollegeGeneralScraper:
    """Scraper to extract non-placement details (reviews, rankings, fees, general info)"""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self.driver = None
        self.cached_data = {}
        self.all_college_names = []
        self.load_college_names()
        self.load_cache()

    def load_college_names(self):
        """Load all college names from input file for filtering cross-promotional content"""
        if os.path.exists(INPUT_FILE):
            try:
                with open(INPUT_FILE, 'r', encoding='utf-8') as f:
                    colleges = json.load(f)
                    self.all_college_names = [c["name"] for c in colleges if "name" in c]
                logger.info(f"Loaded {len(self.all_college_names)} college names for ad-filtering")
            except Exception as e:
                logger.error(f"Error loading college names: {str(e)}")

    def load_cache(self):
        """Load already crawled colleges from output file if it exists"""
        if os.path.exists(OUTPUT_FILE):
            try:
                with open(OUTPUT_FILE, 'r', encoding='utf-8') as f:
                    self.cached_data = json.load(f)
                logger.info(f"Loaded existing cache with {len(self.cached_data)} colleges")
                
                # Automatically clean up any generic advertisements or unrelated college spam from the cache
                self.cleanup_cache()
                # Save the cleanly updated cache back to disk
                self.save_cache()
            except Exception as e:
                logger.error(f"Error loading existing cache file: {str(e)}")
                self.cached_data = {}

    def is_other_college(self, text: str, current_college: Optional[str]) -> bool:
        """Check if the text represents another college (to filter out cross-promotional sidebar links)"""
        if not text or not self.all_college_names:
            return False
        
        text_lower = text.lower().strip()
        
        # Normalize current college name
        current_lower = current_college.lower().strip() if current_college else ""
        
        for name in self.all_college_names:
            name_lower = name.lower().strip()
            # If the name is exactly the current college or its subset, skip it (we want to keep current college info)
            if current_lower and (name_lower in current_lower or current_lower in name_lower):
                continue
            
            # If the heading matches another college name exactly or is a very close match
            if name_lower == text_lower or (len(name_lower) > 10 and name_lower in text_lower):
                return True
                
        return False

    def cleanup_cache(self):
        """Clean up advertisement copy, promo items, and unrelated colleges' boilerplate from existing cached data"""
        logger.info("Running automatic advertisement and promotional copy cleanup on cache...")
        cleaned_count = 0
        
        ad_keywords = [
            "convenience of your phone", "detailed books and sample papers", "regular exam updates",
            "best college recommendations", "college & rank predictors", "question and answers",
            "student community: where questions", "where questions find answers", "all this at the convenience",
            "download mobile app", "install app", "by stream", "write a review", "get matching colleges",
            "apply to check the best colleges", "click on apply to check", "best colleges that might interest you",
            "top government universities in", "top government colleges in", "government universities in",
            "government colleges in", "accepting applications", "admissions 2026 open", "admissions open",
            "last date to apply", "apply now", "vit bhopal", "lovely professional", "lpu", "sharda university",
            "amity university", "upes", "chitkara", "chandigarh university", "nims university",
            "manipal university", "dy patil", "srm university", "bennett university", "diamond rated",
            "naac a+ accredited", "naac a++ grade", "recruitment partners", "job offers", "highest package 1.6 cr",
            "highest ctc", "avail 50% waiver", "brochure", "download brochure", "select course",
            "read more", "all rights reserved", "cookie policy", "terms and conditions", "contact us",
            "site map", "privacy policy",
            # User specific items:
            "reliance infrastructure", "foodvista", "lebua hotels", "accenture services",
            "reliance infrastructure limited", "foodvista india private", "lebua hotels and resorts",
            "accenture services private limited",
        ]

        skip_headings = [
            "login", "register", "apply now", "download", "accepting applications", "top institutes", 
            "accepting application", "senior executive vice pre", "advisor", "ceo", "managing director - tech",
            "by stream", "student community", "convenience of your phone", "sample papers", 
            "exam updates", "college recommendations", "rank predictors", "question and answers"
        ]

        # Deep clean the cache structure
        for college, sources in list(self.cached_data.items()):
            for source_name, source_data in list(sources.items()):
                if not isinstance(source_data, dict):
                    continue
                for page_type, page_data in list(source_data.items()):
                    if not isinstance(page_data, dict) or "sections" not in page_data:
                        continue
                    
                    sections = page_data["sections"]
                    cleaned_sections = {}
                    
                    for heading, sec_content in list(sections.items()):
                        # Check heading
                        if any(sh in heading.lower() for sh in skip_headings) or self.is_other_college(heading, college):
                            cleaned_count += 1
                            continue
                        
                        # Clean paragraphs
                        paragraphs = sec_content.get("paragraphs", [])
                        clean_paragraphs = []
                        for p in paragraphs:
                            if not any(ak in p.lower() for ak in ad_keywords) and not self.is_other_college(p, college):
                                clean_paragraphs.append(p)
                            else:
                                cleaned_count += 1
                                
                        # Clean lists
                        lists = sec_content.get("lists", [])
                        clean_lists = []
                        for lst in lists:
                            clean_items = [
                                item for item in lst 
                                if not any(ak in item.lower() for ak in ad_keywords) and not self.is_other_college(item, college)
                            ]
                            if len(clean_items) > 1:
                                clean_lists.append(clean_items)
                            else:
                                cleaned_count += len(lst)
                                
                        # Clean tables
                        tables = sec_content.get("tables", [])
                        
                        # Save if there is still content
                        if clean_paragraphs or clean_lists or tables:
                            cleaned_sections[heading] = {
                                "paragraphs": clean_paragraphs,
                                "lists": clean_lists,
                                "tables": tables
                            }
                        else:
                            cleaned_count += 1
                            
                    page_data["sections"] = cleaned_sections
                    
        logger.info(f"Cleanup finished! Filtered out {cleaned_count} generic advertisement blocks/headings from existing cache.")

    def save_cache(self):
        """Save crawled data to JSON file incrementally"""
        os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)
        try:
            # Atomic write using temp file
            temp_file = OUTPUT_FILE + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(self.cached_data, f, indent=2, ensure_ascii=False)
            os.replace(temp_file, OUTPUT_FILE)
            logger.info(f"Incremental progress saved to {OUTPUT_FILE}")
        except Exception as e:
            logger.error(f"Error saving data to file: {str(e)}")

    def init_driver(self):
        """Initialize undetected-chromedriver"""
        if self.driver is not None:
            return

        logger.info("Initializing undetected-chromedriver...")
        options = uc.ChromeOptions()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,900")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-first-run")
        options.add_argument("--disable-default-apps")

        # Set user agent
        options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

        try:
            self.driver = uc.Chrome(options=options, version_main=147)
        except Exception as e:
            logger.warning(f"Chrome initialization failed with specific version: {str(e)}. Retrying with default...")
            try:
                self.driver = uc.Chrome(options=options)
            except Exception as e2:
                logger.error(f"Failed to start Chrome driver completely: {str(e2)}")
                raise e2

    def close_driver(self):
        """Close browser driver"""
        if self.driver:
            try:
                self.driver.quit()
                logger.info("Browser driver closed successfully")
            except Exception as e:
                logger.error(f"Error closing browser: {str(e)}")
            finally:
                self.driver = None

    def fetch_page_source(self, url: str) -> Optional[str]:
        """Fetch the HTML source of a page with scrolling and lazy load wait"""
        self.init_driver()
        logger.info(f"Navigating to: {url}")
        
        try:
            self.driver.get(url)
            
            # Wait for base element to load
            try:
                WebDriverWait(self.driver, PAGE_LOAD_WAIT).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except Exception:
                logger.warning("Timeout waiting for page body element")
            
            time.sleep(2)
            
            # Polite scroll down to trigger lazy loading
            logger.info("Scrolling page to trigger lazy-loaded contents...")
            last_height = self.driver.execute_script("return document.body.scrollHeight")
            
            # Scroll up to 3 times to get dynamically loaded tables/comments
            for _ in range(3):
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight / 2);")
                time.sleep(SCROLL_PAUSE)
                self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(SCROLL_PAUSE)
                
                new_height = self.driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height
                
            self.driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(1)
            
            return self.driver.page_source
            
        except Exception as e:
            logger.error(f"Error fetching page {url}: {str(e)}")
            # If the driver has crashed, restart it on next call
            if "target window already closed" in str(e).lower() or "chrome not reachable" in str(e).lower():
                self.close_driver()
            return None

    def clean_text(self, text: str) -> str:
        """Clean and normalize scraped text"""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        return text

    def parse_table(self, table_tag: Tag) -> Optional[Dict]:
        """Convert standard HTML table into a clean JSON structure"""
        headers = []
        rows = []
        
        thead = table_tag.find("thead")
        if thead:
            header_cells = thead.find_all(["th", "td"])
            headers = [self.clean_text(cell.get_text()) for cell in header_cells]
            
        tbody = table_tag.find("tbody") or table_tag
        trs = tbody.find_all("tr")
        
        if not trs:
            return None
            
        start_row = 0
        if not headers:
            first_row_cells = trs[0].find_all(["th", "td"])
            headers = [self.clean_text(cell.get_text()) for cell in first_row_cells]
            start_row = 1
            
        for tr in trs[start_row:]:
            cells = tr.find_all(["td", "th"])
            row = [self.clean_text(cell.get_text()) for cell in cells]
            # Verify it's a valid row and matches column counts approximately
            if any(row):
                rows.append(row)
                
        if not headers and not rows:
            return None
            
        return {
            "headers": headers,
            "rows": rows
        }

    def parse_page_structure(self, html: str, college_name: Optional[str] = None) -> Dict:
        """Extract structured paragraphs, tables, and lists grouped under headings"""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Remove script and style elements
        for tag in soup(["script", "style", "noscript", "iframe", "svg", "header", "footer", "nav"]):
            tag.decompose()
            
        sections = {}
        current_section = "Overview"
        sections[current_section] = {
            "paragraphs": [],
            "lists": [],
            "tables": []
        }

        # Comprehensive keywords for generic ads, mobile app installs, site widgets, and unrelated colleges
        ad_keywords = [
            "convenience of your phone", "detailed books and sample papers", "regular exam updates",
            "best college recommendations", "college & rank predictors", "question and answers",
            "student community: where questions", "where questions find answers", "all this at the convenience",
            "download mobile app", "install app", "by stream", "write a review", "get matching colleges",
            "apply to check the best colleges", "click on apply to check", "best colleges that might interest you",
            "top government universities in", "top government colleges in", "government universities in",
            "government colleges in", "accepting applications", "admissions 2026 open", "admissions open",
            "last date to apply", "apply now", "vit bhopal", "lovely professional", "lpu", "sharda university",
            "amity university", "upes", "chitkara", "chandigarh university", "nims university",
            "manipal university", "dy patil", "srm university", "bennett university", "diamond rated",
            "naac a+ accredited", "naac a++ grade", "recruitment partners", "job offers", "highest package 1.6 cr",
            "highest ctc", "avail 50% waiver", "brochure", "download brochure", "select course",
            "read more", "all rights reserved", "cookie policy", "terms and conditions", "contact us",
            "site map", "privacy policy",
            # User specific items:
            "reliance infrastructure", "foodvista", "lebua hotels", "accenture services",
            "reliance infrastructure limited", "foodvista india private", "lebua hotels and resorts",
            "accenture services private limited",
        ]

        skip_headings = [
            "login", "register", "apply now", "download", "accepting applications", "top institutes", 
            "accepting application", "senior executive vice pre", "advisor", "ceo", "managing director - tech",
            "by stream", "student community", "convenience of your phone", "sample papers", 
            "exam updates", "college recommendations", "rank predictors", "question and answers"
        ]
        
        # Walk document depth-first and capture relevant tags
        # We target headers, paragraphs, lists, and tables to capture the hierarchy
        for elem in soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'p', 'ul', 'ol', 'table']):
            if elem.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                heading_text = self.clean_text(elem.get_text())
                # Ignore very short headings, menu text, or obvious ad headers
                if heading_text and len(heading_text) < 100:
                    heading_lower = heading_text.lower()
                    if not any(sh in heading_lower for sh in skip_headings) and not self.is_other_college(heading_text, college_name):
                        current_section = heading_text
                        if current_section not in sections:
                            sections[current_section] = {
                                "paragraphs": [],
                                "lists": [],
                                "tables": []
                            }
            elif elem.name == 'p':
                paragraph_text = self.clean_text(elem.get_text())
                # Capture substantial informative paragraphs
                if paragraph_text and len(paragraph_text) > 30:
                    # Filter out boilerplate web copy, generic site promotions, and third-party ads
                    paragraph_lower = paragraph_text.lower()
                    if not any(ak in paragraph_lower for ak in ad_keywords) and not self.is_other_college(paragraph_text, college_name):
                        sections[current_section]["paragraphs"].append(paragraph_text)
            elif elem.name in ['ul', 'ol']:
                items = [self.clean_text(li.get_text()) for li in elem.find_all('li')]
                # Filter out individual list items that are generic spam or too short
                items = [
                    item for item in items 
                    if item and len(item) > 2 and not any(ak in item.lower() for ak in ad_keywords) and not self.is_other_college(item, college_name)
                ]
                # Filter lists that are just headers/sub-links or single words
                if items and len(items) > 1 and len(' '.join(items)) > 20:
                    sections[current_section]["lists"].append(items)
            elif elem.name == 'table':
                table_data = self.parse_table(elem)
                if table_data and table_data["rows"]:
                    sections[current_section]["tables"].append(table_data)
                    
        # Filter and keep only sections that have scraped data
        cleaned_sections = {}
        for section_name, section_data in sections.items():
            if section_data["paragraphs"] or section_data["lists"] or section_data["tables"]:
                cleaned_sections[section_name] = section_data
                
        # Scrape overall page rating if present
        page_rating = None
        rating_match = re.search(r'(\d\.\d)\s*/\s*10|(\d\.\d)\s*out of 5', soup.get_text())
        if rating_match:
            page_rating = rating_match.group(0)
            
        return {
            "sections": cleaned_sections,
            "rating": page_rating
        }

    def reconstruct_collegedunia_urls(self, url: str) -> Dict[str, str]:
        """Convert placement URL to other endpoints for CollegeDunia"""
        if not url:
            return {}
        
        # Remove trailing slashes and common placement path suffixes
        base_url = url.rstrip('/')
        patterns = [
            r'/placement$', r'/placements$', r'/placement-details$', 
            r'/placement-packages$', r'/placement-report$'
        ]
        for pattern in patterns:
            base_url = re.sub(pattern, '', base_url)
            
        return {
            "main": base_url,
            "reviews": f"{base_url}/reviews",
            "ranking": f"{base_url}/ranking",
            "courses-fees": f"{base_url}/courses-fees",
            "admission": f"{base_url}/admission"
        }

    def reconstruct_careers360_urls(self, url: str) -> Dict[str, str]:
        """Convert placement URL to other endpoints for Careers360"""
        if not url:
            return {}
            
        base_url = url.rstrip('/')
        patterns = [
            r'/placement$', r'/placements$', r'/placement-details$'
        ]
        for pattern in patterns:
            base_url = re.sub(pattern, '', base_url)
            
        return {
            "main": base_url,
            "reviews": f"{base_url}/reviews",
            "ranking": f"{base_url}/ranking",
            "facilities": f"{base_url}/facilities",
            "courses": f"{base_url}/courses"
        }

    def scrape_college(self, college: Dict) -> Dict:
        """Scrape all non-placement endpoints for a given college map"""
        college_name = college["name"]
        logger.info(f"=== Starting Scrape for: {college_name} ===")
        
        college_data = {
            "college_name": college_name,
            "collegedunia": {},
            "careers360": {},
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ")
        }

        # 1. CollegeDunia scraping
        cd_url = college.get("collegedunia_url")
        if cd_url:
            cd_endpoints = self.reconstruct_collegedunia_urls(cd_url)
            logger.info(f"CollegeDunia endpoints: {cd_endpoints}")
            
            for page_type, endpoint in cd_endpoints.items():
                logger.info(f"Crawling CollegeDunia [{page_type}]: {endpoint}")
                html = self.fetch_page_source(endpoint)
                if html:
                    parsed = self.parse_page_structure(html, college_name=college_name)
                    college_data["collegedunia"][page_type] = {
                        "url": endpoint,
                        "sections": parsed["sections"],
                        "rating": parsed["rating"]
                    }
                    logger.info(f"✓ Scraped {len(parsed['sections'])} sections from {page_type}")
                # Be respectful
                time.sleep(2)

        # 2. Careers360 scraping
        c360_url = college.get("careers360_url")
        if c360_url:
            c360_endpoints = self.reconstruct_careers360_urls(c360_url)
            logger.info(f"Careers360 endpoints: {c360_endpoints}")
            
            for page_type, endpoint in c360_endpoints.items():
                logger.info(f"Crawling Careers360 [{page_type}]: {endpoint}")
                html = self.fetch_page_source(endpoint)
                if html:
                    parsed = self.parse_page_structure(html, college_name=college_name)
                    college_data["careers360"][page_type] = {
                        "url": endpoint,
                        "sections": parsed["sections"],
                        "rating": parsed["rating"]
                    }
                    logger.info(f"✓ Scraped {len(parsed['sections'])} sections from {page_type}")
                # Be respectful
                time.sleep(2)

        return college_data


def main():
    parser = argparse.ArgumentParser(description="College General Data Scraper")
    parser.add_argument("--test", action="store_true", help="Run a quick test on first 2 colleges only")
    parser.add_argument("--headless", type=bool, default=True, help="Run browser in headless mode")
    parser.add_argument("--force", action="store_true", help="Force overwrite already scraped colleges")
    args = parser.parse_args()

    print("=" * 70)
    print(" College General Data Scraper ".center(70, "="))
    print("=" * 70)

    # Verify input file exists
    if not os.path.exists(INPUT_FILE):
        logger.error(f"Input file {INPUT_FILE} not found. Exiting.")
        sys.exit(1)

    # Load college urls
    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        colleges = json.load(f)
    
    logger.info(f"Found {len(colleges)} colleges in input list")
    
    if args.test:
        logger.info("Running in TEST mode (processing first 2 colleges only)")
        colleges = colleges[:2]

    # Initialize scraper
    scraper = CollegeGeneralScraper(headless=args.headless)
    
    try:
        for idx, college in enumerate(colleges, 1):
            name = college["name"]
            logger.info(f"\n[{idx}/{len(colleges)}] Processing college: {name}")
            
            # Check cache
            if name in scraper.cached_data and not args.force:
                logger.info(f"Skipping {name} (already scraped and present in cache)")
                continue

            try:
                scraped_data = scraper.scrape_college(college)
                
                # Check if we successfully scraped any general data
                if scraped_data["collegedunia"] or scraped_data["careers360"]:
                    scraper.cached_data[name] = scraped_data
                    # Incremental save
                    scraper.save_cache()
                    logger.info(f"✓ Successfully processed and cached {name}")
                else:
                    logger.warning(f"No data extracted for {name}")
                    
            except Exception as e:
                logger.error(f"Error scraping {name}: {str(e)}")
                
    finally:
        scraper.close_driver()
        logger.info("Scraping workflow ended.")


if __name__ == "__main__":
    main()
