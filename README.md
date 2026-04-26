# zvoove Keyword Clustering

Semantic clustering of ~500 B2B SaaS keywords from the zvoove blog using embeddings + KMeans.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # fill in credentials
```

## Usage

```bash
python main.py
```

## Config

Edit `config.py` to adjust cluster count, embedding model, and output options.
