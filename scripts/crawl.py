"""
Main crawler orchestrator for Ausschreibungen.
Runs SIMAP and DTVP scrapers, merges results, and saves to data/tenders.json.
Preserves existing seed/sample data for any IDs not returned by scrapers.
"""

import json
import os
import sys
from datetime import datetime, date, timedelta
from pathlib import Path

# Allow running from any directory
ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "tenders.json"

sys.path.insert(0, str(Path(__file__).parent))

from crawl_simap import scrape_simap
from crawl_dtvp import scrape_dtvp


RELEVANCE_KEYWORDS = [
    "digitali", "website", "webseite", "web", "cms", "crm", "erp", "pim",
    "marketing", "design", "app", "applikation", "mobile", "ux", "ui",
    "online-plattform", "e-commerce", "softwareentwicklung", "sharepoint",
    "intranet", "portal", "plattform", "it-dienstleistung",
]

EXCLUDE_KEYWORDS = [
    "strassenbau", "tiefbau", "hochbau", "reinigung", "catering", "verpflegung",
    "fahrzeug", "fahrzeugbau", "sanitär", "heizung", "elektroinstallation",
    "entsorgung", "abfall", "müll", "gebäude", "immobili", "grundstück",
]


def is_relevant(tender: dict) -> bool:
    """Filter to only keep digitalization-related tenders."""
    text = (tender.get("title", "") + " " + tender.get("description", "")).lower()

    # Must have at least one relevance keyword
    has_relevant = any(kw in text for kw in RELEVANCE_KEYWORDS)
    if not has_relevant:
        return False

    # Must not be primarily an excluded topic
    exclude_count = sum(1 for kw in EXCLUDE_KEYWORDS if kw in text)
    if exclude_count >= 2:
        return False

    return True


def get_status(deadline_str: str) -> str:
    """Compute status from deadline date string (DD.MM.YYYY or YYYY-MM-DD)."""
    if not deadline_str:
        return "open"
    try:
        if "." in deadline_str:
            parts = deadline_str.split(".")
            d = date(int(parts[2]), int(parts[1]), int(parts[0]))
        else:
            from dateutil.parser import parse as dateparse
            d = dateparse(deadline_str).date()

        days_left = (d - date.today()).days
        if days_left < 0:
            return "closed"
        if days_left <= 7:
            return "closing"
        return "open"
    except Exception:
        return "open"


def normalize(tender: dict) -> dict:
    """Normalize and clean a tender dict."""
    # Recompute status in case deadline has changed relative to today
    tender["status"] = get_status(tender.get("deadline", ""))

    # Truncate very long descriptions
    desc = tender.get("description", "")
    if len(desc) > 600:
        tender["description"] = desc[:597] + "…"

    # Ensure required fields
    for field in ["id", "title", "description", "authority", "location", "country",
                  "published", "deadline", "categories", "source", "url", "value", "status"]:
        if field not in tender:
            tender[field] = None if field == "value" else ""

    if not tender["categories"]:
        tender["categories"] = ["Digitalisierung"]

    return tender


def load_existing() -> dict:
    """Load existing tenders.json if it exists."""
    if DATA_FILE.exists():
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARNING] Could not load existing data: {e}")
    return {"tenders": []}


def main():
    print("=" * 60)
    print(f"Ausschreibungen Crawler — {datetime.now().isoformat()}")
    print("=" * 60)

    # Load existing data (seed data + previous crawls)
    existing_data = load_existing()
    existing_tenders = {t["id"]: t for t in existing_data.get("tenders", [])}
    print(f"[INFO] Loaded {len(existing_tenders)} existing tenders")

    # Run scrapers
    print("\n[1/2] Scraping SIMAP.ch...")
    simap_tenders = scrape_simap()

    print("\n[2/2] Scraping DTVP.de...")
    dtvp_tenders = scrape_dtvp()

    # Merge new results
    new_tenders = simap_tenders + dtvp_tenders
    print(f"\n[INFO] Raw scraped: {len(new_tenders)} tenders")

    # Filter for relevance
    relevant = [t for t in new_tenders if is_relevant(t)]
    print(f"[INFO] After relevance filter: {len(relevant)} tenders")

    # Merge into existing (new data wins for same ID)
    merged = dict(existing_tenders)  # start with existing
    for tender in relevant:
        merged[tender["id"]] = normalize(tender)

    # Remove very old closed tenders (> 90 days past deadline)
    cutoff = date.today() - timedelta(days=90)
    final = {}
    for tid, tender in merged.items():
        deadline = tender.get("deadline", "")
        keep = True
        if deadline and tender.get("status") == "closed":
            try:
                if "." in deadline:
                    parts = deadline.split(".")
                    d = date(int(parts[2]), int(parts[1]), int(parts[0]))
                else:
                    from dateutil.parser import parse as dateparse
                    d = dateparse(deadline).date()
                if d < cutoff:
                    keep = False
            except Exception:
                pass
        if keep:
            final[tid] = tender

    # Sort: open first, then by deadline ascending
    def sort_key(t):
        status_order = {"open": 0, "closing": 1, "closed": 2}
        s = status_order.get(t.get("status", "open"), 3)
        deadline = t.get("deadline", "9999-12-31")
        return (s, deadline)

    sorted_tenders = sorted(final.values(), key=sort_key)

    # Count by source
    simap_count = sum(1 for t in sorted_tenders if t.get("source") == "simap")
    dtvp_count = sum(1 for t in sorted_tenders if t.get("source") == "dtvp")

    output = {
        "updated": datetime.utcnow().isoformat() + "Z",
        "total": len(sorted_tenders),
        "sources": {"simap": simap_count, "dtvp": dtvp_count},
        "tenders": sorted_tenders,
    }

    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n{'=' * 60}")
    print(f"✓ Saved {len(sorted_tenders)} tenders to {DATA_FILE}")
    print(f"  SIMAP: {simap_count}  |  DTVP: {dtvp_count}")
    print(f"  Timestamp: {output['updated']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
