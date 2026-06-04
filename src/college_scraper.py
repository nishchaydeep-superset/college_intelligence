"""
college_scraper.py

Two pipelines:
  1. fetch_official(college_name, url)  -> scrape official site -> Gemini formats as plain text
  2. fetch_external(college_name)       -> Gemini grounding across web -> plain text

Returns plain descriptive text — no JSON, no markdown symbols.
Max detail requested in prompts.
"""

from __future__ import annotations

import os
import re
import time
from typing import Any

import httpx
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BLOCKED_DOMAINS = ["collegeduniya.com", "careers360.com", "shiksha.com"]

OFFICIAL_SUBPATHS = [
    "",
    "/placements",
    "/placement",
    "/tpo",
    "/training-and-placement",
    "/academics",
    "/departments",
    "/research",
    "/admissions",
    "/admission",
    "/faculty",
    "/about",
    "/about-us",
    "/fees",
    "/fee-structure",
    "/rankings",
    "/infrastructure",
    "/campus-life",
    "/student-life",
    "/hostel",
    "/research-and-development",
    "/industry",
    "/contact",
    "/naac",
    "/nirf",
    "/scholarships",
    "/library",
    "/sports",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

FETCH_TIMEOUT = 15
MAX_OFFICIAL_PAGES = 12
MAX_TEXT_PER_PAGE = 20000
MAX_TOTAL_TEXT = 80000


# ---------------------------------------------------------------------------
# HTML fetch + clean
# ---------------------------------------------------------------------------

def _clean_text(html: str) -> str:
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return "\n".join(lines)


def _college_name_in_text(college_name: str, text: str) -> bool:
    text_lower = text.lower()
    name_words = [w for w in re.split(r"\W+", college_name) if len(w) > 3]
    if any(w.lower() in text_lower for w in name_words):
        return True
    generic_keywords = [
        "institute of technology", "national institute", "engineering college",
        "university", "placement", "admission", "academic", "department",
        "faculty", "campus", "b.tech", "m.tech", "naac", "nirf", "autonomous",
    ]
    return any(kw in text_lower for kw in generic_keywords)


def _is_ac_in_domain(url: str) -> bool:
    return bool(re.search(r"\.(ac\.in|edu\.in)(/|$)", url))


def _fetch_page(url: str) -> str | None:
    try:
        with httpx.Client(headers=HEADERS, timeout=FETCH_TIMEOUT,
                          follow_redirects=True) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                ct = resp.headers.get("content-type", "")
                if "html" in ct or "text" in ct:
                    return _clean_text(resp.text)
    except Exception:
        pass
    return None


# ---------------------------------------------------------------------------
# Gemini client + generate
# ---------------------------------------------------------------------------

def _gemini_client():
    try:
        from google import genai
    except ImportError as e:
        raise RuntimeError("Install google-genai") from e

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        try:
            from src import research_settings as rs
            api_key = getattr(rs, "GEMINI_API_KEY", "")
        except ImportError:
            try:
                import research_settings as rs  # type: ignore
                api_key = getattr(rs, "GEMINI_API_KEY", "")
            except ImportError:
                pass
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set")
    return genai.Client(api_key=api_key)


def _get_response_text(response: Any) -> str:
    try:
        t = (response.text or "").strip()
        if t:
            return t
    except Exception:
        pass
    try:
        parts = []
        for cand in (response.candidates or []):
            for p in (getattr(getattr(cand, "content", None), "parts", None) or []):
                t = getattr(p, "text", None)
                if t:
                    parts.append(t)
        return "\n".join(parts).strip()
    except Exception:
        return ""


def _grounding_sources(response: Any) -> list[dict]:
    out = []
    try:
        for cand in (response.candidates or []):
            gm = getattr(cand, "grounding_metadata", None)
            if not gm:
                continue
            for ch in (getattr(gm, "grounding_chunks", None) or []):
                web = getattr(ch, "web", None)
                if web:
                    uri = str(getattr(web, "uri", "") or "")
                    title = str(getattr(web, "title", "") or "")
                    if uri or title:
                        out.append({"title": title, "link": uri})
    except Exception:
        pass
    return out[:24]


def _gemini_generate(prompt: str, use_grounding: bool = False) -> tuple[str, list[dict]]:
    from google.genai import types

    client = _gemini_client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    tools = [types.Tool(google_search=types.GoogleSearch())] if use_grounding else []
    config = types.GenerateContentConfig(
        tools=tools,
        temperature=0.1,
        max_output_tokens=16000,
    )

    response = client.models.generate_content(
        model=model,
        contents=[types.Content(
            role="user",
            parts=[types.Part.from_text(text=prompt)]
        )],
        config=config,
    )

    text = _get_response_text(response)
    sources = _grounding_sources(response) if use_grounding else []
    return text, sources


# ---------------------------------------------------------------------------
# URL Discovery
# ---------------------------------------------------------------------------

DISCOVER_PROMPT = (
    "What is the official website URL of {college} in India? "
    "Return ONLY the base URL (e.g. https://www.bits-pilani.ac.in). "
    "No explanation, just the URL."
)


def discover_official_url(college_name: str) -> str | None:
    prompt = DISCOVER_PROMPT.format(college=college_name)
    try:
        raw, _ = _gemini_generate(prompt, use_grounding=True)
        match = re.search(r"https?://[^\s\"'<>]+", raw.strip())
        if not match:
            return None
        return match.group(0).rstrip("/.,)")
    except Exception:
        return None


def auto_confirm_url(college_name: str, url: str) -> tuple[bool, str]:
    """
    Three-tier confirmation:
    1. .ac.in / .edu.in domain -> trust immediately
    2. Page loads + keywords found -> confirmed
    3. Page loads but no keywords -> still confirmed (reachable is good enough)
    4. Page cannot be fetched -> unconfirmed
    """
    if _is_ac_in_domain(url):
        return True, "Confirmed: Indian academic domain (.ac.in / .edu.in)"

    text = _fetch_page(url)
    if text is None:
        return False, "Could not fetch the page (timeout or bot-block). Use Fix URL to set manually."

    if _college_name_in_text(college_name, text):
        return True, "College name / keywords found in page content"

    return True, "Page loaded successfully (URL is reachable)"



OFFICIAL_PARSE_PROMPT = """You are a senior college research analyst compiling a comprehensive
institutional profile for {college} based on data from their official website.
do not need to specofy the pages crawled like this: Pages crawled: //admissions/about/campus-life/contact
Your task is to write a VERY DETAILED, EXHAUSTIVE report in plain prose.
Do not speicfy the source from where you are collecting the data just give the data in the way it is described below.
Do not use any markdown symbols like #, *, -, or bullet points.
Do not use bold or italic formatting.
Write in clear paragraphs with section headings in PLAIN CAPITAL LETTERS.
Write as much as possible - the goal is to capture every single piece of
information present in the scraped content. The report should be extremely
long and detailed - do not summarize or shorten anything.

Use the exact numbers, names, percentages, LPA figures, company names,
contact details, email addresses, phone numbers, and dates exactly as they
appear in the content. Do not paraphrase specific data - copy it exactly.

Structure your report with these sections (write everything you find for each,
skip a section only if absolutely no data exists for it):
 start directly with the topic no need to mention the pages crawled or even mention anything about that. 

PLACEMENTS

Write every detail about placements you can find. Include the exact average CTC
in LPA, highest CTC in LPA, median CTC in LPA, total number of students placed,
placement percentage, number of companies that visited, number of offers made,
pre-placement offers count, international offers count. Write year-wise data for
every year mentioned (e.g., 2019-20, 2020-21, 2021-22, 2022-23, 2023-24).
List every single company name mentioned as a recruiter. Include internship
statistics separately - average stipend, companies offering internships, number
of students who got internships. Include department-wise placement statistics if
available (CSE placement rate, ECE placement rate, etc.). Include details about
placement drives, pre-placement talks, and the placement process.
Contact details of the placement cell including email addresses and phone numbers.


ACADEMIC PROGRAMS AND DEPARTMENTS

List every single program offered - every B.Tech branch with intake numbers,
every M.Tech specialization with intake numbers, MBA programs, PhD programs,
any diploma or certificate programs. For each program write the duration,
total seats, eligibility criteria. List all departments with their full names.
Include information about the academic calendar, semester system, credit system,
grading system, minimum attendance requirements, examination pattern.
Write about any special programs, honors courses, minor degrees, electives offered.
Include details about the curriculum, course structure, and any recent changes
to the academic programs.


FACULTY AND ACADEMICS

Write the total number of faculty members, number of professors, associate
professors, assistant professors. Write the percentage with PhD degrees.
Write the student to faculty ratio. List any notable faculty members mentioned
by name along with their designation, specialization, and achievements.
Include visiting faculty or industry experts if mentioned.
Write about teaching methodology, academic rigor, research opportunities
for students, and faculty accessibility.


RESEARCH AND DEVELOPMENT

Write about every research center and laboratory mentioned by name.
Include details of funded research projects - the funding agency (DST, SERB,
DRDO, industry), the amount funded, the duration, and the topic.
Write the total research funding received. Include number of publications,
patents filed, patents granted. Write about PhD enrollment and completion rates.
List research collaborations with other institutions or industry.
Include details of any research journals published by the institution.


RANKINGS AND ACCREDITATIONS

Write the NIRF ranking for every year it is mentioned, with the exact rank
and category (Overall, Engineering, etc.). Write the NAAC grade, NAAC score,
and the year of accreditation. Write about NBA accreditation - which programs
are NBA accredited and for which period. Write about any international rankings.
Include ISO certifications, AICTE approvals, UGC recognition details.
Write about any awards or recognitions received by the institution.


FEES AND SCHOLARSHIPS

Write the complete fee structure in detail. Include tuition fees per semester
and per year for every program. Include development fees, examination fees,
laboratory fees, library fees, and any other charges. Write the total fees
for the complete duration of each program. Write hostel fees per semester and
per year for different types of rooms (single, double, triple). Write mess
fees per month or per semester. Write about scholarships - Merit scholarships,
government scholarships (SC/ST/OBC), sports scholarships, institute merit
scholarships - with exact amounts and eligibility criteria. Write about fee
waivers and financial assistance programs. Include bank loan tie-ups if mentioned.


ADMISSIONS

Write about admission criteria for every program. For B.Tech write the JEE Main
and JEE Advanced cutoff ranks for different categories (General, OBC, SC, ST, EWS)
for every year mentioned. For M.Tech write GATE score requirements and cutoffs.
For MBA write CAT/MAT/XAT score requirements. Write about the admission process,
important dates, application procedure, and documents required. Include details
about lateral entry admissions. Write about any institute-level entrance tests.
Include information about NRI/foreign national admissions if mentioned.


INFRASTRUCTURE AND CAMPUS

Write the total campus area in acres or hectares. Describe every building and
facility mentioned. Write about hostel facilities - number of hostels,
capacity of each hostel, facilities in hostels (wifi, laundry, gym, TV room etc.).
Write about the library - number of books, journals, digital resources,
e-learning resources. Write about laboratories - list every lab by name with
equipment details if mentioned. Write about sports facilities - every sport
mentioned, courts, grounds, gymnasium details. Write about medical facilities,
hospital or dispensary on campus. Write about transportation facilities, buses,
connectivity. Write about canteen and food facilities. Write about auditoriums,
conference halls, seminar rooms with capacity. Write about ATM, bank, post office
on campus. Write about wifi and internet connectivity. Write about power backup
and other utilities.


STUDENT LIFE AND ACTIVITIES

Write about every student club and society mentioned by name.
Write about technical festivals - name, date, scale, events, prizes.
Write about cultural festivals - name, date, events.
Write about sports events and achievements.
Write about student governance - student council, student body.
Write about NSS, NCC activities.
Write about entrepreneurship cell and incubation activities.
Write about alumni association and its activities.


INDUSTRY CONNECT

List every company mentioned in MoU agreements.
Write about industry-sponsored labs or chairs.
Write about internship tie-ups and industry training programs.
Write about the incubation center if any - number of startups, funding raised.
Write about industry advisory board members if mentioned.
Write about consultancy projects undertaken.


CONTACT AND GENERAL INFORMATION

Write the complete address including street, city, state, PIN code.
Write every phone number mentioned.
Write every email address mentioned - director's email, registrar email,
placement cell email, admissions email, etc.
Write the institution's founding year, type (government/private/deemed/autonomous),
affiliating university if applicable.
Write about the governance structure - Board of Governors, Senate, etc.
Write about the total student strength across all programs.
Write any other general information available.


SCRAPED CONTENT FROM OFFICIAL WEBSITE:
{content}

Remember: Write EVERYTHING. Do not skip any detail. Do not summarize.
The report should be as long as needed to capture all information.
Write in plain paragraphs, no bullet points, no markdown, no special symbols.
Use CAPITAL LETTERS only for section headings.
"""


def fetch_official(college_name: str, base_url: str) -> dict[str, Any]:
    """
    Crawl official website subpages, combine text, send to Gemini.
    Returns dict with 'text' key — plain prose, always renderable.
    """
    base_url = base_url.rstrip("/")
    pages_text: list[str] = []
    pages_crawled: list[str] = []

    for subpath in OFFICIAL_SUBPATHS:
        if len(pages_crawled) >= MAX_OFFICIAL_PAGES:
            break
        url = base_url + subpath
        text = _fetch_page(url)
        if text and len(text) > 200:
            pages_text.append(f"=== PAGE: {url} ===\n{text[:MAX_TEXT_PER_PAGE]}")
            pages_crawled.append(url)
        time.sleep(0.3)

    if not pages_text:
        # Scraping failed — fall back to Gemini grounding
        fallback_prompt = (
            f"Search the official website of {college_name} in India "
            f"(URL: {base_url}) using Google Search. "
            f"Find and report every detail available on their official website including "
            f"placements with exact CTC figures and company names, all academic programs "
            f"and fees, faculty details, research, rankings, admissions cutoffs, "
            f"infrastructure, and contact information. "
            f"Write a very long detailed plain text report. "
            f"No bullet points, no markdown. Use CAPITAL LETTERS for section headings. "
            f"Include every number, email address, phone number, and name you find."
        )
        try:
            text_out, _ = _gemini_generate(fallback_prompt, use_grounding=True)
            if not text_out:
                text_out = (
                    "Could not retrieve data from the official website. "
                    "The site may be blocking automated access. "
                    "Please check the external sources section for information "
                    "gathered from other web sources."
                )
            else:
                text_out = (
                    "NOTE: Direct scraping of the official website was blocked. "
                    "The following data was retrieved via Google Search.\n\n"
                    + text_out
                )
        except Exception as e:
            text_out = (
                f"Could not fetch official website data: {e}. "
                "Check external sources section for information."
            )

        return {
            "fetched_at": _now_iso(),
            "pages_crawled": [],
            "text": text_out,
            "scrape_method": "gemini_grounding_fallback",
        }

    combined = "\n\n".join(pages_text)[:MAX_TOTAL_TEXT]
    prompt = OFFICIAL_PARSE_PROMPT.format(college=college_name, content=combined)

    try:
        text_out, _ = _gemini_generate(prompt, use_grounding=False)
        if not text_out:
            text_out = "No data could be extracted. Try the Regenerate button."
    except Exception as e:
        text_out = f"Error generating report: {e}"

    return {
        "fetched_at": _now_iso(),
        "pages_crawled": pages_crawled,
        "text": text_out,
        "scrape_method": "direct_scrape",
    }


# ---------------------------------------------------------------------------
# Pipeline B: External Sources
# ---------------------------------------------------------------------------

EXTERNAL_PROMPT = """You are a senior college research analyst. Search the web
extensively and compile a comprehensive, exhaustive report about {college} in India.
No need for something like : Pages crawled: //placements/placement/tpo/training-and-placement/academics/departments/research/admissions/admission/faculty/about
STRICTLY DO NOT use or reference these websites:
collegeduniya.com, careers360.com, shiksha.com
You should not specify the sources in the description.You should just give the details of the college.
Search and gather data from ALL of the following sources:
- nirfindia.org for official NIRF rankings
- naac.gov.in for NAAC accreditation data
- The college official LinkedIn page
- Reddit threads on r/Indian_Academia, r/jee, r/iit, r/cscareerquestionsIN,
  r/developersIndia, r/india and any other relevant subreddits related to the college.
- Quora questions and answers about this college
- Google Reviews of the college
- Times of India articles
- The Hindu articles
- Hindustan Times articles
- NDTV Education articles
- India Today Education articles
- The Print articles
- Wire articles
- Economic Times Education articles
- YouTube video descriptions about college reviews and vlogs
- LinkedIn posts by alumni and current students
- LinkedIn company page of the college
- Alumni profiles on LinkedIn to understand career outcomes
- Glassdoor reviews for placement and work culture feedback
- AmbitionBox reviews if available
- Internshala placement reports
- Company hiring blogs mentioning campus recruitment
- Google Scholar for research output
- ResearchGate profiles of faculty
- AICTE approval documents on aicte-india.org
- UGC recognition data on ugc.ac.in
- NIRF data portal
- Any news articles or press releases about the college

Dont include in the report : sources used and excluded sources
Write an EXHAUSTIVE, VERY LONG, HIGHLY DETAILED report in plain prose.
Do not include the count of words saying we already have this much details
Do not use any markdown symbols like #, *, -, or bullet points.
Do not use bold or italic formatting.
Write in clear paragraphs with section headings in PLAIN CAPITAL LETTERS.
The report should be extremely long - include every piece of information you find.
Write at least 4000 to 5000 words covering all sections below.
Do not summarize - write everything in full detail.
Use exact numbers, exact LPA figures, exact company names, exact rank numbers.
When information comes from student reviews, note it as such.
When information is verified from official sources, note it as such.


PLACEMENTS

Search for and report every available detail about placements at this college.
Write the average CTC in LPA with the exact figure and year. Write the highest
CTC ever achieved with the company name and year. Write the median CTC.
Write the total number of students who appeared for placements and how many
were placed. Calculate and write the placement percentage. Write year-wise
placement statistics for every year available (2019-20 through 2023-24 minimum).
List every single company that has recruited from this college - separate lists
for product companies, service companies, core companies, finance companies,
consulting companies. Write specific roles offered by specific companies.
Write which companies are the most frequent recruiters and how many offers they
make. Write about pre-placement offers and which companies give them. Write
about international placements - which country, which company, which package.
Write about highest domestic package with company name and year.
Write student reviews and experiences about the placement process - both positive
and negative. Note discrepancies between official claims and what students report.
Write about internship placements separately - average stipend, companies,
conversion rates from internship to full-time. Write about placement cell
contact - email address and phone number if findable.


ACADEMICS AND CURRICULUM

Write about the quality of academics based on student reviews and external
assessments. Write about all programs offered - B.Tech branches, M.Tech
specializations, MBA, PhD programs. Write about curriculum quality - is it
industry-relevant, how frequently is it updated, what do students say about
it. Write about the examination system, grading, academic pressure. Write
about quality of study material, access to online resources, e-learning
platforms used. Write about faculty quality from student perspective - teaching
quality, availability, research orientation. Write about academic rigor and
how it compares to peer institutions. Write about any special academic programs,
honors, minors, industry tie-up courses. Write about attendance policies and
their implementation.


RANKINGS AND RECOGNITION

Write the NIRF ranking for every available year - Overall rank, Engineering rank,
and any other category. State the exact NIRF score breakdown if available
(Teaching, Learning and Resources score, Research and Professional Practice
score, Graduation Outcomes score, Outreach and Inclusivity score, Peer
Perception score). Write the NAAC grade and score with the year of assessment.
Write which programs have NBA accreditation and for which cycle. Write about
any international rankings if applicable. Write about government recognition -
NIT status, Deemed University status, Institute of National Importance status,
Autonomous status. Write about any awards, rankings, or recognitions from
education publications or government bodies.


FEES STRUCTURE

Write the complete fee structure as reported by students and available sources.
Write tuition fees per semester for B.Tech, M.Tech, MBA. Write total fees for
the complete program duration. Write hostel fees with different room types.
Write mess charges. Write any other fees like development fee, exam fee,
lab fee, library fee, sports fee. Write the total annual cost of attendance.
Write about scholarship availability - Merit cum Means scholarships, government
scholarships for SC/ST/OBC/EWS students, sports scholarships - with amounts.
Write about fee waivers and financial assistance. Write what students actually
pay versus what is officially listed. Write about education loan availability
and which banks provide loans easily.


STUDENT LIFE AND CAMPUS CULTURE

Write in great detail about student life based on reviews, Reddit posts, Quora
answers, YouTube vlogs, and any other sources. Write about the campus environment
and atmosphere. Write about hostel life - quality of rooms, cleanliness, food
quality in mess (mention specific complaints or praises), water and electricity
supply, wifi quality in hostels. Write about ragging situation and discipline.
Write about safety on campus for all genders. Write about the social life,
how friendly the environment is, the cultural diversity of the student body.
Write about every technical festival - name, when it happens, what events,
how big it is, prizes offered, whether industry people visit. Write about
every cultural festival similarly. Write about sports facilities and the
sporting culture, any notable sports achievements. Write about every student
club - technical clubs, cultural clubs, entrepreneurship clubs, social service
clubs - by name if available. Write about the political environment on campus.
Write about what a typical day looks like for a student. Write about weekends
and free time activities. Write about the nearest city and how students spend
time off campus. Write about senior-junior relationship culture.


FACULTY AND TEACHING QUALITY

Write about faculty quality from external perspectives - student reviews,
alumni feedback, any external assessments. Note the total faculty count,
ratio of PhD holders, research active faculty versus teaching focused faculty.
Write about specific notable professors or researchers if mentioned anywhere
online. Write about how accessible faculty are, quality of mentorship,
career guidance provided. Write about visiting faculty and industry experts
who come to teach. Write about any distinguished alumni who have returned
as faculty. Write about faculty research publications and their impact.


RESEARCH AND INNOVATION

Write about the research output of the institution. Include number of
publications per year if findable, citation counts, h-index of the institution
if available. Write about notable research projects and their funding.
Write about patents filed and granted with details. Write about startups that
have come out of this institution - names of startups, founders, funding raised,
current status. Write about the incubation center or technology business incubator
if present. Write about industry-sponsored research and the companies involved.
Write about research collaborations with foreign universities or institutions.
Write about PhD program quality and the placement of PhD graduates.


INDUSTRY CONNECT AND ALUMNI

Write about industry connections - companies that have signed MoUs, companies
that sponsor labs, companies that regularly engage with the institution.
Write about notable alumni by name - where they work, what positions they hold,
what companies they are in. Write about alumni in senior positions at major
companies (directors, VPs, founders). Write about alumni startups.
Write about how active the alumni network is and how helpful it is for
current students. Write about alumni mentorship programs and how they work.
Write about alumni events and homecoming activities.


INFRASTRUCTURE AND FACILITIES

Write about the physical infrastructure based on student reviews and available
information. Write about the quality of classrooms, labs, and teaching facilities.
Write about the library - number of books, access to digital journals, quality
of reading environment, timing. Write about internet connectivity - speed,
reliability, access in hostels versus academic buildings. Write about sports
infrastructure quality. Write about medical facilities on campus - hospital,
dispensary, doctors, ambulance availability. Write about transportation
connectivity to nearest city, railway station, airport. Write about power backup
and overall infrastructure maintenance quality. Write about cleanliness and
upkeep of campus.


RECRUITER PERSPECTIVE

Write about how recruiters and companies view this college. Is it on the
preferred campus list of major tech companies, consulting firms, or core sector
companies? Write about the quality of talent signal this college sends to
employers. Write about consistency of placement quality year over year.
Write about how this college compares to peer institutions in terms of
recruitment quality. Write about any companies that have stopped recruiting
and why. Write about new companies that have started recruiting and why.
Write about what makes candidates from this college stand out or not stand out.


RECENT NEWS AND DEVELOPMENTS

Write about any news articles from the past 2-3 years about this college.
Write about any controversies or issues - administrative problems, student
protests, fee hike issues, infrastructure complaints. Write about recent
achievements - new rankings, new research grants, new industry tie-ups.
Write about any new programs launched, new buildings constructed, new
facilities added. Write about any changes in leadership or administration.


COMMON PRAISES FROM STUDENTS

Write in detail about what students and alumni consistently praise about
this college based on reviews, Reddit, Quora, and other sources.
Be specific - not just general praise but specific things they appreciate.


COMMON COMPLAINTS FROM STUDENTS

Write in detail about what students and alumni consistently complain about.
Be honest and thorough - include all genuine complaints about academics,
administration, facilities, food, placement process, faculty quality,
internet, hostel, fees, or anything else that comes up repeatedly.


Write at minimum 3000 words. Be exhaustive. Cover every piece of information
available. The person reading this report needs to know everything about this
college without visiting any other website.
"""


def fetch_external(college_name: str) -> dict[str, Any]:
    """
    Use Gemini grounding to gather external info.
    Returns dict with 'text' and 'sources' keys — plain prose.
    """
    from google import genai
    from google.genai import types

    prompt = EXTERNAL_PROMPT.format(college=college_name)
    client = _gemini_client()
    model = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())],
        temperature=0.1,
        max_output_tokens=16000,
    )

    try:
        response = client.models.generate_content(
            model=model,
            contents=[types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)]
            )],
            config=config,
        )
        text_out = _get_response_text(response)
        sources = _grounding_sources(response)

        if not text_out:
            text_out = "No data returned. Try the Regenerate button."

    except Exception as e:
        return {
            "fetched_at": _now_iso(),
            "text": f"Error fetching external data: {e}",
            "sources": [],
        }

    return {
        "fetched_at": _now_iso(),
        "text": text_out,
        "sources": sources,
    }


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()