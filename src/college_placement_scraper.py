"""
College Placement Data Scraper
Extracts placement details from College Dunia and Careers360
"""

import requests
from bs4 import BeautifulSoup
import json
import time
import re
from urllib.parse import urljoin, urlparse
from typing import Dict, List, Optional
import logging
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from shiksha_scraper import ShikshaPlacementScraper

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class CollegePlacementScraper:
    """Scraper for college placement data from multiple sources"""
    
    def __init__(self):
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        self.colleges_data = {}
        
    def get_page(self, url: str, max_retries: int = 3) -> Optional[BeautifulSoup]:
        """Fetch and parse a webpage with retry logic"""
        for attempt in range(max_retries):
            try:
                logger.info(f"Fetching: {url}")
                # Use fresh request with headers to avoid session caching
                response = requests.get(url, headers=self.headers, timeout=30)
                response.raise_for_status()
                time.sleep(2)  # Be respectful to servers
                return BeautifulSoup(response.content, 'html.parser')
            except Exception as e:
                logger.error(f"Attempt {attempt + 1} failed for {url}: {str(e)}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                else:
                    return None
        return None
    
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
        # Remove common text patterns
        text = text.replace('INR', '').replace('Rs', '').replace('₹', '')
        text = text.replace('LPA', '').replace('Lakhs', '').replace('lakhs', '')
        text = text.replace(',', '').strip()
        
        # Extract number
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
    
    def transform_hierarchical_data(self, table_data: Dict) -> Dict:
        """
        Transform flat table data into hierarchical structure.
        
        This function identifies patterns in table headers and data to create
        a hierarchical structure where:
        - First column represents metrics (e.g., "Median Package", "No. of Students Graduating")
        - Time period columns contain year data
        - Category columns represent different programs
        - Data is grouped by category and then by time period
        
        Args:
            table_data: Dictionary containing 'headers' and 'data' from a table
            
        Returns:
            Transformed hierarchical data structure
        """
        headers = table_data.get('headers', [])
        data_rows = table_data.get('data', [])
        table_index = table_data.get('table_index', 0)
        
        if not headers or not data_rows:
            return table_data
        
        # Enhanced hierarchical detection for CollegeDunia patterns
        # Check for multiple hierarchical patterns
        hierarchical_patterns = [
            ['particulars', 'program', 'category', 'course'],
            ['statistics', 'details', 'information'],
            ['company', 'recruiter', 'organization']
        ]
        
        is_hierarchical = False
        for pattern in hierarchical_patterns:
            if headers[0].lower() in pattern:
                is_hierarchical = True
                break
        
        if not is_hierarchical and len(headers) < 2:
            return table_data
        
        # Enhanced time period and category detection
        time_columns = []
        category_columns = []
        program_columns = []
        
        for header in headers[1:]:
            header_lower = header.lower()
            
            # Enhanced year detection
            year_patterns = ['2022', '2023', '2024', '2025', '2021', '2020', '2019', '2018']
            if any(keyword in header_lower for keyword in year_patterns):
                time_columns.append(header)
            # Check for year in parentheses or brackets
            elif re.search(r'20\d{2}', header):
                time_columns.append(header)
            # Enhanced category detection for CollegeDunia
            elif any(cat in header_lower for cat in ['ug', 'pg', 'year', 'integrated', '(', ')', 'b.tech', 'm.tech', 'bba', 'mba']):
                category_columns.append(header)
            # Program-specific columns
            elif any(prog in header_lower for prog in ['computer', 'mechanical', 'electrical', 'civil', 'electronics']):
                program_columns.append(header)
        
        # Additional pattern matching for CollegeDunia specific formats
        if not time_columns:
            for header in headers[1:]:
                # Look for patterns like "Placement Statistics 2024"
                year_match = re.search(r'(20\d{2})', header)
                if year_match:
                    time_columns.append(header)
                # Look for batch/academic year patterns
                elif any(batch in header_lower for batch in ['batch', 'academic year', 'session']):
                    time_columns.append(header)
        
        # Advanced hierarchical transformation for multiple data types
        if (time_columns and (category_columns or program_columns)) or len(headers) > 3:
            hierarchical_result = {}
            
            # Initialize structure for all categories/programs
            all_categories = category_columns + program_columns
            for category in all_categories:
                hierarchical_result[category] = {}
            
            # Enhanced metric grouping with better pattern recognition
            metric_groups = {}
            subcategory_groups = {}
            
            for row in data_rows:
                particulars = row.get(headers[0], '').strip()
                
                if not particulars:
                    continue
                
                # Enhanced metric key normalization
                metric_key = self._normalize_metric_key(particulars)
                
                # Detect subcategories (e.g., "Computer Science - Placement Rate")
                subcategory = self._extract_subcategory(particulars)
                
                # Group by metric and subcategory
                group_key = f"{metric_key}_{subcategory}" if subcategory else metric_key
                if group_key not in metric_groups:
                    metric_groups[group_key] = {
                        'metric_key': metric_key,
                        'subcategory': subcategory,
                        'rows': []
                    }
                metric_groups[group_key]['rows'].append(row)
            
            # Process each metric group with enhanced mapping
            for group_data in metric_groups.values():
                metric_key = group_data['metric_key']
                subcategory = group_data['subcategory']
                rows = group_data['rows']
                
                # Process each category/program column
                for i, category in enumerate(all_categories):
                    if category not in hierarchical_result:
                        hierarchical_result[category] = {}
                    
                    # Enhanced row mapping logic
                    row_index = self._find_row_index_for_category(headers, category, all_categories, i)
                    
                    if row_index < len(rows):
                        row = rows[row_index]
                        
                        # Process all time columns for this category
                        category_data = {}
                        for time_col in time_columns:
                            value = row.get(time_col, '')
                            year = self._extract_year_from_column(time_col)
                            
                            if year and value:
                                if year not in hierarchical_result[category]:
                                    hierarchical_result[category][year] = {}
                                
                                # Enhanced value conversion
                                converted_value = self._convert_metric_value(value, metric_key)
                                if converted_value is not None:
                                    # Store with subcategory if present
                                    if subcategory:
                                        if subcategory not in hierarchical_result[category][year]:
                                            hierarchical_result[category][year][subcategory] = {}
                                        hierarchical_result[category][year][subcategory][metric_key] = converted_value
                                    else:
                                        hierarchical_result[category][year][metric_key] = converted_value
            
            # Return enhanced hierarchical structure with metadata
            if hierarchical_result and any(hierarchical_result.values()):
                return {
                    'type': 'hierarchical',
                    'table_index': table_index,
                    'data': hierarchical_result,
                    'metadata': {
                        'time_columns': time_columns,
                        'categories': all_categories,
                        'total_metrics': len(metric_groups)
                    }
                }
        
        # Return enhanced tabular data if not hierarchical
        return {
            'type': 'tabular',
            'table_index': table_index,
            'headers': headers,
            'data': data_rows,
            'metadata': {
                'total_rows': len(data_rows),
                'total_columns': len(headers)
            }
        }
    
    def _normalize_metric_key(self, metric_name: str) -> str:
        """Normalize metric names to consistent keys"""
        metric_name = metric_name.lower().strip()
        
        # Common metric mappings
        metric_mappings = {
            'median package': 'median_package_lpa',
            'average package': 'average_package_lpa',
            'highest package': 'highest_package_lpa',
            'no. of students graduating': 'students_graduating',
            'number of students graduating': 'students_graduating',
            'students graduating': 'students_graduating',
            'no. of students placed': 'students_placed',
            'number of students placed': 'students_placed',
            'students placed': 'students_placed',
            'placement rate': 'placement_rate_percentage',
            'placement percentage': 'placement_rate_percentage'
        }
        
        for key, normalized in metric_mappings.items():
            if key in metric_name:
                return normalized
        
        # Default: snake_case conversion
        return re.sub(r'[^a-z0-9]+', '_', metric_name).strip('_')
    
    def _extract_subcategory(self, particulars: str) -> Optional[str]:
        """Extract subcategory from particulars (e.g., 'Computer Science - Placement Rate')"""
        if not particulars:
            return None
        
        # Look for common subcategory patterns
        separators = [' - ', ' | ', ': ', ' (', ') ']
        for sep in separators:
            if sep in particulars:
                parts = particulars.split(sep)
                if len(parts) >= 2:
                    # Return the subcategory part
                    return parts[-1].strip()
        
        return None
    
    def _find_row_index_for_category(self, headers: List[str], category: str, all_categories: List[str], category_index: int) -> int:
        """Find the correct row index for a given category in hierarchical data"""
        try:
            # Count how many category columns come before the current one
            preceding_categories = all_categories[:category_index]
            category_positions = [headers.index(cat) for cat in preceding_categories if cat in headers]
            
            # Row index is based on the position of the category in headers
            return len(category_positions)
        except (ValueError, IndexError):
            # Fallback to category index
            return category_index
    
    def _extract_year_from_column(self, column_name: str) -> Optional[str]:
        """Extract year from column name"""
        year_match = re.search(r'(20\d{2})', column_name)
        return year_match.group(1) if year_match else None
    
    def _convert_metric_value(self, value: str, metric_key: str):
        """Convert metric value to appropriate type"""
        if not value or not value.strip():
            return None
        
        value = value.strip()
        
        # Handle different metric types
        if 'package' in metric_key or 'lpa' in metric_key:
            # Extract numeric value from package strings
            num = self.extract_number(value)
            return num
        
        elif 'percentage' in metric_key:
            return self.extract_percentage(value)
        
        elif any(key in metric_key for key in ['students', 'placed', 'graduating']):
            # Extract integer counts
            num = self.extract_number(value)
            return int(num) if num and num.is_integer() else num
        
        else:
            # Try to extract number, otherwise return as string
            num = self.extract_number(value)
            return num if num is not None else value
    
    def _parse_collegedunia_tables(self, placement_data: Dict):
        """Parse raw table data from CollegeDunia to extract structured information"""
        raw_data = placement_data.get('raw_data', [])
        
        for table in raw_data:
            # Handle new format with data array
            if 'data' in table:
                table_rows = table.get('data', [])
                headers = table.get('headers', [])
                
                for row in table_rows:
                    # Check if this is a company table (Company, Package Offered)
                    if len(headers) == 2 and 'Company' in headers[0]:
                        company = row.get(headers[0], '')
                        if company and len(company) < 100 and company not in placement_data['top_recruiters']:
                            placement_data['top_recruiters'].append(company)
                    
                    # Check if this is a companies list table (Companies)
                    elif len(headers) == 1 and 'Companies' in headers[0]:
                        company = row.get(headers[0], '')
                        if company and len(company) < 100 and company not in placement_data['top_recruiters']:
                            placement_data['top_recruiters'].append(company)
            
            # Handle legacy format with values array
            else:
                headers = table.get('headers', [])
                values = table.get('values', [])
                
                if not headers or not values:
                    continue
                
                # Check if this is a company table (Company, Package Offered)
                if len(headers) == 2 and 'Company' in headers[0]:
                    company = values[0] if len(values) > 0 else ''
                    if company and len(company) < 100 and company not in placement_data['top_recruiters']:
                        placement_data['top_recruiters'].append(company)
                
                # Check if this is a companies list table (Companies)
                elif len(headers) == 1 and 'Companies' in headers[0]:
                    for company in values:
                        if company and len(company) < 100 and company not in placement_data['top_recruiters']:
                            placement_data['top_recruiters'].append(company)
    
    def _parse_careers360_tables(self, placement_data: Dict):
        """Parse raw table data from Careers360 to extract structured information"""
        raw_data = placement_data.get('raw_data', [])
        
        for table in raw_data:
            headers = table.get('headers', [])
            table_rows = table.get('data', [])
            
            if not headers or not table_rows:
                continue
            
            # Look for recruiter/company columns
            for row in table_rows:
                for header, value in row.items():
                    if not value:
                        continue
                    
                    # Extract recruiters based on header names
                    if 'recruiter' in header.lower() or 'company' in header.lower():
                        if value and len(value) < 100 and value not in placement_data['top_recruiters']:
                            placement_data['top_recruiters'].append(value)
    
    def scrape_collegedunia(self, college_url: str) -> Dict:
        """Scrape placement data from CollegeDunia"""
        logger.info(f"Scraping CollegeDunia: {college_url}")
        
        soup = self.get_page(college_url)
        if not soup:
            return {}
        
        placement_data = {
            'source': 'collegedunia',
            'url': college_url,
            'placement_statistics': {},
            'top_recruiters': [],
            'raw_data': []
        }
        
        # Extract placement statistics from tables
        tables = soup.find_all('table')
        for table_idx, table in enumerate(tables):
            headers = [self.clean_text(th.get_text()) for th in table.find_all('th')]
            rows = table.find_all('tr')
            
            # Process entire table at once for hierarchical transformation
            table_data = []
            for row in rows[1:]:  # Skip header row
                cells = [self.clean_text(td.get_text()) for td in row.find_all('td')]
                if cells:
                    row_dict = {}
                    for i, cell in enumerate(cells):
                        header = headers[i] if i < len(headers) else f'column_{i}'
                        row_dict[header] = cell
                    table_data.append(row_dict)
            
            if table_data:
                table_dict = {
                    'table_index': table_idx,
                    'headers': headers,
                    'data': table_data
                }
                
                # Apply enhanced hierarchical transformation directly during parsing
                transformed_data = self.transform_hierarchical_data(table_dict)
                
                # Store transformed data with enhanced structure
                if isinstance(transformed_data, dict) and transformed_data.get('type') == 'hierarchical':
                    # Store hierarchical data with metadata
                    placement_data['raw_data'].append(transformed_data)
                else:
                    # Store enhanced tabular data
                    placement_data['raw_data'].append(transformed_data)
        
        # Parse raw table data to extract structured information
        self._parse_collegedunia_tables(placement_data)
        
        # Extract recruiters
        recruiter_section = soup.find(text=re.compile(r'top\s+recruiters?', re.IGNORECASE))
        if recruiter_section:
            parent = recruiter_section.find_parent()
            if parent:
                recruiters = parent.find_all(['li', 'span', 'div'])
                for rec in recruiters:
                    text = self.clean_text(rec.get_text())
                    if text and len(text) < 100:  # Reasonable company name length
                        placement_data['top_recruiters'].append(text)
        
        # Extract from lists and paragraphs
        lists = soup.find_all(['ul', 'ol'])
        for lst in lists:
            items = lst.find_all('li')
            for item in items:
                text = self.clean_text(item.get_text())
                # Check if it might be a company name
                if any(keyword in text.lower() for keyword in ['tcs', 'infosys', 'wipro', 'amazon', 'google', 'microsoft', 'accenture']):
                    if text not in placement_data['top_recruiters'] and len(text) < 100:
                        placement_data['top_recruiters'].append(text)
        
        return placement_data
    
    def scrape_careers360(self, college_url: str) -> Dict:
        """Scrape placement data from Careers360"""
        logger.info(f"Scraping Careers360: {college_url}")
        
        soup = self.get_page(college_url)
        if not soup:
            return {}
        
        placement_data = {
            'source': 'careers360',
            'url': college_url,
            'placement_statistics': {},
            'top_recruiters': [],
            'program_wise_data': [],
            'nirf_data': {},
            'raw_data': []
        }
        
        # Extract all tables for structured data
        tables = soup.find_all('table')
        for idx, table in enumerate(tables):
            headers = [self.clean_text(th.get_text()) for th in table.find_all('th')]
            rows = table.find_all('tr')
            
            table_data = []
            for row in rows[1:]:
                cells = [self.clean_text(td.get_text()) for td in row.find_all('td')]
                if cells:
                    row_dict = {}
                    for i, cell in enumerate(cells):
                        header = headers[i] if i < len(headers) else f'column_{i}'
                        row_dict[header] = cell
                    table_data.append(row_dict)
            
            if table_data:
                table_dict = {
                    'table_index': idx,
                    'headers': headers,
                    'data': table_data
                }
                
                # Apply enhanced hierarchical transformation directly during parsing
                transformed_data = self.transform_hierarchical_data(table_dict)
                
                # Store transformed data with enhanced structure
                if isinstance(transformed_data, dict) and transformed_data.get('type') == 'hierarchical':
                    # Store hierarchical data with metadata
                    placement_data['raw_data'].append(transformed_data)
                else:
                    # Store enhanced tabular data
                    placement_data['raw_data'].append(transformed_data)
        
        # Parse raw table data to extract structured information
        self._parse_careers360_tables(placement_data)
        
        # Extract recruiters from lists
        recruiter_keywords = ['recruiters', 'companies', 'top recruiters']
        for keyword in recruiter_keywords:
            sections = soup.find_all(text=re.compile(keyword, re.IGNORECASE))
            for section in sections:
                parent = section.find_parent()
                if parent:
                    # Find nearby lists
                    nearby_lists = parent.find_all(['ul', 'ol'])
                    for lst in nearby_lists:
                        items = lst.find_all('li')
                        for item in items:
                            text = self.clean_text(item.get_text())
                            if text and len(text) < 100 and text not in placement_data['top_recruiters']:
                                placement_data['top_recruiters'].append(text)
        
        # Extract NIRF data if available
        page_text = soup.get_text()
        nirf_mentions = re.findall(r'NIRF\s+(?:report|data|ranking)?\s*(\d{4})', page_text, re.IGNORECASE)
        if nirf_mentions:
            placement_data['nirf_data']['year'] = nirf_mentions[0]
        
        # Extract student placed count
        students_placed = re.findall(r'(\d+)\s*students?\s+(?:got\s+)?placed', page_text, re.IGNORECASE)
        if students_placed:
            placement_data['placement_statistics']['students_placed'] = int(students_placed[0])
        
        return placement_data
    
    def scrape_shiksha(self, college_url: str) -> Dict:
        """Scrape placement data from Shiksha using the dedicated Shiksha scraper"""
        logger.info(f"Scraping Shiksha: {college_url}")
        
        try:
            shiksha_scraper = ShikshaPlacementScraper()
            data = shiksha_scraper.scrape(college_url)
            
            # Transform Shiksha data to match our format
            placement_data = {
                'source': 'shiksha',
                'url': college_url,
                'placement_statistics': {},
                'top_recruiters': [],
                'program_wise_data': data.get('program_wise_data', []),
                'raw_data': data.get('raw_data', [])
            }
            
            return placement_data
            
        except Exception as e:
            logger.error(f"Error scraping Shiksha: {str(e)}")
            return {}
    
    def scrape_college(self, collegedunia_url: str = None, careers360_url: str = None, shiksha_url: str = None, college_name: str = None) -> Dict:
        """Scrape placement data from both sources for a college"""
        
        if not college_name:
            college_name = "Unknown College"
        
        college_data = {
            'data_sources': [],
            'source_data': {}
        }
        
        # Scrape CollegeDunia
        if collegedunia_url:
            cd_data = self.scrape_collegedunia(collegedunia_url)
            if cd_data:
                college_data['source_data']['collegedunia'] = cd_data
                college_data['data_sources'].append('collegedunia')
        
        # Scrape Careers360
        if careers360_url:
            c360_data = self.scrape_careers360(careers360_url)
            if c360_data:
                college_data['source_data']['careers360'] = c360_data
                college_data['data_sources'].append('careers360')
        
        # Scrape Shiksha
        if shiksha_url:
            shiksha_data = self.scrape_shiksha(shiksha_url)
            if shiksha_data:
                college_data['source_data']['shiksha'] = shiksha_data
                college_data['data_sources'].append('shiksha')
        
        return college_data
    
    def _consolidate_data(self, college_data: Dict):
        """Consolidate data from multiple sources"""
        
        sources = college_data.get('source_data', {})
        all_recruiters = set()
        
        for source_name, source_data in sources.items():
            # Recruiters
            recruiters = source_data.get('top_recruiters', [])
            all_recruiters.update(recruiters)
        
        # Consolidate recruiters
        if college_data.get('consolidated_data'):
            college_data['consolidated_data']['top_recruiters'] = sorted(list(all_recruiters))
    
    def load_from_json(self, filename: str = 'college_placement_data.json'):
        """Load existing collected data from JSON file if it exists"""
        if os.path.exists(filename):
            try:
                with open(filename, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.colleges_data.update(data)
                        logger.info(f"Loaded {len(data)} existing colleges from {filename}")
            except Exception as e:
                logger.error(f"Error loading existing data from {filename}: {str(e)}")

    def save_to_json(self, filename: str = 'college_placement_data.json'):
        """Save collected data to JSON file"""
        logger.info(f"Saving data to {filename}")
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(self.colleges_data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Data saved successfully to {filename}")
    
    def add_college(self, college_name: str, collegedunia_url: str = None, careers360_url: str = None, shiksha_url: str = None, force_refresh: bool = False):
        """Add a college to scrape. If data already exists, skip unless force_refresh is True."""
        import re
        def norm(s):
            return re.sub(r'[^a-z0-9]', '', s.lower().replace("&", "and"))
        
        c_norm = norm(college_name)
        matched_key = None
        for k in self.colleges_data.keys():
            if norm(k) == c_norm:
                matched_key = k
                break
                
        if not force_refresh and matched_key:
            existing = self.colleges_data[matched_key]
            if existing and existing.get('data_sources'):
                logger.info(f"College {matched_key} already exists with data. Skipping scrape.")
                return existing

        logger.info(f"Adding college: {college_name}")
        
        college_data = self.scrape_college(
            collegedunia_url=collegedunia_url,
            careers360_url=careers360_url,
            shiksha_url=shiksha_url,
            college_name=college_name
        )
        
        key_to_use = matched_key if matched_key else college_name
        self.colleges_data[key_to_use] = college_data
        
        return college_data


def main():
    """Main execution function"""
    
    # Initialize scraper
    scraper = CollegePlacementScraper()
    
    # Example colleges to scrape
    colleges = [
        {
            'name': 'ITS Engineering College Greater Noida',
            'collegedunia': 'https://collegedunia.com/college/13761-its-engineering-college-greater-noida/placement',
            'careers360': None
        },
        {
            'name': 'Maitreyi College Delhi',
            'collegedunia': 'https://collegedunia.com/college/2849-maitreyi-college-new-delhi/placement',
            'careers360': None
        },
        # Add more colleges here
    ]
    
    # Scrape each college
    for college in colleges:
        try:
            scraper.add_college(
                college_name=college['name'],
                collegedunia_url=college.get('collegedunia'),
                careers360_url=college.get('careers360')
            )
            logger.info(f"Successfully scraped: {college['name']}")
        except Exception as e:
            logger.error(f"Error scraping {college['name']}: {str(e)}")
    
    # Save to JSON
    scraper.save_to_json('college_placement_data.json')
    
    logger.info("Scraping completed!")


if __name__ == "__main__":
    main()
