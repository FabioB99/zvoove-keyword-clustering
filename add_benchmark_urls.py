import os
import time
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv
from pyairtable import Api

load_dotenv()

AIRTABLE_TOKEN = os.environ["AIRTABLE_API_KEY"]
DATAFORSEO_LOGIN = os.environ["DATAFORSEO_LOGIN"]
DATAFORSEO_PASSWORD = os.environ["DATAFORSEO_PASSWORD"]

# --- Config ---
BASE_ID = "appCgjGR9rFvho1pa"
BRIEFS_TABLE_ID = "tbls4s6xkN1rfTYjF"
KEYWORDS_TABLE_ID = "tblypfYJctBQT5CpU"
DATAFORSEO_URL = "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"

TEST_MODE = False   # True = nur 3 Cluster, dann auf False setzen
TEST_LIMIT = 3


def get_top_keywords(keywords_data: list[dict], n: int = 3) -> list[tuple[str, int]]:
    """Returns top n (keyword_text, search_volume) tuples sorted by SV descending."""
    results = []
    for kw in keywords_data:
        fields = kw.get("fields", {})
        sv = fields.get("Search Volume")
        text = fields.get("Keyword")
        if text and sv is not None:
            results.append((text, sv))
    results.sort(key=lambda x: x[1], reverse=True)
    return results[:n]


def fetch_serp_urls(keyword: str) -> list[str]:
    """Returns up to 3 organic URLs from DataForSEO SERP."""
    payload = [{"location_code": 2276, "language_code": "de", "keyword": keyword}]
    for attempt in range(3):
        try:
            resp = requests.post(
                DATAFORSEO_URL,
                auth=HTTPBasicAuth(DATAFORSEO_LOGIN, DATAFORSEO_PASSWORD),
                json=payload,
                timeout=30,
            )
            if resp.status_code == 429:
                print("  Rate limit hit, waiting 60s...")
                time.sleep(60)
                continue
            resp.raise_for_status()
            data = resp.json()
            items = data["tasks"][0]["result"][0]["items"]
            urls = [
                item["url"]
                for item in items
                if item.get("type") == "organic" and item.get("url")
            ]
            return urls[:3]
        except Exception as e:
            print(f"  DataForSEO error (attempt {attempt + 1}): {e}")
            if attempt < 2:
                time.sleep(5)
    return []


def main():
    api = Api(AIRTABLE_TOKEN)
    briefs_table = api.table(BASE_ID, BRIEFS_TABLE_ID)
    keywords_table = api.table(BASE_ID, KEYWORDS_TABLE_ID)

    print("Loading all keywords...")
    all_keywords = keywords_table.all()

    # Build reverse index: cluster_record_id -> list of keyword records
    # (Keywords link to a "Clusters" table; Content Briefs also link to that table via "Cluster")
    keywords_by_cluster: dict[str, list[dict]] = {}
    for kw in all_keywords:
        for cid in kw.get("fields", {}).get("Keyword Clusters", []):
            keywords_by_cluster.setdefault(cid, []).append(kw)
    print(f"  {len(all_keywords)} keywords loaded.")

    print("Loading content briefs...")
    briefs = briefs_table.all()
    print(f"  {len(briefs)} briefs loaded.")

    if TEST_MODE:
        briefs = briefs[:TEST_LIMIT]
        print(f"  TEST MODE: processing first {TEST_LIMIT} briefs only.\n")

    updated = 0
    total = len(briefs)

    for brief in briefs:
        brief_id = brief["id"]
        fields = brief.get("fields", {})
        name = fields.get("Brief Name", brief_id)
        cluster_ids = fields.get("Cluster", [])
        linked_kw_ids = []
        for cid in cluster_ids:
            linked_kw_ids.extend(keywords_by_cluster.get(cid, []))

        if not linked_kw_ids:
            print(f"Cluster: {name} | No keywords found — skipped")
            continue

        top_keywords = get_top_keywords(linked_kw_ids, n=3)

        if not top_keywords:
            print(f"Cluster: {name} | No keywords with Search Volume — skipped")
            continue

        sections = []
        for kw_text, kw_sv in top_keywords:
            urls = fetch_serp_urls(kw_text)
            if urls:
                numbered = "\n".join(f"{i+1}. {url}" for i, url in enumerate(urls))
            else:
                numbered = "Keine Rankings gefunden"
            sections.append(f"Keyword: {kw_text}\n{numbered}")

        benchmark_text = "\n\n".join(sections)

        try:
            briefs_table.update(brief_id, {"Benchmark URLs": benchmark_text})
            updated += 1
            kw_names = ", ".join(f"{kw} (SV: {sv})" for kw, sv in top_keywords)
            print(f"Cluster: {name} | Keywords: {kw_names} | done")
        except Exception as e:
            print(f"Cluster: {name} | Airtable update failed: {e}")

    print(f"\n{updated}/{total} Clusters updated.")
    if TEST_MODE:
        print("Fertig mit Test. Setze TEST_MODE = False für alle 30.")


if __name__ == "__main__":
    main()
