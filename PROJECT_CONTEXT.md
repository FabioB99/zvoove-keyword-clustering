# zvoove Keyword Clustering & Content Brief Pipeline — Projektkontext

Dieses Dokument beschreibt die vollständige Pipeline, alle Design-Entscheidungen und den aktuellen Stand. Es dient als Kontextdokument für weiterführende Arbeit im Claude Web Interface.

---

## Überblick

Die Pipeline nimmt 536 Keywords aus Airtable, gruppiert sie semantisch in 30 Themen-Cluster und generiert daraus strukturierte SEO Content Briefs — ebenfalls zurück in Airtable und als Markdown-Dateien.

**Tech Stack:** Python 3.10+, Gemini API, scikit-learn, pyairtable  
**Datenquelle:** Airtable Base mit Keywords-Tabelle (Search Volume, KW Difficulty, Search Intent, Kategorie)  
**Output:** Airtable-Tabelle "Content Briefs" + `content-briefs/*.md`

---

## Pipeline-Schritte im Detail

### Schritt 1: Keywords laden (`extract_airtable.py`)

Liest alle Records aus der Airtable-Tabelle `Keywords` und normalisiert sie in eine Liste von Dicts mit den Feldern: `keyword`, `search_volume`, `keyword_difficulty`, `keyword_category`, `search_intent`, `blog_url`.

Ergebnis wird in `data/keywords_full.json` gespeichert (536 Keywords).

---

### Schritt 2: Clustering (`cluster.py`)

**Algorithmus: K-Means auf normalisierten Gemini-Embeddings**

#### 2a. Embeddings generieren
Jedes Keyword wird über die Gemini Embedding API (`gemini-embedding-2`) in einen hochdimensionalen Vektor umgewandelt, der die semantische Bedeutung des Keywords kodiert. Die Embeddings werden in Batches von 20 abgerufen und in `data/embeddings_cache.npy` zwischengespeichert — bei Abbruch wird beim nächsten Start dort weitergemacht.

#### 2b. K-Means Clustering
```
vectors = normalize(embeddings)   # L2-Normalisierung
KMeans(n_clusters=30, random_state=42, n_init=10).fit_predict(vectors)
```

**Design-Entscheidungen:**
- **L2-Normalisierung vor K-Means:** Embedding-Vektoren unterschiedlicher Länge würden ohne Normalisierung die Distanzberechnung verzerren. Durch Normalisierung auf die Einheitskugel verhält sich K-Means ähnlich wie Cosine-Similarity-basiertes Clustering — semantisch ähnliche Keywords landen näher beieinander.
- **K-Means statt hierarchisches Clustering:** Schneller und skaliert besser für ~500 Keywords. Der Nachteil (fixe Clusteranzahl muss vorab gewählt werden) wird durch manuelles Tuning von `N_CLUSTERS = 30` gelöst.
- **`n_init=10`:** K-Means wird 10x mit zufälligen Startpunkten initialisiert, das beste Ergebnis (niedrigste Inertia) wird genommen — reduziert die Abhängigkeit vom Zufall.
- **`random_state=42`:** Reproduzierbarkeit.

#### 2c. Cluster-Namen generieren
Für jeden Cluster werden die Top-10 Keywords (nach Häufigkeit im Cluster) an Gemini (`gemini-3.1-flash-lite-preview`) übergeben, das einen prägnanten deutschen Cluster-Namen (2–4 Wörter) generiert.

Ergebnis: `data/clusters_output.json` — 30 Cluster mit Namen, Keywords, Keyword-Anzahl, Ø Search Volume.

---

### Schritt 3: Content Briefs generieren (`brief_generation.py`)

Für jeden der 30 Cluster wird ein vollständiges Content Brief erstellt. Die Logik ist bewusst aufgeteilt: was deterministisch berechenbar ist, macht Python — was inhaltliches Urteilsvermögen erfordert, macht Gemini.

#### Stats-Berechnung (Python, deterministisch)
- **Gesamtes Search Volume** (Summe aller Keywords im Cluster)
- **Ø Keyword Difficulty** (Durchschnitt über Keywords mit vorhandenem KD-Wert)
- **Search Intent Verteilung** (informational/transactional/navigational in %)
- **Top 10 Keywords** nach Search Volume
- **Priorität** (Hoch/Mittel/Niedrig) — vollständig in Python berechnet:
  - Hoch: Total SV > 20.000/Monat
  - Mittel: Total SV 3.000–20.000/Monat
  - Niedrig: Total SV < 3.000/Monat

