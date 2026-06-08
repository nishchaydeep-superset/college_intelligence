#!/usr/bin/env python3
"""
reddit_scraper.py

Extracts reviews, discussions, placement statistics, and student sentiments
from Reddit for Indian colleges using public RSS/Atom XML feeds.

Saves all extracted college data in a single unified JSON file:
  data/college_reddit_data.json
"""

from __future__ import annotations

import os
import re
import json
import time
import argparse
import urllib.parse
import random
from typing import Any, Dict, List, Optional

import httpx
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants & Config
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/xml,text/xml,application/xhtml+xml",
}

FETCH_TIMEOUT = 15
REQUEST_DELAY = 1.2  # Polite delay between HTTP calls
SINGLE_FILE_PATH = os.path.join("data", "college_reddit_data.json")


# ---------------------------------------------------------------------------
# Helper Utilities
# ---------------------------------------------------------------------------

def slugify(name: str) -> str:
    """Create a URL-safe, filename-safe slug from a string."""
    s = name.lower()
    s = re.sub(r'[^a-z0-9]', '_', s)
    s = re.sub(r'_+', '_', s)
    return s.strip('_')


def _now_iso() -> str:
    """Return current UTC time in ISO format."""
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def clean_rss_content(html_content: str) -> str:
    """Extract and clean plain text from HTML formatted RSS content."""
    if not html_content:
        return ""
    soup = BeautifulSoup(html_content, "html.parser")
    # Replace linebreaks with newlines
    for br in soup.find_all("br"):
        br.replace_with("\n")
    for p in soup.find_all("p"):
        p.insert_after("\n")
    
    # Get text and clean extra whitespaces
    text = soup.get_text()
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join([line for line in lines if line]).strip()


def get_clean_rss_url(url: str) -> str:
    """Remove query parameters from thread URL and append .rss."""
    parsed = urllib.parse.urlparse(url)
    clean_path = parsed.path.rstrip('/')
    clean_url = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, clean_path, '', '', ''))
    return f"{clean_url}.rss"


# ---------------------------------------------------------------------------
# College Query Optimizer
# ---------------------------------------------------------------------------

def generate_search_terms(college_name: str) -> List[str]:
    """
    Generate optimal Reddit search queries for a college based on common aliases,
    abbreviations, and student terminology.
    """
    terms = []
    
    # 1. Full name (truncated up to comma)
    full_clean = college_name.split(",")[0].strip()
    terms.append(full_clean)
    
    lower_name = college_name.lower()
    
    # Check for NITs
    if "national institute of technology" in lower_name:
        match = re.search(r'technology\s+([a-zA-Z]+)', lower_name)
        if match:
            city = match.group(1).title()
            terms.append(f"NIT {city}")
            terms.append(f"NIT{city}")
            
    # Check for IITs
    elif "indian institute of technology" in lower_name:
        match = re.search(r'technology\s+([a-zA-Z]+)', lower_name)
        if match:
            city = match.group(1).title()
            terms.append(f"IIT {city}")
            terms.append(f"IIT{city}")
            
    # Check for IIMs
    elif "indian institute of management" in lower_name:
        match = re.search(r'management\s+([a-zA-Z]+)', lower_name)
        if match:
            city = match.group(1).title()
            terms.append(f"IIM {city}")
            terms.append(f"IIM{city}")
            
    # Check for IIITs
    elif "indian institute of information technology" in lower_name:
        match = re.search(r'technology\s+([a-zA-Z]+)', lower_name)
        if match:
            city = match.group(1).title()
            terms.append(f"IIIT {city}")
            terms.append(f"IIIT{city}")

    # Special rules for specific famous colleges
    special_cases = {
        "birla institute of technology and science pilani": ["BITS Pilani", "BITS"],
        "birla institute of technology & sciences, pilani": ["BITS Pilani", "BITS"],
        "lovely professional university": ["LPU"],
        "delhi technological university": ["DTU"],
        "netaji subhas university of technology": ["NSUT", "NSIT"],
        "vit vellore": ["VIT", "VIT Vellore"],
        "vellore institute of technology": ["VIT", "VIT Vellore"],
        "kalinga institute of industrial technology": ["KIIT"],
        "ramaiah institute of technology": ["MSRIT", "Ramaiah"],
        "manipal institute of technology": ["MIT Manipal", "Manipal"],
        "b.m.s. college of engineering": ["BMSCE"],
        "rv college of engineering": ["RVCE"],
        "peoples education society university": ["PES University", "PESU", "PESIT"],
        "pes university": ["PESU", "PESIT"],
    }
    
    for key, aliases in special_cases.items():
        if key in lower_name:
            for alias in aliases:
                # If the college name contains specific campus details
                if "hyderabad" in lower_name:
                    terms.append(f"{alias} Hyderabad")
                elif "goa" in lower_name:
                    terms.append(f"{alias} Goa")
                else:
                    terms.append(alias)
            break

    # Clean duplicates and format
    seen = set()
    cleaned_terms = []
    for t in terms:
        t_clean = t.strip()
        if t_clean and t_clean.lower() not in seen:
            seen.add(t_clean.lower())
            cleaned_terms.append(t_clean)
            
    return cleaned_terms


