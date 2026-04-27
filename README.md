# zvoove Keyword Clustering & Content Brief Pipeline

Automated pipeline: reads keywords from Airtable, groups them into thematic clusters, and generates SEO content briefs.

**Note:** This repository contains only the Python clustering & brief generation scripts. The n8n workflows for scraping, keyword extraction, and SEO data enrichment are included in `/n8n-workflows/` for reference but are documented separately.


## Prerequisites

- Python 3.10+
- Airtable Personal Access Token (with read & write access to the base)
- Google Gemini API Key ([aistudio.google.com](https://aistudio.google.com))
- DataForSEO account (only for step 3)

**Airtable base must contain:**
- Table `Blogposts` (populated by n8n)
- Table `Keywords` with fields: `Keyword`, `Search Volume`, `KW Difficulty`, `Search Intent`, `Keyword Category`
- Table `Content Briefs` (created by `brief_generation.py`)
- Table `Keyword Clusters` (created by `main.py`)


## Setup

```bash
# 1. Virtual environment
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Install packages
pip install -r requirements.txt

# 3. Credentials
cp .env.example .env
# Open .env and fill in the values
```


## Running

**Prerequisites:** Keywords must already exist in Airtable (via n8n workflows or manual import). Each Python step depends on the previous one:

### Step 1: Clustering
```bash
python main.py
```
Reads keywords from Airtable, computes embeddings, clusters them, and writes the clusters back to Airtable.

### Step 2: Generate content briefs
```bash
python brief_generation.py
```
Requires step 1. Generates or updates content briefs. The script is idempotent.

### Step 3: Add benchmark URLs
```bash
python add_benchmark_urls.py
```
Requires step 2. Queries DataForSEO for top 3 URLs per cluster's top 3 keywords.

## Configuration

In `main.py`:
```python
N_CLUSTERS = 30  # adjust number of clusters
```

In `brief_generation.py`:
```python
GEMINI_MODEL = "models/gemini-2.5-flash"
```
Priority thresholds in `compute_stats()`:
* 20,000 → High
* 3,000–20,000 → Medium
* < 3,000 → Low


## Rate limits

Gemini 2.5 Flash Free Tier: **5 RPM**. The script automatically waits 12s between requests and retries on 429/503.


## Project structure

```
├── main.py                  # Step 1: Clustering pipeline
├── cluster.py               # Keyword clustering via embeddings
├── extract_airtable.py      # Load keywords from Airtable
├── upload_airtable.py       # Write cluster results to Airtable
├── brief_generation.py      # Step 2: Generate & upload content briefs
├── add_benchmark_urls.py    # Step 3: Benchmark URLs via DataForSEO
├── fix_priorities.py        # Update priorities without Gemini
├── data/
│   ├── keywords_full.json   # 536 keywords (raw data)
│   └── clusters_output.json # 30 clusters (clustering output)
├── content-briefs/          # 30 generated content briefs (.md)
├── requirements.txt
└── .env.example
```