**Design-Entscheidung Priorität:** Frühere Versionen liessen Gemini die Priorität bestimmen — das Ergebnis war durchgehend "Hoch" für alle Cluster. Die Schwellenwerte wurden anhand der tatsächlichen SV-Verteilung der 30 Cluster kalibriert (Min: 691, Max: 447.464, Median: 9.115). Ergebnis: 11× Hoch, 15× Mittel, 4× Niedrig.

#### Gemini-generierte Felder (Gemini 2.5 Flash)
Gemini bekommt: Cluster-Name, Keyword-Liste, Total SV, Ø KD, Intent-Verteilung.

Gemini liefert zurück (JSON):
- `thematischer_fokus`: 1 Satz was das Thema abdeckt
- `content_luecke`: Was in B2B SaaS Blogs typischerweise fehlt
- `zielgruppe`: Rolle, Branche, Pain Points
- `schwerpunkte`: 3 thematische Schwerpunkte mit Beschreibung
- `h1`: SEO-optimierter Arbeitstitel
- `h2s`: 4 Subthemen-Vorschläge
- `content_typ`: Guide / How-To / Vergleich / Übersicht
- `content_laenge`: Empfohlene Wortanzahl + Begründung

**Design-Entscheidung Content-Typ:** Der Prompt enthält explizite Kriterien damit Gemini nicht standardmässig "Guide" wählt:
- *How-To*: Konkrete Prozesse, Schritt-für-Schritt (Lohnabrechnung, Meldeprozesse)
- *Vergleich*: Alternativen, Outsourcing vs. Inhouse, Software-Vergleiche
- *Übersicht*: Gesetzliche Regelungen, Compliance, Tarifwerke, Listen
- *Guide*: Nur wenn keiner der anderen Typen besser passt

#### Airtable-Upload (idempotent)
Das Script prüft beim Start welche Cluster bereits als Brief in Airtable existieren:
- **Existiert bereits** → Update (alle Felder werden überschrieben)
- **Neu** → Create

**Design-Entscheidung Idempotenz:** Frühere Version übersprang bereits hochgeladene Briefs. Das führte dazu, dass Korrekturen (z.B. an Prompt oder Prioritäts-Logik) immer einen manuellen Löschvorgang in Airtable erforderten. Jetzt reicht ein einziger Durchlauf, auch für Re-Runs.

---

## Rate Limits & Fehlerbehandlung

| API | Limit | Handling |
|-----|-------|----------|
| Gemini Embedding | 100 req/min | Batch à 20, 4s Sleep |
| Gemini Flash (Labeling) | 15 req/min | 5s Sleep |
| Gemini 2.5 Flash (Briefs) | 5 RPM | 12s Sleep |
| Alle | 429 Rate Limit | Automatischer Retry nach 90s |
| Alle | 503 Unavailable | Automatischer Retry nach 30s |

**Bekannte Einschränkung:** Gemini Free Tier hat ein Tageslimit. Bei mehrfachem Ausführen an einem Tag können die Keys ausgeschöpft werden. Empfehlung: Pro Tag maximal einen vollständigen Durchlauf.

---

## Dateistruktur

```
├── main.py                  # Orchestriert Schritt 1+2 (Clustering)
├── extract_airtable.py      # Keywords aus Airtable laden
├── cluster.py               # Embeddings + K-Means + Cluster-Namen
├── upload_airtable.py       # Cluster-Ergebnisse in Airtable schreiben
├── brief_generation.py      # Content Briefs generieren & hochladen
├── fix_priorities.py        # Prioritäten ohne Gemini aktualisieren
├── data/
│   ├── keywords_full.json   # 536 Keywords (Rohdaten aus Airtable)
│   ├── clusters_output.json # 30 Cluster mit Keywords (Clustering-Output)
│   └── embeddings_cache.npy # Embedding-Cache (nicht im Git)
├── content-briefs/          # 30 generierte Content Briefs (.md)
└── requirements.txt
```

---

## Aktueller Stand (April 2026)

- 536 Keywords in 30 Cluster aufgeteilt — **erledigt**
- 30 Content Briefs in Airtable + als Markdown — **erledigt**
- Prioritäten korrekt nach SV-Schwellenwerten gesetzt — **erledigt**
- Content-Typen durch Gemini bestimmt (15/30 Cluster haben aktuellen Content-Typ, 15/30 haben noch den alten Wert aus einem früheren Run mit schlechterem Prompt) — **teilweise, Gemini-Tageslimit erreicht**
- Nächster Schritt: `python brief_generation.py` nochmals ausführen (am nächsten Tag) um die restlichen Content-Typen zu aktualisieren