# ---------------------------------------------------------------------------
# Scraping Engine
# ---------------------------------------------------------------------------

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2.1 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]

class UrllibResponse:
    def __init__(self, text: str, status_code: int):
        self.text = text
        self.status_code = status_code

def make_request(url: str, timeout: int = FETCH_TIMEOUT) -> Optional[UrllibResponse]:
    """Execute HTTP GET using urllib.request with rotating User-Agent and retry logic for rate limits/blocks."""
    import urllib.request
    import urllib.error
    
    backoff = 6.0
    max_retries = 30
    
    for attempt in range(max_retries):
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                status_code = response.getcode()
                content = response.read()
                try:
                    text = content.decode('utf-8')
                except UnicodeDecodeError:
                    text = content.decode('latin-1', errors='ignore')
                
                if status_code == 200:
                    return UrllibResponse(text, status_code)
                else:
                    print(f"    [!] HTTP status {status_code} for URL: {url}")
                    return UrllibResponse(text, status_code)
                    
        except urllib.error.HTTPError as e:
            status_code = e.code
            if status_code in (429, 403):
                action = "Rate limited" if status_code == 429 else "Forbidden/Blocked"
                print(f"    [!] {action} ({status_code}). Sleeping {backoff}s before retry (attempt {attempt+1}/{max_retries})...")
                time.sleep(backoff)
                backoff *= 2.0
            else:
                print(f"    [!] HTTP error {status_code} for URL: {url}")
                return UrllibResponse("", status_code)
        except Exception as e:
            print(f"    [!] Request exception: {e}. Retrying in 2s...")
            time.sleep(2.0)
            
    return None


def search_reddit_rss(query: str, limit: int =15) -> List[Dict[str, Any]]:
    """Query Reddit's public search RSS feed for a specific keyword."""
    encoded_query = urllib.parse.quote(query)
    url = f"https://www.reddit.com/search.rss?q={encoded_query}&sort=relevance&t=all&limit={limit}"
    
    print(f"[*] Querying search feed: {url}")
    threads = []
    
    resp = make_request(url)
    if resp and resp.status_code == 200:
        try:
            soup = BeautifulSoup(resp.text, "xml")
            entries = soup.find_all("entry")
            
            for entry in entries:
                link_tag = entry.find("link")
                link = link_tag["href"] if link_tag and "href" in link_tag.attrs else ""
                
                if "/comments/" not in link:
                    continue
                    
                title = entry.find("title").text.strip() if entry.find("title") else "No Title"
                author_tag = entry.find("author")
                author = author_tag.find("name").text.strip() if author_tag and author_tag.find("name") else "anonymous"
                
                subreddit_tag = entry.find("category")
                subreddit = subreddit_tag["term"] if subreddit_tag and "term" in subreddit_tag.attrs else "unknown"
                
                threads.append({
                    "title": title,
                    "url": link,
                    "author": author,
                    "subreddit": subreddit
                })
                
                if len(threads) >= limit:
                    break
        except Exception as e:
            print(f"    [!] Error parsing search RSS: {e}")
    else:
        print(f"    [!] Search RSS failed or returned no response")
        
    return threads


