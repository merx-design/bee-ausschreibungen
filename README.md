# Ausschreibungen — merx design Vergabe-Monitor

Automatisches Monitoring von öffentlichen Ausschreibungen aus Deutschland und der Schweiz — speziell für Projekte im Bereich **Digitalisierung, Web, CRM, ERP, PIM, Marketing, Design und Apps**.

## Live-Website

**→ [merx-design.github.io/ausschreibungen](https://merx-design.github.io/ausschreibungen)**

## Quellen

| Quelle | Land | Beschreibung |
|--------|------|-------------|
| [SIMAP.ch](https://www.simap.ch) | 🇨🇭 Schweiz | Interoperabler Marktplatz für das öffentliche Beschaffungswesen |
| [DTVP.de](https://www.dtvp.de) | 🇩🇪 Deutschland | Deutsches Vergabeportal |

## Kategorien

Gefiltert wird nach folgenden Themenbereichen:

- **Website** — Webauftritt, CMS, Relaunch, Webplattform
- **CRM** — Customer Relationship Management Systeme
- **ERP** — Enterprise Resource Planning (SAP, etc.)
- **PIM** — Product Information Management
- **Marketing** — Online-Marketing, Social Media, SEO, Kampagnen
- **Design** — Corporate Design, UX/UI, Usability
- **App** — Mobile Apps (iOS/Android), Progressive Web Apps
- **Digitalisierung** — E-Government, Online-Plattformen, IT-Projekte
- **E-Commerce** — Online-Shops, B2B-Plattformen

## Automatische Aktualisierung

Die Daten werden **jeden Montag um 06:30 UTC** automatisch per GitHub Actions aktualisiert.

```
.github/workflows/crawl.yml → scripts/crawl.py → data/tenders.json
```

## Lokale Ausführung

```bash
cd scripts
pip install -r requirements.txt
python crawl.py
```

## Struktur

```
ausschreibungen/
├── .github/workflows/crawl.yml    # GitHub Actions (weekly)
├── scripts/
│   ├── crawl.py                   # Haupt-Orchestrator
│   ├── crawl_simap.py             # SIMAP.ch Scraper
│   ├── crawl_dtvp.py              # DTVP.de Scraper
│   └── requirements.txt
├── data/
│   └── tenders.json               # Aktuelle Ausschreibungen
├── index.html                     # Frontend
├── style.css
└── app.js
```

---

Made with ♥ by [merx design](https://merx-design.com)
