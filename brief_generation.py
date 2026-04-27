import os
import json
import logging
import re
import time
import requests
from pathlib import Path
from pyairtable import Api
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]
GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
GEMINI_MODEL = "models/gemini-2.5-flash"

HEADERS = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
META_URL = f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}/tables"

BRIEFS_DIR = Path("content-briefs")
BRIEFS_TABLE = "Content Briefs"


# ── Step 1: Read clusters + keywords from Airtable ───────────────────────────

def fetch_clusters() -> list[dict]:
    api = Api(AIRTABLE_API_KEY)
    clusters_table = api.table(AIRTABLE_BASE_ID, "Keyword Clusters")
    keywords_table = api.table(AIRTABLE_BASE_ID, "Keywords")

    log.info("Fetching keyword index...")
    kw_records = keywords_table.all()
    kw_by_id = {r["id"]: r["fields"] for r in kw_records}

    log.info("Fetching clusters...")
    cluster_records = clusters_table.all()
    log.info(f"Found {len(cluster_records)} clusters")

    clusters = []
    for r in cluster_records:
        f = r["fields"]
        linked_ids = f.get("Keywords", [])
        keywords = []
        for kid in linked_ids:
            kw = kw_by_id.get(kid, {})
            if kw.get("Keyword"):
                keywords.append({
                    "keyword": kw["Keyword"],
                    "search_volume": kw.get("Search Volume") or 0,
                    "kw_difficulty": kw.get("KW Difficulty") or None,
                    "search_intent": kw.get("Search Intent", ""),
                    "keyword_category": kw.get("Keyword Category", ""),
                })
        clusters.append({
            "airtable_id": r["id"],
            "cluster_name": f.get("Cluster Name", ""),
            "keyword_count": f.get("Keyword Count", len(keywords)),
            "keywords": keywords,
        })

    return clusters


# ── Step 2: Python calculates all stats ──────────────────────────────────────

def compute_stats(cluster: dict) -> dict:
    kws = cluster["keywords"]

    total_sv = sum(k["search_volume"] for k in kws)

    kws_with_kd = [k for k in kws if k["kw_difficulty"] is not None]
    avg_kd = round(sum(k["kw_difficulty"] for k in kws_with_kd) / len(kws_with_kd)) if kws_with_kd else None

    intent_counts: dict[str, int] = {}
    for k in kws:
        intent = k["search_intent"] or "unbekannt"
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
    total = len(kws)
    intent_breakdown = ", ".join(
        f"{intent} ({round(count/total*100)}%)"
        for intent, count in sorted(intent_counts.items(), key=lambda x: -x[1])
    )

    top10 = sorted(kws, key=lambda k: k["search_volume"], reverse=True)[:10]

    if total_sv > 20000:
        prioritaet = "Hoch"
    elif total_sv >= 3000:
        prioritaet = "Mittel"
    else:
        prioritaet = "Niedrig"

    return {
        "total_sv": total_sv,
        "avg_kd": avg_kd,
        "avg_kd_str": f"{avg_kd}/100" if avg_kd is not None else "nicht verfügbar",
        "intent_breakdown": intent_breakdown,
        "top10": top10,
        "all_keywords": kws,
        "prioritaet": prioritaet,
    }


def format_top10_table(top10: list) -> str:
    return "\n".join(
        f"**{k['keyword']}** — SV: {k['search_volume']} | KD: {k['kw_difficulty'] if k['kw_difficulty'] is not None else '-'} | Intent: {k['search_intent'] or '-'}"
        for k in top10
    )


# ── Step 3: Gemini generates only text fields ─────────────────────────────────