def scrape_thread_comments(thread_url: str) -> Optional[Dict[str, Any]]:
    """Fetch and parse original post selftext and comments from a thread's RSS feed."""
    rss_url = get_clean_rss_url(thread_url)
    print(f"    [*] Fetching comments RSS: {rss_url}")
    
    resp = make_request(rss_url)
    if resp and resp.status_code == 200:
        try:
            soup = BeautifulSoup(resp.text, "xml")
            entries = soup.find_all("entry")
            
            if not entries:
                return None
                
            # 1. The first entry is the original post itself
            op_entry = entries[0]
            op_title = op_entry.find("title").text.strip() if op_entry.find("title") else ""
            op_author_tag = op_entry.find("author")
            op_author = op_author_tag.find("name").text.strip() if op_author_tag and op_author_tag.find("name") else "anonymous"
            
            content_tag = op_entry.find("content")
            op_selftext = clean_rss_content(content_tag.text) if content_tag else ""
            
            # 2. Subsequent entries are the comments
            comments = []
            for entry in entries[1:]:
                c_author_tag = entry.find("author")
                c_author = c_author_tag.find("name").text.strip() if c_author_tag and c_author_tag.find("name") else "anonymous"
                
                c_content_tag = entry.find("content")
                c_body = clean_rss_content(c_content_tag.text) if c_content_tag else ""
                
                if c_body:
                    comments.append({
                        "author": c_author,
                        "body": c_body
                    })
            
            return {
                "title": op_title,
                "author": op_author,
                "selftext": op_selftext,
                "comments": comments
            }
        except Exception as e:
            print(f"    [!] Error parsing comments RSS: {e}")
            
    return None


