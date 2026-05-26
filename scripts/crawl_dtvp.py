"""
Crawler for dtvp.de — Deutsches Vergabeportal (German public procurement).
Uses the confirmed JWT authentication flow to access the search API and
retrieve real individual tender detail page URLs.

Flow:
  1. GET /Center/common/project/search.do — establishes JSESSIONID cookie
  2. POST /Center/common/project/search.do — returns HTML with <input id="token" value="<JWT>">
  3. POST /Center/api/v2/project/search with X-JWT header — returns JSON with project data
  4. Extract links.ENTER_PROJECTROOM for each project → direct detail page URL
"""

import re
import time
import hashlib
import json
import requests
from datetime import datetime, date

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9",
    "Referer": "https://www.dtvp.de/",
}

KEYWORDS = [
    "Website",
    "Webseite",
    "Webplattform",
    "Digitalisierung",
    "CRM",
    "ERP",
    "PIM",
    "Marketing",
    "Design",
    "App",
    "Online-Plattform",
    "E-Commerce",
    "Softwareentwicklung",
    "UX",
    "UI Design",
]

CATEGORY_MAP = {
    "Website": ["website", "webseite", "webauftritt", "webplattform", "cms", "relaunch"],
    "CRM": ["crm", "customer relationship"],
    "ERP": ["erp", "sap", "s/4hana", "enterprise resource"],
    "PIM": ["pim", "product information"],
    "Marketing": ["marketing", "social media", "seo", "performance marketing", "kampagne"],
    "Design": ["design", "ux", "ui", "usability", "corporate design", "brand"],
    "App": ["app", "applikation", "mobile", "ios", "android"],
    "Digitalisierung": ["digitali", "digital", "e-government", "online-plattform", "e-commerce"],
    "E-Commerce": ["e-commerce", "shop", "b2b plattform"],
    "UX": ["ux research", "usability", "user experience"],
}

BASE_URL = "https://www.dtvp.de"
SEARCH_PAGE = f"{BASE_URL}/Center/common/project/search.do"
API_SEARCH = f"{BASE_URL}/Center/api/v2/project/search"


def make_id(text: str) -> str:
    return "dtvp-" + hashlib.md5(text.encode()).hexdigest()[:10]


def detect_categories(text: str) -> list[str]:
    text_lower = text.lower()
    found = []
    for cat, keywords in CATEGORY_MAP.items():
        if any(kw in text_lower for kw in keywords):
            if cat not in found:
                found.append(cat)
    return found or ["Digitalisierung"]


def get_status(deadline_str: str) -> str:
    try:
        if "." in deadline_str:
            parts = deadline_str.split(".")
            d = date(int(parts[2]), int(parts[1]), int(parts[0]))
        else:
            d = datetime.fromisoformat(deadline_str[:10]).date()
        days_left = (d - date.today()).days
        if days_left < 0:
            return "closed"
        if days_left <= 7:
            return "closing"
        return "open"
    except Exception:
        return "open"


def acquire_jwt(session: requests.Session) -> str | None:
    """Establish JSESSIONID and extract JWT token from search page HTML."""
    try:
        # Step 1: GET to establish session cookie
        session.get(
            SEARCH_PAGE + "?method=showExtendedSearch&fromExternal=true",
            timeout=20,
        )
        time.sleep(1)

        # Step 2: POST to get page with JWT token embedded
        resp = session.post(
            SEARCH_PAGE,
            data={
                "method": "showExtendedSearch",
                "fromExternal": "true",
                "searchText": "Website",
                "page": "1",
                "sortField": "rank",
                "order": "0",
            },
            timeout=30,
        )
        html = resp.content.decode("latin-1", errors="replace")
        m = re.search(r'id="token"[^>]*value="([^"]+)"', html)
        if m:
            return m.group(1)
        print("[DTVP] WARNING: JWT token not found in page HTML")
        return None
    except Exception as e:
        print(f"[DTVP] JWT acquisition failed: {e}")
        return None


