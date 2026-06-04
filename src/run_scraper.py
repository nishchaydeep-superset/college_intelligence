"""
Main scraper runner
Loads colleges from JSON and scrapes placement data
"""

import json
import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
from college_placement_scraper import CollegePlacementScraper
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/scraper.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)


def load_colleges(filename='data/college_urls.json'):
    """Load colleges from JSON file"""
    try:
        with open(filename, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        logger.error(f"{filename} not found. Please run college_url_manager.py first!")
        return []


def main():
    """Main execution"""
    
    print("="*70)
    print(" College Placement Data Scraper ".center(70, "="))
    print("="*70)
    print()
    
    # Load college list
    colleges = load_colleges('data/college_urls.json')
    
    if not colleges:
        print("No colleges found in data/college_urls.json")
        print("Please run: python src/college_url_manager.py first")
        return
    print(f"Found {len(colleges)} colleges to scrape\n")
    
    # Initialize scraper and load existing data to prevent overwriting
    scraper = CollegePlacementScraper()
    scraper.load_from_json('data/college_placement_data.json')
    
    # Track statistics
    successful = 0
    failed = 0
    
    # Scrape each college
    for idx, college in enumerate(colleges, 1):
        print(f"\n[{idx}/{len(colleges)}] Processing: {college['name']}")
        print("-" * 70)
        
        try:
            # Check if college data already exists in memory to log a cleaner message in console
            import re
            c_norm = re.sub(r'[^a-z0-9]', '', college['name'].lower().replace("&", "and"))
            exists = any(re.sub(r'[^a-z0-9]', '', k.lower().replace("&", "and")) == c_norm for k in scraper.colleges_data.keys() if scraper.colleges_data[k].get('data_sources'))
            
            if exists:
                print("  Data already exists in database. Skipping scrape.")
                result = scraper.add_college(
                    college_name=college['name'],
                    collegedunia_url=college.get('collegedunia_url'),
                    careers360_url=college.get('careers360_url'),
                    shiksha_url=college.get('shiksha_url')
                )
                successful += 1
                continue

            result = scraper.add_college(
                college_name=college['name'],
                collegedunia_url=college.get('collegedunia_url'),
                careers360_url=college.get('careers360_url'),
                shiksha_url=college.get('shiksha_url')
            )
            
            # Display summary
            print(f"  Successfully scraped!")
            print(f"  Sources: {', '.join(result.get('data_sources', []))}")
            
            successful += 1
            # Save results incrementally
            scraper.save_to_json('data/college_placement_data.json')
            
        except Exception as e:
            logger.error(f"✗ Error scraping {college['name']}: {str(e)}")
            failed += 1
    
    # Save results (final write)
    print("\n" + "="*70)
    print("Saving final results...")
    scraper.save_to_json('data/college_placement_data.json')


if __name__ == "__main__":
    main()