def process_college(college_name: str, max_threads_limit: int = 15) -> Optional[Dict[str, Any]]:
    """Run Reddit RSS extraction and save output to the unified JSON file."""
    print(f"\n======================================================================")
    print(f" Processing College: {college_name}")
    print(f"======================================================================")
 
    # 1. Optimize search queries
    search_terms = generate_search_terms(college_name)
    print(f"[*] Generated Search Keywords: {search_terms}")
 
    # 2. Gather unique threads up to the limit
    unique_threads: Dict[str, Dict[str, Any]] = {}
    
    for term in search_terms:
        if len(unique_threads) >= max_threads_limit:
            break
        found_threads = search_reddit_rss(term, limit=max_threads_limit)
        for thread in found_threads:
            url = thread["url"]
            if url not in unique_threads:
                unique_threads[url] = thread
                if len(unique_threads) >= max_threads_limit:
                    break
        
        # Polite delay with jitter
        time.sleep(REQUEST_DELAY + random.uniform(0.5, 1.5))
 
    print(f"[*] Found {len(unique_threads)} unique Reddit threads. Scraping details and comments...")
 
    # 3. Scrape post content and comments for each unique thread
    scraped_threads = []
    
    for idx, (url, thread_info) in enumerate(unique_threads.items(), 1):
        print(f"  [{idx}/{len(unique_threads)}] Scoping: {thread_info['title'][:60]}...")
        
        thread_details = scrape_thread_comments(url)
            
        if thread_details:
            scraped_threads.append({
                "title": thread_details["title"],
                "url": url,
                "author": thread_details["author"],
                "subreddit": thread_info["subreddit"],
                "selftext": thread_details["selftext"],
                "comments": thread_details["comments"]
            })
        else:
            # Fallback for threads that failed (e.g. due to rate limits)
            # They still show up in the UI!
            scraped_threads.append({
                "title": thread_info["title"],
                "url": url,
                "author": thread_info["author"],
                "subreddit": thread_info["subreddit"],
                "selftext": "",
                "comments": []
            })
        
        # Polite delay with jitter
        time.sleep(REQUEST_DELAY + random.uniform(0.5, 1.5))

    # 4. Read existing unified JSON data
    all_data = {}
    if os.path.exists(SINGLE_FILE_PATH):
        try:
            with open(SINGLE_FILE_PATH, "r", encoding="utf-8") as f:
                all_data = json.load(f)
        except Exception as e:
            print(f"[!] Warning: Failed to load existing unified file, initializing fresh: {e}")

    # 5. Update dictionary and write atomically
    college_data = {
        "scraped_at": _now_iso(),
        "search_terms": search_terms,
        "total_threads_extracted": len(scraped_threads),
        "threads": scraped_threads
    }
    all_data[college_name] = college_data

    # Create data directory if not exists
    os.makedirs(os.path.dirname(SINGLE_FILE_PATH), exist_ok=True)

    try:
        # Save backup first if file already exists
        if os.path.exists(SINGLE_FILE_PATH):
            os.replace(SINGLE_FILE_PATH, SINGLE_FILE_PATH + ".bak")

        # Write to temp and replace (atomic write)
        temp_file = SINGLE_FILE_PATH + ".tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(all_data, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, SINGLE_FILE_PATH)
        print(f"[✓] Saved updated Reddit data for '{college_name}' to single file: {SINGLE_FILE_PATH}")
    except Exception as e:
        print(f"[!] Failed to save data to single file: {e}")

    return college_data


def main():
    parser = argparse.ArgumentParser(description="Reddit College Scraper (RSS-Based, Single Output)")
    parser.add_argument("--test", type=str, help="Name of a single college to scrape and test")
    parser.add_argument("--run-all", action="store_true", help="Scrape all colleges listed in files")
    parser.add_argument("--source", type=str, default="data/college_urls.json",
                        help="Path to JSON file containing list of colleges (e.g. data/college_urls.json or data/college_to_aishe_map.json)")
    args = parser.parse_args()

    if args.test:
        process_college(args.test)
    elif args.run_all:
        colleges = []
        if os.path.exists(args.source):
            try:
                with open(args.source, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if isinstance(content, list):
                        colleges = [item["name"] for item in content if isinstance(item, dict) and "name" in item]
                    elif isinstance(content, dict):
                        colleges = list(content.keys())
            except Exception as e:
                print(f"[!] Error reading source file {args.source}: {e}")
                return
        else:
            print(f"[!] Source file does not exist: {args.source}")
            return

        if not colleges:
            print("[!] No colleges found to process.")
            return

        # Load existing data to support skipping already scraped colleges
        existing_colleges = set()
        if os.path.exists(SINGLE_FILE_PATH):
            try:
                with open(SINGLE_FILE_PATH, "r", encoding="utf-8") as f:
                    existing_data = json.load(f)
                    existing_colleges = set(existing_data.keys())
            except Exception as e:
                print(f"[!] Warning: Failed to load existing unified file for duplicate checking: {e}")

        print(f"[*] Starting scraper for {len(colleges)} colleges from {args.source}...")
        for index, college in enumerate(colleges, 1):
            if college in existing_colleges:
                print(f"\n[{index}/{len(colleges)}] Skipping '{college}' (already scraped in {SINGLE_FILE_PATH})")
                continue

            print(f"\n[{index}/{len(colleges)}] Processing...")
            try:
                process_college(college)
            except Exception as e:
                print(f"[!] Error processing {college}: {e}")
            # Extra delay between colleges
            time.sleep(2.5)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
