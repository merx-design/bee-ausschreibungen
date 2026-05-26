"""
Main crawler orchestrator for Ausschreibungen.
Runs SIMAP and DTVP scrapers, merges results, and saves to data/tenders.json.
Preserves existing seed/sample data for any IDs not returned by scrapers.
"""

import json
import os
import sys
from datetime import datetime, date
from pathlib import Path

# Allow running from any directory
ROOT = Path(__file__).parent.parent
DATA_FILE = ROOT / "data" / "tenders.json"

sys.path.insert(0, str(Path(__file__).parent))

from crawl_simap import scrape_simap
from crawl_dtvp import scrape_dtvp


# ── Strict digital-services-only filter ───────────────────────────────────────
# A tender must contain at least ONE keyword from DIGITAL_REQUIRE
# AND must NOT contain any keyword from HARD_EXCLUDE.
# This ensures only tenders a digital agency (web, CRM, ERP, PIM, UX, etc.)
# would realistically bid on are included — no document scanning, catering,
# construction, pharmaceuticals, etc.

DIGITAL_REQUIRE = [
    # Web
    "website", "webseite", "webauftritt", "webplattform",
    "internetpräsenz", "internetauftritt", "online-auftritt",
    "webanwendung", "webentwicklung", "relaunch",
    # CMS / Portal
    "content management", " cms", "cms-", "typo3", "wordpress", "drupal",
    "intranet", "online-portal", "webportal", "-portal",
    # CRM
    " crm", "crm-", "customer relationship", "kundenmanagementsystem",
    # ERP / SAP
    " erp", "erp-", " sap", "sap-", "s/4hana", "enterprise resource",
    # PIM
    " pim", "pim-", "product information management",
    # Software dev / IT
    "softwareentwicklung", "software-entwicklung", "app-entwicklung",
    "mobile app", "ios-app", "android app",
    " app ",        # standalone "App" word (e.g. "Stadtwerke App", "Markterkundung App")
    "appsecurity", "app security", "app-security",
    "softwarepflege", "softwarewartung", "softwarebetreuung",
    "it-dienstleistung", "it-system", "it-lösung", "it-infrastruktur",
    "it-sicherheit", "it-beratung",
    "schnittstellenmodel", "entwicklungsplattform",
    "auskunftssystem", "fahrplanauskunft",
    # UX / UI
    "user experience", "usability", "ux-design", "ux design",
    "ui design", "ui-design",
    # Digital marketing
    "performance marketing", "social media", "online-marketing",
    "digital marketing", "digitalmarketing", "seo", "sem ",
    "suchmaschinenwerbung", "suchmaschinenoptimierung",
    "content marketing", "leadagentur", "digitale kommunikationskana",
    # E-commerce
    "e-commerce", "onlineshop", "online-shop", "webshop",
    # Cloud / Hosting
    " hosting", "cloud-dienst", " saas", "saas-", "cdn-plattform", " cdn ",
    # E-learning
    "e-learning", "elearning", "lernplattform", " lms",
    # E-gov / digital platforms
    "e-government", "digitale verwaltung", "digitale plattform",
    "online-plattform",
    # BI / Analytics / Dashboards
    "business intelligence", " bi-system", "power bi", " dashboard",
    "datenvisualisierung",
    # MS enterprise
    "microsoft dynamics", "dynamics 365", "sharepoint",
    # Security (digital)
    "pentest", "websicherheit",
    # Other digital
    "corporate design", "digitales design tool", "digital design tool",
    "digitale transformation", "digital transformation",
    "digitale kommunikation",
    "ticketing-system", "ticketingsystem", "kassensystem",
    "digitalisierung der webseite", "digitalisierung der lagerlogistik",
    "computergestützte testung", "digital biodiversity learning",
    "oracle bi", "oracle erp",
]

HARD_EXCLUDE = [
    # Document scanning (not digital services)
    "digitalisierung von akten", "digitalisierung von bestands",
    "digitalisierung von dokument", "digitalisierung historischer",
    "digitalisierung der ausländer", "digitalisierung und entsorgung",
    "digitalisierung von papier", "digitalisierung von archiv",
    "digitalisierung von kku", "digitalisierung bau",
    "digitalisierung von zeitungen", "digitalisierung von zeichnung",
    "aktendigitalisierung", "digitalisierung und inputmanagement",
    # Catering / food
    "mittagsverpflegung", "schulverpflegung", "verpflegung",
    "catering", "mensaversorgung",
    # Construction / civil engineering
    "straßenbau", "strassenbau", "tiefbau", "hochbau",
    "neubau ", "anbau ", "umbau ", "erweiterungsneubau",
    "energetische sanierung", "sanierung des hochwasser",
    "sanierung feuerlösch", "sanierung klösterl",
    "dachsanierung", "dachabdichtung",
    "fliesenarbeiten", "schmutzwasserpumpwerk", "kläranlage",
    "betonsanierung", "uferwegverlegung", "rückbau rampenbau",
    "straßenendausbau", "metallbauarbeiten", "tischlerarbeiten",
    "bodenlegearbeiten", "heizungs- und sanitär",
    "kunststofffenster", "brandschutztüren", "schleuse schlüs",
    # Pharmaceuticals
    "arzneimittel", "rabattvertrag", "wirkstoff",
    "inhalationslösung", "atemwegsversorgung",
    # Vehicles / emergency equipment
    "feuerwehrfahrzeug", "löschgruppenfahrzeug", "rettungswagen",
    "krankenwagen", "fahrtrage", "beladung für ein",
    # Environment / outdoor
    "baumpflegemaßnahmen", "stubbenfräsung", "böschungspflege",
    "biomasseentsorgung", "klärschlamm", "streusalz",
    "recycling-kopierpapier",
    # Events / physical marketing
    "lichtinszenierung", "sternschnuppenmarkt", "spielgeräteprüfung",
    # Other non-digital
    "möblierung", "rf signal generator", "kontrollsysteme av signale",
]


def is_relevant(tender: dict) -> bool:
    """Return True only for genuine digital-service tenders."""
    text = (tender.get("title", "") + " " + tender.get("description", "")).lower()
    # Hard exclusions first
    if any(ex in text for ex in HARD_EXCLUDE):
        return False
    # Must match at least one digital keyword
    return any(req in text for req in DIGITAL_REQUIRE)


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

    # Only keep current tenders (open or closing) — discard anything past deadline
    final = {
        tid: t for tid, t in merged.items()
        if t.get("status") != "closed"
    }
    dropped = len(merged) - len(final)
    if dropped:
        print(f"[INFO] Dropped {dropped} expired tenders (deadline passed)")

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
