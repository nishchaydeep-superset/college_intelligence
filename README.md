College Intelligence Platform — Data Overview

This repository collects placement and institutional intelligence for Indian colleges. Below is a concise summary of the scraped data files.

- **College list**: [data/college_urls.json](data/college_urls.json) — input list of colleges and their known source URLs (CollegeDunia, Careers360, Shiksha, official site overrides).
- **Placement data (primary)**: [data/college_placement_data.json](data/college_placement_data.json) — consolidated placement results collected by `src/college_placement_scraper.py`: tables transformed into JSON, top recruiters lists, program-wise summaries and other placement statistics.
- **General (non-placement) data**: [data/college_general_data.json](data/college_general_data.json) — scraped general pages (overview, highlights, admission, cutoff, facilities, campus, reviews, ranking, fees, courses, etc.) produced by `src/college_general_scraper.py`.
- **Shiksha results**: example outputs from `src/shiksha_scraper.py` (used by the placement pipeline). Some runs save per-college JSON artifacts.
- **Unified output (alternate)**: [data/unified_placements.json](data/unified_placements.json) — produced by `src/unified_scraper.py` (overlaps with `college_placement_data.json` format).
- **Placement season metadata**: [data/placement_seasons.json](data/placement_seasons.json) — seasonal placement details for colleges, including placement months, peak placement windows, eligible student cohorts, notes, accreditation/NAAC grade, and contact details for placement offices.
- **College intelligence cache**: [data/college_intelligence_by_college.json](data/college_intelligence_by_college.json) — intelligence profiles (official + external) produced via `src/college_scraper.py` and exposed through `src/college_intelligence_api.py`.
- **University grouping**: [data/university_grouped_colleges.json](data/university_grouped_colleges.json), [data/college_aliases.json](data/college_aliases.json)

How to run:

1. Activate the virtual environment (example):

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

2. Run the research API (serves UI + endpoints):

```bash
uvicorn src.placement_research_api:app --reload --port 8765
```