GEMINI_PROMPT_TEMPLATE = """Du bist ein erfahrener Content-Stratege und SEO-Experte für B2B SaaS im DACH-Raum.
zvoove bietet Software für Personaldienstleister und Facility-Services-Unternehmen an.

Analysiere folgenden Keyword-Cluster und liefere ausschliesslich ein JSON-Objekt zurück — kein Markdown, keine Erklärung.

**Cluster:** {cluster_name}
**Gesamtes Search Volume:** {total_sv}/Monat
**Ø Keyword Difficulty:** {avg_kd}
**Search Intent:** {intent_breakdown}
**Keywords ({keyword_count} total):**
{all_keywords}

**Kriterien für "content_typ"** — wähle den SPEZIFISCHSTEN passenden Typ, nicht automatisch "Guide":
- "How-To": Thema dreht sich um einen konkreten Prozess, Schritt-für-Schritt-Anleitung, oder operative Umsetzung (Lohnabrechnung durchführen, Meldeprozesse abwickeln, Stellen ausschreiben)
- "Vergleich": Keywords enthalten "vs", "Unterschied", "Alternative", "besser", "Vergleich", oder das Thema ist Outsourcing vs. Inhouse, Software A vs. B
- "Übersicht": Gesetzliche Regelungen, Compliance-Anforderungen, Tarifwerke, Listen von Tools/Anbietern/Optionen — wenn es primär um "was gibt es / was gilt" geht
- "Guide": Nur wenn das Thema wirklich strategisch-umfassend ist und keiner der drei anderen Typen besser passt

Antworte mit diesem JSON (alle Felder auf Deutsch):
{{
  "thematischer_fokus": "1 prägnanter Satz was dieses Thema abdeckt",
  "content_luecke": "Was fehlt typischerweise in B2B SaaS Blogs zu diesem Thema?",
  "zielgruppe": "Konkrete Beschreibung: Rolle, Branche, Pain Points",
  "schwerpunkte": ["Schwerpunkt 1 mit 2-3 Sätzen Beschreibung was konkret behandelt wird", "Schwerpunkt 2", "Schwerpunkt 3"],
  "h1": "Konkreter SEO-optimierter Arbeitstitel",
  "h2s": ["H2 Subthema 1", "H2 Subthema 2", "H2 Subthema 3", "H2 Subthema 4"],
  "content_typ": "Guide" oder "How-To" oder "Vergleich" oder "Übersicht",
  "content_laenge": 1500,
  "content_laenge_begruendung": "1 Satz Begründung"
}}"""


def call_gemini(prompt: str) -> dict:
    url = f"https://generativelanguage.googleapis.com/v1beta/{GEMINI_MODEL}:generateContent"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}

    while True:
        resp = requests.post(url, json=payload, params={"key": GEMINI_API_KEY}, timeout=60)
        if resp.status_code == 429:
            log.warning("Rate limit — waiting 90s...")
            time.sleep(90)
            continue
        if resp.status_code == 503:
            log.warning("Service unavailable — waiting 30s...")
            time.sleep(30)
            continue
        resp.raise_for_status()
        text = resp.json()["candidates"][0]["content"]["parts"][0]["text"]
        text = re.sub(r"^```json\s*|\s*```$", "", text.strip())
        data = json.loads(text)
        break

    for key in ["zielgruppe", "thematischer_fokus", "content_luecke"]:
        if key in data and not isinstance(data[key], str):
            data[key] = ", ".join(str(v) for v in data[key].values()) if isinstance(data[key], dict) else str(data[key])
    return data


def get_text_fields(cluster: dict, stats: dict) -> dict:
    all_kws = "\n".join(f"- {k['keyword']}" for k in cluster["keywords"])
    prompt = GEMINI_PROMPT_TEMPLATE.format(
        cluster_name=cluster["cluster_name"],
        keyword_count=cluster["keyword_count"],
        all_keywords=all_kws,
        total_sv=f"{stats['total_sv']:,}",
        avg_kd=stats["avg_kd_str"],
        intent_breakdown=stats["intent_breakdown"],
    )
    return call_gemini(prompt)


# ── Step 4: Python assembles the final brief ──────────────────────────────────

def build_brief(cluster: dict, stats: dict, text: dict) -> str:
    top10_table = format_top10_table(stats["top10"])
    schwerpunkte = "\n".join(f"{i+1}. {s}" for i, s in enumerate(text["schwerpunkte"]))
    h2s = "\n".join(f"- {h}" for h in text["h2s"])

    return f"""# Content Brief: {cluster['cluster_name']}

## Strategic Overview
- **Thematischer Fokus:** {text['thematischer_fokus']}
- **Content-Lücke:** {text['content_luecke']}
- **Priorität:** {stats['prioritaet']}

## Keyword-Analyse
- **Anzahl Keywords:** {cluster['keyword_count']}
- **Gesamtes Search Volume:** {stats['total_sv']:,}/Monat
- **Ø Keyword Difficulty:** {stats['avg_kd_str']}
- **Search Intent:** {stats['intent_breakdown']}

### Top 10 Keywords
{top10_table}

## Zielgruppe
{text['zielgruppe']}

## Empfohlene Content-Richtung

### Thematische Schwerpunkte
{schwerpunkte}

### Vorgeschlagene Struktur
**H1:** {text['h1']}

**H2-Empfehlungen:**
{h2s}

**Content-Typ:** {text['content_typ']}

### Geschätzte Content-Länge
~{text['content_laenge']:,} Wörter — {text['content_laenge_begruendung']}
"""


# ── Step 5: Save Markdown ─────────────────────────────────────────────────────

def slugify(text: str) -> str:
    text = text.lower().replace(" ", "-").replace("&", "und")
    return re.sub(r"[^a-z0-9\-]", "", text)[:60]


