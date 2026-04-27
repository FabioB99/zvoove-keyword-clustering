# zvoove Keyword Clustering & Content Brief Pipeline

Automatisierte Pipeline: liest Keywords aus Airtable, gruppiert sie in thematische Cluster und generiert daraus SEO Content Briefs.

---

## Was die Pipeline macht

```
Airtable Keywords
      │
      ▼
1. Clustering (cluster.py)
   - Embeddings via Gemini
   - K-Means Clustering (30 Cluster)
   - Ergebnis: data/clusters_output.json
      │
      ▼
2. Content Briefs (brief_generation.py)
   - Stats berechnen (SV, KD, Intent) → Python
   - Priorität bestimmen (SV-Schwellenwerte) → Python
   - Content-Typ + Briefing-Texte → Gemini 2.5 Flash
   - Markdown speichern → content-briefs/
   - Hochladen → Airtable "Content Briefs" Tabelle
```

---

## Rohdaten & Transparenz

Die Rohdaten (`data/`) und generierten Briefs (`content-briefs/`) sind im Repository enthalten.

**Priorität-Logik (transparent & nachvollziehbar):**
- **Hoch**: Gesamtes Search Volume > 20.000/Monat
- **Mittel**: Search Volume 3.000–20.000/Monat
- **Niedrig**: Search Volume < 3.000/Monat

**Content-Typ-Logik (Gemini):**
- *How-To*: Prozessorientierte Themen (Lohnabrechnung, Meldeprozesse, etc.)
- *Vergleich*: Themen mit Alternativen / Outsourcing vs. Inhouse
- *Übersicht*: Gesetzliche Regelungen, Compliance, Tarifwerke
- *Guide*: Strategisch-umfassende Themen

---

## Voraussetzungen

- Python 3.10+
- Airtable Personal Access Token (mit Lese- & Schreibrechten auf die Base)
- Google Gemini API Key ([aistudio.google.com](https://aistudio.google.com))

**Airtable Base muss enthalten:**
- Tabelle `Keywords` mit Feldern: `Keyword`, `Search Volume`, `KW Difficulty`, `Search Intent`, `Keyword Category`
- Tabelle `Keyword Clusters` (wird von `main.py` befüllt)

---

## Setup

```bash
# 1. Virtuelle Umgebung
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate

# 2. Pakete installieren
pip install -r requirements.txt

# 3. Zugangsdaten
cp .env.example .env
# .env öffnen und Werte eintragen
```

---

## Ausführen

Die beiden Schritte sind unabhängig voneinander und können separat gestartet werden.

### Schritt 1: Clustering
```bash
python main.py
```
Liest Keywords aus Airtable, berechnet Embeddings, clustert und schreibt die Cluster zurück in Airtable. Ergebnis wird in `data/` gespeichert.

### Schritt 2: Content Briefs generieren / aktualisieren
```bash
python brief_generation.py
```
Setzt voraus dass Schritt 1 bereits gelaufen ist. Das Script ist idempotent — bestehende Briefs werden aktualisiert, neue erstellt. Einmal laufen lassen reicht.

### Nur Prioritäten aktualisieren (ohne Gemini)
```bash
python fix_priorities.py
```

---

## Konfiguration

In `main.py`:
```python
N_CLUSTERS = 30  # Anzahl Cluster anpassen
```

In `brief_generation.py`:
```python
GEMINI_MODEL = "models/gemini-2.5-flash"

# Priorität-Schwellenwerte in compute_stats():
# > 20.000 → Hoch | 3.000–20.000 → Mittel | < 3.000 → Niedrig
```

---

## Rate Limits

Gemini 2.5 Flash Free Tier: **5 RPM**. Das Script wartet automatisch 12s zwischen Requests und retried bei 429/503. Bei ~30 Clustern: ca. 10–15 Minuten Laufzeit.

---

## Projektstruktur

```
├── main.py                  # Komplette Pipeline (Schritt 1+2)
├── cluster.py               # Keyword Clustering via Embeddings
├── extract_airtable.py      # Keywords aus Airtable laden
├── upload_airtable.py       # Cluster-Ergebnisse in Airtable schreiben
├── brief_generation.py      # Content Briefs generieren & hochladen
├── fix_priorities.py        # Prioritäten ohne Gemini aktualisieren
├── data/
│   ├── keywords_full.json   # 536 Keywords (Rohdaten)
│   └── clusters_output.json # 30 Cluster (Clustering-Ergebnis)
├── content-briefs/          # 30 generierte Content Briefs (.md)
├── requirements.txt
└── .env.example
```
