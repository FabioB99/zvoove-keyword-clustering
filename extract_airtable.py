import os
import json
import logging
from pyairtable import Api
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

AIRTABLE_API_KEY = os.environ["AIRTABLE_API_KEY"]
AIRTABLE_BASE_ID = os.environ["AIRTABLE_BASE_ID"]
TABLE_NAME = "Keywords"


def fetch_keywords() -> list[dict]:
    api = Api(AIRTABLE_API_KEY)
    table = api.table(AIRTABLE_BASE_ID, TABLE_NAME)

    log.info("Fetching keywords from Airtable...")
    records = table.all()
    log.info(f"Fetched {len(records)} records")

    keywords = []
    for r in records:
        f = r["fields"]
        if not f.get("Keyword"):
            continue
        keywords.append({
            "id": r["id"],
            "keyword": f["Keyword"],
            "search_volume": f.get("Search Volume"),
            "keyword_difficulty": f.get("KW Difficulty"),
            "keyword_category": f.get("Keyword Category"),
            "search_intent": f.get("Search Intent"),
            "blog_url": f.get("Blog URL (from Blogposts)", [None])[0],
        })

    log.info(f"Valid keywords: {len(keywords)}")
    return keywords


if __name__ == "__main__":
    keywords = fetch_keywords()
    out_path = "data/keywords_full.json"
    os.makedirs("data", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(keywords, f, ensure_ascii=False, indent=2)
    log.info(f"Saved to {out_path}")

    # Preview
    for kw in keywords[:5]:
        print(kw)