def save_markdown(cluster: dict, content: str) -> Path:
    BRIEFS_DIR.mkdir(exist_ok=True)
    path = BRIEFS_DIR / f"{slugify(cluster['cluster_name'])}.md"
    path.write_text(content, encoding="utf-8")
    log.info(f"Saved: {path}")
    return path


# ── Step 6: Upload / Update Airtable ─────────────────────────────────────────

def ensure_briefs_table() -> str:
    resp = requests.get(META_URL, headers=HEADERS)
    resp.raise_for_status()
    tables = {t["name"]: t for t in resp.json()["tables"]}

    if BRIEFS_TABLE in tables:
        log.info("'Content Briefs' table already exists")
        return tables[BRIEFS_TABLE]["id"]

    log.info("Creating 'Content Briefs' table...")
    payload = {
        "name": BRIEFS_TABLE,
        "fields": [
            {"name": "Brief Name", "type": "singleLineText"},
            {"name": "Cluster", "type": "multipleRecordLinks",
             "options": {"linkedTableId": tables["Keyword Clusters"]["id"]}},
            {"name": "Full Content Brief", "type": "richText"},
            {"name": "Priorität", "type": "singleSelect",
             "options": {"choices": [{"name": "Hoch"}, {"name": "Mittel"}, {"name": "Niedrig"}]}},
            {"name": "Content-Typ", "type": "singleSelect",
             "options": {"choices": [{"name": "Guide"}, {"name": "How-To"}, {"name": "Vergleich"}, {"name": "Übersicht"}]}},
            {"name": "Thematischer Fokus", "type": "multilineText"},
            {"name": "Search Volume", "type": "number", "options": {"precision": 0}},
            {"name": "Zielgruppe", "type": "multilineText"},
            {"name": "Content-Lücke", "type": "multilineText"},
            {"name": "Status", "type": "singleSelect",
             "options": {"choices": [{"name": "Draft"}, {"name": "Review"}, {"name": "Approved"}]}},
        ],
    }
    resp = requests.post(META_URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    return resp.json()["id"]


def get_existing_briefs(table_id: str) -> dict:
    """Returns {cluster_name: record_id} for all existing briefs."""
    api = Api(AIRTABLE_API_KEY)
    table = api.table(AIRTABLE_BASE_ID, table_id)
    return {r["fields"].get("Brief Name"): r["id"] for r in table.all() if r["fields"].get("Brief Name")}


def _brief_fields(cluster: dict, stats: dict, text: dict, content: str) -> dict:
    return {
        "Full Content Brief": content,
        "Priorität": stats["prioritaet"],
        "Content-Typ": text["content_typ"],
        "Thematischer Fokus": text["thematischer_fokus"],
        "Search Volume": stats["total_sv"],
        "Zielgruppe": text["zielgruppe"],
        "Content-Lücke": text["content_luecke"],
    }


def upload_brief(table_id: str, cluster: dict, stats: dict, text: dict, content: str):
    api = Api(AIRTABLE_API_KEY)
    table = api.table(AIRTABLE_BASE_ID, table_id)
    fields = _brief_fields(cluster, stats, text, content)
    fields["Brief Name"] = cluster["cluster_name"]
    fields["Cluster"] = [cluster["airtable_id"]]
    fields["Status"] = "Draft"
    table.create(fields)
    log.info(f"Created: {cluster['cluster_name']} [{stats['prioritaet']}] [{text['content_typ']}]")


def update_brief(table_id: str, record_id: str, cluster: dict, stats: dict, text: dict, content: str):
    api = Api(AIRTABLE_API_KEY)
    table = api.table(AIRTABLE_BASE_ID, table_id)
    table.update(record_id, _brief_fields(cluster, stats, text, content))
    log.info(f"Updated: {cluster['cluster_name']} [{stats['prioritaet']}] [{text['content_typ']}]")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    clusters = fetch_clusters()
    briefs_table_id = ensure_briefs_table()
    existing = get_existing_briefs(briefs_table_id)
    log.info(f"{len(existing)} existing briefs will be updated, {len(clusters) - len(existing)} will be created")

    for i, cluster in enumerate(clusters):
        log.info(f"[{i+1}/{len(clusters)}] {cluster['cluster_name']}")
        try:
            stats = compute_stats(cluster)
            text = get_text_fields(cluster, stats)
            content = build_brief(cluster, stats, text)
            save_markdown(cluster, content)
            if cluster["cluster_name"] in existing:
                update_brief(briefs_table_id, existing[cluster["cluster_name"]], cluster, stats, text, content)
            else:
                upload_brief(briefs_table_id, cluster, stats, text, content)
        except Exception as e:
            log.error(f"Failed: {cluster['cluster_name']} — {e}")
            continue
        time.sleep(12)  # 5 RPM = 1 req/12s

    log.info("All briefs generated.")


if __name__ == "__main__":
    main()
