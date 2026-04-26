import os
import json
import logging
import time
import requests
import numpy as np
from sklearn.cluster import KMeans
from sklearn.preprocessing import normalize
from google import genai
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

GEMINI_API_KEY = os.environ["GEMINI_API_KEY"]
EMBEDDING_MODEL = "gemini-embedding-2"
LABEL_MODEL = "models/gemini-3.1-flash-lite-preview"
N_CLUSTERS = 8
TOP_KEYWORDS_FOR_LABEL = 10
BATCH_SIZE = 20
BATCH_SLEEP = 4   # 15 batches/min, under 100 req/min embedding limit
LABEL_SLEEP = 5   # 12 labels/min, under 15 req/min label limit

client = genai.Client(api_key=GEMINI_API_KEY)


def embed_batch_rest(keywords: list[str]) -> list:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{EMBEDDING_MODEL}:batchEmbedContents"
    payload = {
        "requests": [
            {"model": f"models/{EMBEDDING_MODEL}", "content": {"parts": [{"text": kw}]}}
            for kw in keywords
        ]
    }
    while True:
        resp = requests.post(url, json=payload, params={"key": GEMINI_API_KEY})
        if resp.status_code == 429:
            log.warning("Embedding rate limit — waiting 60s...")
            time.sleep(60)
            continue
        resp.raise_for_status()
        return [e["values"] for e in resp.json()["embeddings"]]


def get_embeddings(keywords: list[str], cache_path: str = "data/embeddings_cache.npy") -> np.ndarray:
    if os.path.exists(cache_path):
        cached = np.load(cache_path)
        if len(cached) == len(keywords):
            log.info(f"Loading embeddings from cache: {cache_path}")
            return cached
        log.info(f"Partial cache found ({len(cached)}/{len(keywords)}) — resuming from there...")
        embeddings = cached.tolist()
        start_i = (len(cached) // BATCH_SIZE) * BATCH_SIZE
    else:
        embeddings = []
        start_i = 0

    log.info(f"Generating embeddings for {len(keywords)} keywords in batches of {BATCH_SIZE}...")
    for i in range(start_i, len(keywords), BATCH_SIZE):
        batch = keywords[i:i + BATCH_SIZE]
        embeddings.extend(embed_batch_rest(batch))
        done = min(i + BATCH_SIZE, len(keywords))
        log.info(f"  {done}/{len(keywords)} done")
        np.save(cache_path, np.array(embeddings))
        time.sleep(BATCH_SLEEP)

    arr = np.array(embeddings)
    log.info(f"Embeddings cached to {cache_path}")
    return arr



def cluster_keywords(embeddings: np.ndarray, n_clusters: int) -> np.ndarray:
    log.info(f"Clustering into {n_clusters} clusters...")
    vectors = normalize(embeddings)
    km = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
    return km.fit_predict(vectors)


def generate_label(keywords_in_cluster: list[str]) -> str:
    sample = keywords_in_cluster[:TOP_KEYWORDS_FOR_LABEL]
    prompt = (
        "Du bist ein SEO-Experte für B2B SaaS im deutschsprachigen Raum.\n"
        "Erstelle einen prägnanten deutschen Cluster-Namen (2-4 Wörter) für diese Keywords:\n"
        + "\n".join(f"- {kw}" for kw in sample)
        + "\n\nNur den Namen, keine Erklärung."
    )
    while True:
        try:
            response = client.models.generate_content(model=LABEL_MODEL, contents=prompt)
            return response.text.strip()
        except Exception as e:
            if "429" in str(e):
                log.warning("Label rate limit — waiting 60s...")
                time.sleep(60)
            else:
                raise


def run_clustering(input_file: str, n_clusters: int = N_CLUSTERS) -> list[dict]:
    with open(input_file, encoding="utf-8") as f:
        keywords = json.load(f)

    kw_texts = [k["keyword"] for k in keywords]
    embeddings = get_embeddings(kw_texts)
    labels = cluster_keywords(embeddings, n_clusters)

    clusters: dict[int, list[dict]] = {}
    for kw, label in zip(keywords, labels):
        clusters.setdefault(int(label), []).append(kw)

    results = []
    for cluster_id, members in sorted(clusters.items()):
        log.info(f"Generating label for cluster {cluster_id} ({len(members)} keywords)...")
        name = generate_label([m["keyword"] for m in members])
        volumes = [m["search_volume"] for m in members if m.get("search_volume")]
        avg_sv = round(sum(volumes) / len(volumes)) if volumes else 0
        results.append({
            "cluster_id": cluster_id,
            "cluster_name": name,
            "keywords": members,
            "keyword_count": len(members),
            "avg_search_volume": avg_sv,
        })
        log.info(f"  → {name}")
        time.sleep(LABEL_SLEEP)

    return results


if __name__ == "__main__":
    import sys
    input_file = sys.argv[1] if len(sys.argv) > 1 else "data/keywords_test.json"
    n_clusters = int(sys.argv[2]) if len(sys.argv) > 2 else N_CLUSTERS

    results = run_clustering(input_file, n_clusters)

    out_path = "data/clusters_output.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    log.info(f"Saved to {out_path}")

    print("\n=== CLUSTER RESULTS ===")
    for c in results:
        print(f"\n[{c['cluster_name']}] ({c['keyword_count']} Keywords)")
        for kw in c["keywords"]:
            print(f"  - {kw['keyword']}")
