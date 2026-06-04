"""
Shiksha.com Placement Data Scraper
====================================
Extracts structured placement data from Shiksha.com similar to careers360/collegedunia approach.

Requirements:
    pip install undetected-chromedriver selenium beautifulsoup4

Usage:
    python shiksha_scraper.py
    Output: bits_pilani_placements.json
"""

import json
import time
import re
import sys
from typing import Dict, List, Optional, Set

try:
    import undetected_chromedriver as uc
except ImportError:
    sys.exit("Missing dependency. Run:  pip install undetected-chromedriver selenium beautifulsoup4")

try:
    from bs4 import BeautifulSoup, NavigableString, Tag
except ImportError:
    sys.exit("Missing dependency. Run:  pip install undetected-chromedriver selenium beautifulsoup4")

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# ─── Config ───────────────────────────────────────────────────────────────────
URL = "https://www.shiksha.com/university/bits-pilani-birla-institute-of-technology-and-science-467/placement"
OUTPUT_FILE = "../bits_pilani_placements.json"
PAGE_LOAD_WAIT = 15
SCROLL_PAUSE = 1.5
# ──────────────────────────────────────────────────────────────────────────────


class ShikshaPlacementScraper:
    """Scraper for Shiksha.com placement data with structured extraction"""

    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }

    def clean_text(self, text: str) -> str:
        """Clean and normalize text"""
        if not text:
            return ""
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        return text

    def extract_number(self, text: str) -> Optional[float]:
        """Extract numerical values from text"""
        if not text:
            return None
        text = text.replace('INR', '').replace('Rs', '').replace('₹', '')
        text = text.replace('LPA', '').replace('Lakhs', '').replace('lakhs', '')
        text = text.replace(',', '').strip()
        match = re.search(r'(\d+(?:\.\d+)?)', text)
        if match:
            return float(match.group(1))
        return None

    def extract_percentage(self, text: str) -> Optional[float]:
        """Extract percentage from text"""
        if not text:
            return None
        match = re.search(r'(\d+(?:\.\d+)?)\s*%', text)
        if match:
            return float(match.group(1))
        return None

    def extract_salary_lpa(self, text: str) -> Optional[float]:
        """Extract salary in LPA from text"""
        if not text:
            return None
        match = re.search(r'(?:INR|Rs|₹)?\s*(\d+(?:\.\d+)?)\s*LPA', text, re.IGNORECASE)
        if match:
            return float(match.group(1))
        return None

    def is_placement_table(self, table_tag: Tag) -> bool:
        """Check if a table contains placement-related data"""
        # Get all text from the table
        table_text = table_tag.get_text().lower()

        # Keywords that indicate placement data
        placement_keywords = [
            'salary', 'package', 'lpa', 'lakh', 'placed', 'placement',
            'recruiter', 'company', 'average', 'median', 'highest',
            'student', 'registered', 'companies visited', 'statistics'
        ]

        # Keywords that indicate navigation/sidebar content (exclude these)
        exclusion_keywords = [
            'top ranked colleges', 'top law colleges', 'top hotel management',
            'popular courses', 'popular specializations', 'colleges by location',
            'exams', 'resources', 'ask a question', 'discussions', 'trends',
            'college predictor', 'all law courses', 'all hospitality courses',
            'catering', 'culinary arts', 'event management', 'travel & tourism'
        ]

        # Check if table has placement keywords
        has_placement = any(keyword in table_text for keyword in placement_keywords)

        # Check if table has exclusion keywords
        has_exclusion = any(keyword in table_text for keyword in exclusion_keywords)

        # Also check table headers specifically
        headers = []
        thead = table_tag.find("thead")
        if thead:
            header_cells = thead.find_all(["th", "td"])
            headers = [self.clean_text(cell.get_text()) for cell in header_cells]
            for text in headers:
                if text:
                    table_text += ' ' + text.lower()
        else:
            # Check first row for headers
            first_row = table_tag.find("tr")
            if first_row:
                header_cells = first_row.find_all(["td", "th"])
                headers = [self.clean_text(cell.get_text()) for cell in header_cells]
                for text in headers:
                    if text:
                        table_text += ' ' + text.lower()

        # Check if table has placement keywords in headers OR content
        has_placement_header = any(keyword in table_text for keyword in [
            'salary', 'package', 'lpa', 'lakh', 'placed', 'placement',
            'recruiter', 'company', 'average', 'median', 'highest',
            'student', 'registered', 'companies visited', 'statistics'
        ])
        
        has_exclusion_header = any(keyword in table_text for keyword in [
            'top ranked', 'top law', 'top hotel', 'popular courses',
            'popular specializations', 'colleges by location',
            'exams', 'placement report', 'download', 'internship'
        ])
        has_strong_exclusion = any(keyword in table_text for keyword in exclusion_keywords)
        
        # Include if it has placement indicators and no strong exclusion indicators
        return (has_placement or has_placement_header) and not has_strong_exclusion

    def parse_table(self, table_tag: Tag) -> dict:
        """Parse table into structured format"""
        headers = []
        rows = []
        cell_texts = set()

        thead = table_tag.find("thead")
        if thead:
            header_cells = thead.find_all(["th", "td"])
            headers = [self.clean_text(cell.get_text()) for cell in header_cells]
            for text in headers:
                if text:
                    cell_texts.add(text.lower())

        tbody = table_tag.find("tbody") or table_tag
        for tr in tbody.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if not cells:
                continue
            row = [self.clean_text(cell.get_text()) for cell in cells]
            if any(cell.strip() for cell in row):
                rows.append(row)
                for text in row:
                    if text:
                        cell_texts.add(text.lower())

        if not headers and rows:
            headers = rows.pop(0)

        return {
            "headers": headers,
            "rows": rows,
            "cell_texts": cell_texts
        }

    def extract_placement_statistics(self, tables: List[dict], page_text: str) -> Dict:
        """Extract placement statistics from tables and text"""
        stats = {}

        for table in tables:
            headers = table.get('headers', [])
            rows = table.get('rows', [])

            # Look for the main placement statistics table
            if 'statistics' in ' '.join(headers).lower() or 'particulars' in ' '.join(headers).lower():
                for row in rows:
                    for i, cell in enumerate(row):
                        header = headers[i] if i < len(headers) else ''
                        header_lower = header.lower()

                        # Extract average package
                        if 'average' in header_lower and 'package' in header_lower:
                            salary = self.extract_salary_lpa(cell)
                            if salary:
                                stats['average_package_lpa'] = salary

                        # Extract highest package
                        elif 'highest' in header_lower and 'package' in header_lower:
                            salary = self.extract_salary_lpa(cell)
                            if salary:
                                stats['highest_package_lpa'] = salary

                        # Extract median package
                        elif 'median' in header_lower and 'package' in header_lower:
                            salary = self.extract_salary_lpa(cell)
                            if salary:
                                stats['median_package_lpa'] = salary

                        # Extract placement percentage/rate
                        elif 'placement' in header_lower or 'rate' in header_lower:
                            pct = self.extract_percentage(cell)
                            if pct:
                                stats['placement_percentage'] = pct

                        # Extract students placed
                        elif 'student placed' in header_lower or 'placed' in header_lower:
                            num = self.extract_number(cell)
                            if num:
                                stats['students_placed'] = int(num)

                        # Extract companies visited
                        elif 'companies' in header_lower or 'company' in header_lower:
                            num = self.extract_number(cell)
                            if num:
                                stats['companies_visited'] = int(num)

        # Extract from text as fallback - look for specific patterns
        avg_match = re.search(r'average\s+(?:package|salary|salary offered)[^\d]*(\d+(?:\.\d+)?)\s*LPA', page_text, re.IGNORECASE)
        if avg_match and 'average_package_lpa' not in stats:
            stats['average_package_lpa'] = float(avg_match.group(1))

        highest_match = re.search(r'highest\s+(?:package|salary)[^\d]*(\d+(?:\.\d+)?)\s*LPA', page_text, re.IGNORECASE)
        if highest_match and 'highest_package_lpa' not in stats:
            stats['highest_package_lpa'] = float(highest_match.group(1))

        # Extract placement percentage from text
        pct_match = re.search(r'(\d+(?:\.\d+)?)\s*%\s*(?:placement|placed)', page_text, re.IGNORECASE)
        if pct_match and 'placement_percentage' not in stats:
            stats['placement_percentage'] = float(pct_match.group(1))

        # Extract students placed
        placed_match = re.search(r'(\d+)\s+students?\s+(?:got\s+)?placed', page_text, re.IGNORECASE)
        if placed_match and 'students_placed' not in stats:
            stats['students_placed'] = int(placed_match.group(1))

        return stats

    def extract_top_recruiters(self, tables: List[dict], soup: BeautifulSoup) -> List[str]:
        """Extract top recruiters from tables and lists"""
        recruiters = set()
        cell_texts = set()

        # Collect all table cell texts
        for table in tables:
            cell_texts.update(table.get('cell_texts', set()))

        # Extract from tables with company/recruiter columns
        for table in tables:
            headers = table.get('headers', [])
            rows = table.get('rows', [])

            for i, header in enumerate(headers):
                if any(keyword in header.lower() for keyword in ['company', 'recruiter', 'top']):
                    for row in rows:
                        if i < len(row):
                            company = row[i]
                            if company and len(company) < 100 and len(company) > 2:
                                recruiters.add(company)

        # Extract from lists near recruiter keywords
        recruiter_keywords = ['recruiter', 'company', 'top']
        for keyword in recruiter_keywords:
            sections = soup.find_all(string=re.compile(keyword, re.IGNORECASE))
            for section in sections:
                parent = section.find_parent()
                if parent:
                    nearby_lists = parent.find_all(['ul', 'ol'])
                    for lst in nearby_lists:
                        items = lst.find_all('li')
                        for item in items:
                            text = self.clean_text(item.get_text())
                            if text and len(text) < 100 and len(text) > 2:
                                recruiters.add(text)

        # Also look for company names in paragraphs near recruiter keywords
        page_text = soup.get_text()
        # Look for patterns like "Top recruiters include X, Y, Z"
        recruiter_pattern = re.search(r'(?:top\s+recruiters?|recruiters?|companies?)(?:\s+(?:include|are|such as))[:\s]*([^.]+)', page_text, re.IGNORECASE)
        if recruiter_pattern:
            companies_text = recruiter_pattern.group(1)
            # Split by common separators
            for company in re.split(r',|and|&', companies_text):
                company = self.clean_text(company)
                if company and len(company) < 100 and len(company) > 2:
                    recruiters.add(company)

        # Filter out non-company names
        filtered_recruiters = []
        for rec in recruiters:
            rec_lower = rec.lower()
            if rec_lower in cell_texts:
                continue
            if any(skip in rec_lower for skip in ['more', 'view', 'click', 'etc', 'and', 'or', 'the', 'all']):
                continue
            # Skip if it's just a number or very generic
            if re.match(r'^\d+$', rec):
                continue
            filtered_recruiters.append(rec)

        return sorted(list(set(filtered_recruiters)))

    def extract_program_wise_data(self, tables: List[dict], soup: BeautifulSoup) -> List[Dict]:
        """Extract program-wise placement data"""
        program_data = []

        for table in tables:
            headers = table.get('headers', [])
            rows = table.get('rows', [])

            if any(keyword in ' '.join(headers).lower() for keyword in ['program', 'course', 'branch', 'degree']):
                for row in rows:
                    row_dict = {}
                    for i, cell in enumerate(row):
                        header = headers[i] if i < len(headers) else f'column_{i}'
                        row_dict[header] = cell
                    if row_dict:
                        program_data.append(row_dict)

        return program_data

    def scrape(self, url: str) -> Dict:
        """Main scraping method following careers360/collegedunia pattern"""
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1440,900")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-first-run")
        options.add_argument("--disable-default-apps")
        
        try:
            driver = uc.Chrome(options=options, version_main=147)
        except Exception as e:
            print(f"[!] Chrome initialization error: {str(e)}")
            print("[!] Trying with default Chrome version...")
            try:
                driver = uc.Chrome(options=options)
            except Exception as e2:
                print(f"[!] Default Chrome also failed: {str(e2)}")
                sys.exit(1)

        print(f"[*] Opening browser and navigating to:\n    {url}\n")

        try:
            driver.get(url)

            try:
                WebDriverWait(driver, PAGE_LOAD_WAIT).until(
                    EC.presence_of_element_located((By.TAG_NAME, "h2"))
                )
            except Exception:
                print("[!] Timed out waiting for h2 — proceeding anyway.")

            time.sleep(3)
            print("[*] Scrolling to trigger lazy-loaded sections...")

            last_height = driver.execute_script("return document.body.scrollHeight")
            while True:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                time.sleep(SCROLL_PAUSE)
                new_height = driver.execute_script("return document.body.scrollHeight")
                if new_height == last_height:
                    break
                last_height = new_height

            driver.execute_script("window.scrollTo(0, 0);")
            time.sleep(2)

            html = driver.page_source
        except Exception as e:
            print(f"[!] Browser error occurred: {str(e)}")
            if "target window already closed" in str(e).lower():
                print("[!] Retrying with fresh browser instance...")
                try:
                    driver = uc.Chrome(options=options, version_main=147)
                    driver.get(url)
                    WebDriverWait(driver, PAGE_LOAD_WAIT).until(
                        EC.presence_of_element_located((By.TAG_NAME, "h2"))
                    )
                    time.sleep(3)
                    print("[*] Scrolling to trigger lazy-loaded sections...")
                    last_height = driver.execute_script("return document.body.scrollHeight")
                    while True:
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(SCROLL_PAUSE)
                        new_height = driver.execute_script("return document.body.scrollHeight")
                        if new_height == last_height:
                            break
                        last_height = new_height
                    driver.execute_script("window.scrollTo(0, 0);")
                    time.sleep(2)
                    html = driver.page_source
                    driver.quit()
                    print("[*] Browser closed.\n")
                except Exception as retry_e:
                    print(f"[!] Retry failed: {str(retry_e)}")
                    html = ""
        finally:
            if 'driver' in locals():
                driver.quit()
                print("[*] Browser closed.\n")

        print("[*] Parsing extracted HTML...")
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style", "noscript", "iframe", "svg"]):
            tag.decompose()

        tables = []
        seen_table_ids = set()
        for table in soup.find_all("table"):
            tid = id(table)
            if tid not in seen_table_ids:
                seen_table_ids.add(tid)
                # Only parse tables that contain placement-related data
                if self.is_placement_table(table):
                    parsed = self.parse_table(table)
                    if parsed["rows"]:
                        tables.append(parsed)

        program_data = self.extract_program_wise_data(tables, soup)

        result = {
            "source": "shiksha",
            "url": url,
            "program_wise_data": program_data,
            "raw_data": []
        }

        for table in tables:
            result["raw_data"].append({
                "headers": table["headers"],
                "rows": table["rows"]
            })

        return result

    def save(self, data: Dict, path: str) -> None:
        """Save data to JSON file"""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[✓] Saved data → {path}")

    def pretty_print(self, data: Dict) -> None:
        """Pretty print the extracted data"""
        print(f"\n{'='*60}")
        print(f"  SHIKSHA.COM PLACEMENT DATA")
        print(f"{'='*60}")
        print(f"\nSource: {data['source']}")
        print(f"URL: {data['url']}")

        print(f"\n{'─'*60}")
        print(f"  PROGRAM-WISE DATA ({len(data.get('program_wise_data', []))} entries)")
        print(f"{'─'*60}")
        for i, program in enumerate(data.get('program_wise_data', [])[:5], 1):
            print(f"  {i}. {program}")
        if len(data.get('program_wise_data', [])) > 5:
            print(f"  ... and {len(data.get('program_wise_data', [])) - 5} more")

        print(f"\n{'─'*60}")
        print(f"  RAW DATA ({len(data.get('raw_data', []))} tables)")
        print(f"{'─'*60}")
        for i, table in enumerate(data.get('raw_data', [])[:3], 1):
            print(f"  Table {i}: {len(table['headers'])} headers, {len(table['rows'])} rows")
            print(f"    Headers: {table['headers'][:2]}{'...' if len(table['headers']) > 2 else ''}")
        if len(data.get('raw_data', [])) > 3:
            print(f"  ... and {len(data.get('raw_data', [])) - 3} more tables")

        print(f"\n{'='*60}\n")


def main():
    """Main execution function"""
    scraper = ShikshaPlacementScraper()

    print(f"[*] Starting Shiksha.com scraper...")
    data = scraper.scrape(URL)

    if not data or not data.get('raw_data'):
        print("[!] No content extracted. The page may have blocked the request.")
        sys.exit(1)

    scraper.save(data, OUTPUT_FILE)
    scraper.pretty_print(data)

    print(f"Total tables extracted: {len(data.get('raw_data', []))}")
    print(f"Program-wise data entries: {len(data.get('program_wise_data', []))}")


if __name__ == "__main__":
    main()