def search_keyword(
    session: requests.Session,
    jwt: str,
    keyword: str,
    max_pages: int = 4,
) -> list[dict]:
    """Search for a keyword and return raw project list from API."""
    api_headers = {
        "X-JWT": jwt,
        "Accept": "application/json",
        "Content-Type": "application/json",
        "X-Requested-With": "XMLHttpRequest",
        "Referer": SEARCH_PAGE,
    }
    projects = []
    for page in range(1, max_pages + 1):
        try:
            r = session.post(
                API_SEARCH,
                json={
                    "searchText": keyword,
                    "page": page,
                    "pageSize": 20,
                    "sortField": "rank",
                    "order": 0,
                },
                headers=api_headers,
                timeout=30,
            )
            if r.status_code != 200:
                break
            data = r.json()
            page_projects = data.get("projects", [])
            if not page_projects:
                break
            projects.extend(page_projects)
            # Stop if we got fewer than a full page
            if len(page_projects) < 20:
                break
        except Exception as e:
            print(f"  [DTVP] API error on '{keyword}' page {page}: {e}")
            break
        time.sleep(0.8)
    return projects


def project_to_tender(project: dict, keyword: str) -> dict | None:
    """Convert a raw DTVP API project object to our tender schema."""
    try:
        # Skip awarded contracts
        pub_type = project.get("publicationType", "")
        if "Vergeben" in pub_type or "Award" in pub_type:
            return None

        title = project.get("title", "").strip()
        if not title:
            return None

        pid = project.get("projectId")
        url = project.get("links", {}).get("ENTER_PROJECTROOM", "")
        if not url and pid:
            url = f"{BASE_URL}/Center/public/company/projectForwarding.do?pid={pid}"
        if not url:
            return None

        deadline = project.get("relevantDate", "") or project.get("deadline", "")
        published = project.get("publicationDate", "") or project.get("published", "")
        status = get_status(deadline)
        if status == "closed":
            return None

        org = (
            project.get("organisationName", "")
            or project.get("authority", "")
            or "Deutsche Behörde"
        )

        return {
            "id": make_id(url + title),
            "title": title[:250],
            "description": project.get("description", title)[:500],
            "authority": org[:150],
            "location": project.get("location", "Deutschland"),
            "country": "DE",
            "published": published,
            "deadline": deadline,
            "categories": detect_categories(title + " " + keyword),
            "source": "dtvp",
            "url": url,
            "value": project.get("estimatedValue"),
            "status": status,
        }
    except Exception as e:
        print(f"  [DTVP] Project parse error: {e}")
        return None


def scrape_dtvp() -> list[dict]:
    """Main entry point — scrapes DTVP for all keywords and returns deduplicated results."""
    session = requests.Session()
    session.headers.update(HEADERS)

    print("[DTVP] Acquiring JWT token...")
    jwt = acquire_jwt(session)
    if not jwt:
        print("[DTVP] Could not get JWT — aborting")
        return []
    print(f"[DTVP] JWT acquired: {jwt[:40]}...")

    seen_ids: set[str] = set()
    all_results: list[dict] = []

    for keyword in KEYWORDS:
        print(f"  [DTVP] Searching: '{keyword}'")
        raw_projects = search_keyword(session, jwt, keyword)
        added = 0
        for proj in raw_projects:
            tender = project_to_tender(proj, keyword)
            if tender and tender["id"] not in seen_ids:
                seen_ids.add(tender["id"])
                all_results.append(tender)
                added += 1
        print(f"  [DTVP] +{added} new  |  total: {len(all_results)}")
        time.sleep(1.5)

    print(f"[DTVP] Total unique tenders: {len(all_results)}")
    return all_results


if __name__ == "__main__":
    data = scrape_dtvp()
    print(json.dumps(data, indent=2, ensure_ascii=False))
