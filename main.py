import os
import json
import logging
import sys
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

N_CLUSTERS = 30  # adjust if needed


def check_env():
    missing = [k for k in ["AIRTABLE_API_KEY", "AIRTABLE_BASE_ID", "GEMINI_API_KEY"] if not os.environ.get(k)]
    if missing:
        print(f"ERROR: Missing environment variables: {', '.join(missing)}")
        print("Please fill in your .env file (copy from .env.example)")
        sys.exit(1)


def main():
    check_env()

    os.makedirs("data", exist_ok=True)

    # Step 1: Extract keywords from Airtable
    log.info("=== STEP 1: Extracting keywords from Airtable ===")
    from extract_airtable import fetch_keywords
    keywords = fetch_keywords()
    with open("data/keywords_full.json", "w", encoding="utf-8") as f:
        json.dump(keywords, f, ensure_ascii=False, indent=2)
    log.info(f"Extracted {len(keywords)} keywords")

    # Step 2: Cluster keywords
    log.info(f"=== STEP 2: Clustering into {N_CLUSTERS} clusters ===")
    from cluster import run_clustering
    results = run_clustering("data/keywords_full.json", N_CLUSTERS)
    with open("data/clusters_output.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log.info(f"Created {len(results)} clusters")

    # Step 3: Upload to Airtable
    log.info("=== STEP 3: Uploading to Airtable ===")
    from upload_airtable import upload_clusters
    upload_clusters("data/clusters_output.json")

    log.info("=== DONE ===")
    print("\nAll done! Check your Airtable base for the 'Keyword Clusters' table.")


if __name__ == "__main__":
    main()
