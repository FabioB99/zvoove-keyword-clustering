# zvoove Keyword Clustering

Liest Keywords aus Airtable, gruppiert sie semantisch in Themen-Cluster und schreibt die Ergebnisse zurück.

---

## Voraussetzungen

- Python 3.10 oder neuer ([python.org](https://www.python.org/downloads/))
- Ein Airtable Personal Access Token
- Ein Google Gemini API Key ([aistudio.google.com](https://aistudio.google.com))

---

## Setup (einmalig)

**1. Repository klonen**
```bash
git clone <repo-url>
cd zvoove-keyword-clustering
```

**2. Virtuelle Umgebung erstellen und Pakete installieren**
```bash
python -m venv .venv

# Mac/Linux:
source .venv/bin/activate

# Windows:
.venv\Scripts\activate

pip install -r requirements.txt
```

**3. Zugangsdaten eintragen**

Kopiere `.env.example` zu `.env` und fülle die Werte aus:
```bash
cp .env.example .env
```

Öffne `.env` in einem Texteditor und trage ein:
```
AIRTABLE_API_KEY=dein_airtable_token
AIRTABLE_BASE_ID=deine_base_id        # z.B. appXXXXXXXXXXXXXX
GEMINI_API_KEY=dein_gemini_api_key
```

---

## Ausführen

```bash
python main.py
```

Das Script läuft in drei Schritten durch:
1. Keywords aus Airtable laden
2. Semantisches Clustering (dauert ~5–10 Min je nach Rate Limits)
3. Ergebnisse zurück in Airtable schreiben

Die Ergebnisse landen in der Tabelle **Keyword Clusters** in deiner Airtable Base.

---

## Konfiguration

In `main.py` kannst du die Anzahl der Cluster anpassen:
```python
N_CLUSTERS = 30  # Standard: 30
```

---

## Hinweise

- Das Script speichert die Embeddings zwischen (`data/embeddings_cache.npy`). Bei einem Abbruch wird beim nächsten Start dort weitergemacht.
- Die Gemini API hat im Free Tier ein Rate Limit — das Script wartet automatisch und macht weiter.
- API Keys niemals ins Git einchecken (`.env` ist bereits in `.gitignore`).
