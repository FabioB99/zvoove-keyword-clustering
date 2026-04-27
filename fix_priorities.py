"""Updates Priorität for all Content Briefs based on total search volume — no Gemini needed."""
import os
import logging
from pyairtable import Api
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]


def prioritaet(total_sv: int) -> str:
    if total_sv > 20000:
        return "Hoch"
    elif total_sv >= 3000:
        return "Mittel"
    return "Niedrig"


def main():
    api = Api(AIRTABLE_API_KEY)
    keywords_table = api.table(AIRTABLE_BASE_ID, "Keywords")
    clusters_table = api.table(AIRTABLE_BASE_ID, "Keyword Clusters")
    briefs_table = api.table(AIRTABLE_BASE_ID, "Content Briefs")

    log.info("Fetching keywords...")
    kw_by_id = {r["id"]: r["fields"] for r in keywords_table.all()}

    log.info("Fetching clusters...")
    cluster_sv = {}
    for r in clusters_table.all():
        total_sv = sum(kw_by_id.get(kid, {}).get("Search Volume") or 0 for kid in r["fields"].get("Keywords", []))
        cluster_sv[r["fields"].get("Cluster Name", "")] = total_sv

    log.info("Fetching briefs...")
    briefs = briefs_table.all()
    log.info(f"Updating {len(briefs)} briefs...")

    for r in briefs:
        name = r["fields"].get("Brief Name", "")
        sv = cluster_sv.get(name, 0)
        prio = prioritaet(sv)
        briefs_table.update(r["id"], {"Priorität": prio})
        log.info(f"{name}: SV {sv:,} → {prio}")

    log.info("Done.")


if __name__ == "__main__":
    main()
