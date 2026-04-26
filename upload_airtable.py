import os
import json
import logging
import requests
from pyairtable import Api
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]
CLUSTERS_TABLE = "Keyword Clusters"
KEYWORDS_TABLE = "Keywords"
HEADERS = {"Authorization": f"Bearer {AIRTABLE_API_KEY}", "Content-Type": "application/json"}
META_URL = f"https://api.airtable.com/v0/meta/bases/{AIRTABLE_BASE_ID}/tables"


def get_tables() -> dict:
    resp = requests.get(META_URL, headers=HEADERS)
    resp.raise_for_status()
    return {t["name"]: t for t in resp.json()["tables"]}


def ensure_clusters_table(keywords_table_id: str) -> tuple[str, bool]:
    """Returns (clusters_table_id, just_created)."""
    tables = get_tables()
    if CLUSTERS_TABLE in tables:
        log.info("'Keyword Clusters' table already exists")
        return tables[CLUSTERS_TABLE]["id"], False

    log.info("Creating 'Keyword Clusters' table...")
    payload = {
        "name": CLUSTERS_TABLE,
        "fields": [
            {"name": "Cluster Name", "type": "singleLineText"},
            {"name": "Keyword Count", "type": "number", "options": {"precision": 0}},
            {
                "name": "Keywords",
                "type": "multipleRecordLinks",
                "options": {"linkedTableId": keywords_table_id},
            },
        ],
    }
    resp = requests.post(META_URL, headers=HEADERS, json=payload)
    resp.raise_for_status()
    table_id = resp.json()["id"]
    log.info(f"Created table id: {table_id}")
    return table_id, True


def ensure_linked_field(clusters_table_id: str, keywords_table_id: str):
    """Add 'Keywords' linked field to Keyword Clusters if missing."""
    tables = get_tables()
    clusters_fields = tables[CLUSTERS_TABLE]["fields"]
    for f in clusters_fields:
        if f["type"] == "multipleRecordLinks" and f.get("options", {}).get("linkedTableId") == keywords_table_id:
            log.info(f"Linked field '{f['name']}' already exists in Keyword Clusters")
            return

    log.info("Adding linked field 'Keywords' to Keyword Clusters...")
    url = f"{META_URL}/{clusters_table_id}/fields"
    payload = {
        "name": "Keywords",
        "type": "multipleRecordLinks",
        "options": {"linkedTableId": keywords_table_id},
    }
    resp = requests.post(url, headers=HEADERS, json=payload)
    resp.raise_for_status()
    log.info("Linked field added")


def get_reciprocal_field_name(clusters_table_id: str) -> str:
    """Find the auto-created reciprocal linked field in Keywords pointing to Keyword Clusters."""
    tables = get_tables()
    for field in tables[KEYWORDS_TABLE]["fields"]:
        if (
            field["type"] == "multipleRecordLinks"
            and field.get("options", {}).get("linkedTableId") == clusters_table_id
        ):
            log.info(f"Reciprocal field in Keywords: '{field['name']}'")
            return field["name"]
    raise RuntimeError("Reciprocal linked field not found in Keywords — check Airtable token scopes (needs schema.bases:write)")


def upload_clusters(clusters_file: str):
    with open(clusters_file, encoding="utf-8") as f:
        clusters = json.load(f)

    tables = get_tables()
    keywords_table_id = tables[KEYWORDS_TABLE]["id"]

    clusters_table_id, just_created = ensure_clusters_table(keywords_table_id)
    if not just_created:
        ensure_linked_field(clusters_table_id, keywords_table_id)

    linked_field_name = get_reciprocal_field_name(clusters_table_id)

    api = Api(AIRTABLE_API_KEY)
    clusters_table = api.table(AIRTABLE_BASE_ID, clusters_table_id)
    keywords_table = api.table(AIRTABLE_BASE_ID, KEYWORDS_TABLE)

    # Clear existing cluster records
    existing = clusters_table.all()
    if existing:
        log.info(f"Clearing {len(existing)} existing cluster records...")
        clusters_table.batch_delete([r["id"] for r in existing])

    for cluster in clusters:
        log.info(f"Uploading: {cluster['cluster_name']} ({cluster['keyword_count']} keywords)")

        cluster_record = clusters_table.create({
            "Cluster Name": cluster["cluster_name"],
            "Keyword Count": cluster["keyword_count"],
        })
        cluster_record_id = cluster_record["id"]

        kw_ids = [kw["id"] for kw in cluster["keywords"]]
        updates = [
            {"id": kw_id, "fields": {linked_field_name: [cluster_record_id]}}
            for kw_id in kw_ids
        ]
        keywords_table.batch_update(updates)
        log.info(f"  Linked {len(kw_ids)} keywords")

    log.info("Upload complete.")


if __name__ == "__main__":
    import sys
    clusters_file = sys.argv[1] if len(sys.argv) > 1 else "data/clusters_output.json"
    upload_clusters(clusters_file)
