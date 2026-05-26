"""
Crawler for simap.ch — Swiss public procurement platform.
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
    "Accept-Language": "de-CH,de;q=0.9,en;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
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
    "website": ["website", "webseite", "webauftritt", "webplattform", "cms", "relaunch"],
    "CRM": ["crm", "customer relationship"],
    "ERP": ["erp", "sap", "s/4hana", "enterprise resource"],
    "PIM": ["pim", "product information"],
    "Marketing": ["marketing", "social media", "seo", "performance marketing", "kampagne"],
    "Design": ["design", "ux", "ui", "usability", "corporate design", "brand"],
    "App": ["app", "applikation", "mobile", "ios", "android"],
    "Digitalisierung": ["digitali", "digital", "e-government", "online-plattform", "e-commerce"],
    "E-Commerce": ["e-commerce", "shop", "b2b plattform"],
    "UX": ["ux research", "usability", "user experience", "user research"],
}

BASE_URL = "https://www.simap.ch"
SEARCH_URL = f"{BASE_URL}/shabforms/servlet/Search"


def make_id(url_or_text: str) -> str:
    """Generate a stable short ID from a string."""
    return "simap-" + hashlib.md5(url_or_text.encode()).hexdigest()[:10]


def detect_categories(text: str) -> list[str]:
    """Detect relevant categories from tender text."""
    text_lower = text.lower()
    found = []
    for cat, keywords in CATEGORY_MAP.items():
        if any(kw in text_lower for kw in keywords):
            if cat not in found:
                found.append(cat)
    return found or ["Digitalisierung"]


def get_status(deadline_str: str) -> str:
    """Determine tender status from deadline date string."""
    try:
        parts = deadline_str.split(".")
        if len(parts) == 3:
            d = date(int(parts[2]), int(parts[1]), int(parts[0]))
        else:
            d = datetime.fromisoformat(deadline_str).date()
        today = date.today()
        days_left = (d - today).days
        if days_left < 0:
            return "closed"
        if days_left <= 7:
            return "closing"
        return "open"
    except Exception:
        return "open"


def parse_row(row, keyword: str) -> dict | None:
    """Parse a single SIMAP result row."""
    try:
        cells = row.find_all("td")
        if len(cells) < 4:
            return None

        # Try to find a link with the tender title
        link = row.find("a", href=True)
        title = link.get_text(strip=True) if link else cells[2].get_text(strip=True)
        href = link["href"] if link else ""

        if not title or len(title) < 5:
            return None

        if href and href.startswith("/"):
            full_url = BASE_URL + href
        elif href and href.startswith("http"):
            full_url = href
        else:
            full_url = f"{SEARCH_URL}?SIMAP_COMMON_FIELD_LANGUAGE=DE&SIMAP_COMMON_FIELD_PROJECT_TITLE={requests.utils.quote(title[:60])}"

        # Extract cells — SIMAP column order varies but typically:
        # [notice_no, date, title_link, authority, procedure, deadline]
        text_cells = [c.get_text(strip=True) for c in cells]

        # Find date-like fields
        date_pattern = re.compile(r"\d{2}\.\d{2}\.\d{4}")
        dates = [t for t in text_cells if date_pattern.match(t)]
        published = dates[0] if len(dates) > 0 else ""
        deadline = dates[-1] if len(dates) > 1 else dates[0] if dates else ""

        # Authority is usually the cell after the title
        authority = ""
        for i, cell in enumerate(cells):
            if cell.find("a") and i + 1 < len(cells):
                authority = cells[i + 1].get_text(strip=True)
                break

        # Build description from title + keyword context
        description = title

        categories = detect_categories(title + " " + keyword)
        status = get_status(deadline) if deadline else "open"

        return {
            "id": make_id(full_url + title),
            "title": title,
            "description": description,
            "authority": authority or "Schweizer Behörde",
            "location": "Schweiz",
            "country": "CH",
            "published": published,
            "deadline": deadline,
            "categories": categories,
            "source": "simap",
            "url": full_url,
            "value": None,
            "status": status,
        }
    except Exception as e:
        print(f"  [SIMAP] Row parse error: {e}")
        return None


def parse_article(article, keyword: str) -> dict | None:
    """Parse a div/article-based result (alternate SIMAP layout)."""
    try:
        link = article.find("a", href=True)
        title_el = article.find(["h2", "h3", "h4", "strong", "b"])
        title = (title_el or link or article).get_text(strip=True)[:200]

        if not title or len(title) < 5:
            return None

        href = link["href"] if link else ""
        if href and href.startswith("/"):
            full_url = BASE_URL + href
        elif href and href.startswith("http"):
            full_url = href
        else:
            full_url = f"{SEARCH_URL}?SIMAP_COMMON_FIELD_LANGUAGE=DE&SIMAP_COMMON_FIELD_PROJECT_TITLE={requests.utils.quote(title[:60])}"

        text = article.get_text(" ", strip=True)
        date_pattern = re.compile(r"\d{2}\.\d{2}\.\d{4}")
        dates = date_pattern.findall(text)

        published = dates[0] if len(dates) > 0 else ""
        deadline = dates[-1] if len(dates) > 1 else dates[0] if dates else ""

        categories = detect_categories(title + " " + keyword)
        status = get_status(deadline) if deadline else "open"

        return {
            "id": make_id(full_url + title),
            "title": title,
            "description": text[:400] if len(text) > 50 else title,
            "authority": "Schweizer Behörde",
            "location": "Schweiz",
            "country": "CH",
            "published": published,
            "deadline": deadline,
            "categories": categories,
            "source": "simap",
            "url": full_url,
            "value": None,
            "status": status,
        }
    except Exception as e:
        print(f"  [SIMAP] Article parse error: {e}")
        return None


def scrape_simap() -> list[dict]:
    """Main entry point — scrapes SIMAP for all keywords and returns deduplicated results."""
    session = requests.Session()
    session.headers.update(HEADERS)
    seen_ids = set()
    results = []

    for keyword in KEYWORDS:
        print(f"  [SIMAP] Searching: '{keyword}'")
        try:
            params = {
                "SIMAP_COMMON_FIELD_LANGUAGE": "DE",
                "SIMAP_COMMON_FIELD_PROJECT_TITLE": keyword,
                "SIMAP_COMMON_FIELD_SUBMIT": "Suchen",
                "orderBy": "DATUM_PUBLIKATION_DESC",
            }
            resp = session.get(SEARCH_URL, params=params, timeout=30)
            resp.raise_for_status()

            soup = BeautifulSoup(resp.text, "lxml")

            # Strategy 1: table rows
            table = soup.find("table")
            if table:
                rows = table.find_all("tr")[1:]  # skip header
                for row in rows:
                    item = parse_row(row, keyword)
                    if item and item["id"] not in seen_ids:
                        seen_ids.add(item["id"])
                        results.append(item)

            # Strategy 2: article/div-based results
            articles = soup.find_all(["article", "li"], class_=re.compile(r"result|item|announce|ausschreibung", re.I))
            for art in articles:
                item = parse_article(art, keyword)
                if item and item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    results.append(item)

            # Strategy 3: any link in main content area containing procurement terms
            main = soup.find(["main", "div"], id=re.compile(r"content|main|result", re.I))
            if main and not results:
                for link in main.find_all("a", href=True):
                    text = link.get_text(strip=True)
                    if len(text) > 20:
                        href = link["href"]
                        full_url = BASE_URL + href if href.startswith("/") else href
                        item = {
                            "id": make_id(full_url),
                            "title": text[:200],
                            "description": text[:200],
                            "authority": "Schweizer Behörde",
                            "location": "Schweiz",
                            "country": "CH",
                            "published": "",
                            "deadline": "",
                            "categories": detect_categories(text + " " + keyword),
                            "source": "simap",
                            "url": full_url,
                            "value": None,
                            "status": "open",
                        }
                        if item["id"] not in seen_ids:
                            seen_ids.add(item["id"])
                            results.append(item)

            print(f"  [SIMAP] Found {len(results)} total so far")
            time.sleep(2.5)  # polite delay

        except requests.RequestException as e:
            print(f"  [SIMAP] Network error for '{keyword}': {e}")
        except Exception as e:
            print(f"  [SIMAP] Unexpected error for '{keyword}': {e}")

    print(f"[SIMAP] Total unique tenders: {len(results)}")
    return results


if __name__ == "__main__":
    import json
    data = scrape_simap()
    print(json.dumps(data, indent=2, ensure_ascii=False))
