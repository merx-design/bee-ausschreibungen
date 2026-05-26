"""
Crawler for dtvp.de — Deutsches Vergabeportal (German public procurement).
Searches for tenders matching digital/web/design keywords.
"""

import re
import time
import hashlib
import requests
from bs4 import BeautifulSoup
from datetime import datetime, date

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Referer": "https://www.dtvp.de/",
}

KEYWORDS = [
    "Digitalisierung",
    "Website",
    "Webseite",
    "Webplattform",
    "CRM",
    "ERP",
    "PIM",
    "Marketing",
    "Design",
    "App",
    "Applikation",
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

# DTVP search endpoints to try
SEARCH_ENDPOINTS = [
    f"{BASE_URL}/Center/announce/search.do",
    f"{BASE_URL}/DTVP/notice/search",
    f"{BASE_URL}/vergabe/suche",
]


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


def parse_date_de(text: str) -> str:
    """Extract first German date (DD.MM.YYYY) from text."""
    m = re.search(r"\d{2}\.\d{2}\.\d{4}", text)
    return m.group(0) if m else ""


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


def parse_dtvp_item(item, keyword: str) -> dict | None:
    """Parse a single result item from any DTVP page layout."""
    try:
        link = item.find("a", href=True)
        if not link:
            return None

        title = link.get_text(strip=True)
        if len(title) < 10:
            # Try parent or sibling for title
            parent = link.parent
            title = parent.get_text(strip=True)[:200] if parent else title

        if not title or len(title) < 5:
            return None

        href = link["href"]
        if href.startswith("/"):
            full_url = BASE_URL + href
        elif href.startswith("http"):
            full_url = href
        else:
            # Fall back to a keyword search — never link to bare homepage
            from urllib.parse import quote
            full_url = f"{BASE_URL}/Center/notice/searchNotice.do?method=showSearchForm&freeText={quote(title[:60])}"

        full_text = item.get_text(" ", strip=True)
        dates = re.findall(r"\d{2}\.\d{2}\.\d{4}", full_text)
        published = dates[0] if len(dates) > 0 else ""
        deadline = dates[-1] if len(dates) > 1 else dates[0] if dates else ""

        # Try to extract authority — look for known patterns
        authority = ""
        auth_el = item.find(class_=re.compile(r"authority|auftraggeber|client|vergabestelle", re.I))
        if auth_el:
            authority = auth_el.get_text(strip=True)

        if not authority:
            # Try to find org-like text after title
            lines = [l.strip() for l in full_text.split("\n") if l.strip()]
            for line in lines[1:4]:
                if len(line) > 5 and not re.search(r"\d{2}\.\d{2}", line):
                    authority = line[:100]
                    break

        categories = detect_categories(title + " " + keyword)
        status = get_status(deadline) if deadline else "open"

        return {
            "id": make_id(full_url + title),
            "title": title[:250],
            "description": full_text[:500] if len(full_text) > 50 else title,
            "authority": authority or "Deutsche Behörde",
            "location": "Deutschland",
            "country": "DE",
            "published": published,
            "deadline": deadline,
            "categories": categories,
            "source": "dtvp",
            "url": full_url,
            "value": None,
            "status": status,
        }
    except Exception as e:
        print(f"  [DTVP] Item parse error: {e}")
        return None


def try_search_endpoint(session: requests.Session, endpoint: str, keyword: str) -> list[dict]:
    """Attempt to search one DTVP endpoint and parse results."""
    results = []
    try:
        params = {
            "method": "searchFormAnnouncements",
            "query": keyword,
            "freeText": keyword,
            "q": keyword,
            "suche": keyword,
            "orderBy": "DATE_DESC",
        }
        resp = session.get(endpoint, params=params, timeout=30, allow_redirects=True)

        if resp.status_code == 404 or "not found" in resp.text.lower()[:200]:
            return []

        soup = BeautifulSoup(resp.text, "lxml")

        # Strategy 1: Table rows
        for table in soup.find_all("table"):
            rows = table.find_all("tr")[1:]
            for row in rows:
                if row.find("a"):
                    item = parse_dtvp_item(row, keyword)
                    if item:
                        results.append(item)

        # Strategy 2: Article / li items
        candidates = soup.find_all(
            ["article", "li", "div"],
            class_=re.compile(r"result|item|announce|tender|vergabe|ausschreibung", re.I),
        )
        for el in candidates:
            if el.find("a"):
                item = parse_dtvp_item(el, keyword)
                if item:
                    results.append(item)

        # Strategy 3: Links in main content
        if not results:
            main_area = soup.find(["main", "section", "div"], id=re.compile(r"content|main|result", re.I))
            if main_area:
                for link in main_area.find_all("a", href=True)[:30]:
                    text = link.get_text(strip=True)
                    if len(text) > 20:
                        item = parse_dtvp_item(link.parent or link, keyword)
                        if item:
                            results.append(item)

    except requests.RequestException:
        pass

    return results


def scrape_dtvp() -> list[dict]:
    """Main entry point — scrapes DTVP for all keywords and returns deduplicated results."""
    session = requests.Session()
    session.headers.update(HEADERS)

    # Initial visit to get cookies
    try:
        session.get(BASE_URL, timeout=15)
        time.sleep(1)
    except Exception:
        pass

    seen_ids = set()
    all_results = []

    for keyword in KEYWORDS:
        print(f"  [DTVP] Searching: '{keyword}'")
        keyword_results = []

        for endpoint in SEARCH_ENDPOINTS:
            items = try_search_endpoint(session, endpoint, keyword)
            keyword_results.extend(items)
            if items:
                break  # Use first endpoint that returns results

        for item in keyword_results:
            if item["id"] not in seen_ids:
                seen_ids.add(item["id"])
                all_results.append(item)

        print(f"  [DTVP] Found {len(all_results)} total so far")
        time.sleep(2.0)

    print(f"[DTVP] Total unique tenders: {len(all_results)}")
    return all_results


if __name__ == "__main__":
    import json
    data = scrape_dtvp()
    print(json.dumps(data, indent=2, ensure_ascii=False))
