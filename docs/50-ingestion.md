# Strategie di ingestion

## Obiettivo

Convertire i file sorgenti nei formati supportati in testo Markdown strutturato, pronto per il chunking. Ogni strategia incapsula una libreria di conversione e ne espone i parametri configurabili via TOML (`[ingestion].params`).

## Formati supportati

L'insieme è **chiuso**: qualsiasi formato non in questa lista viene rifiutato con errore esplicito dal manager.

| Formato | Estensioni | Profilo d'uso prevalente |
|---------|-----------|--------------------------|
| Paper accademici | `.pdf` | `researcher` |
| Testi legislativi | `.pdf`, `.txt` | `legal` |
| Libri di testo | `.pdf` | `student` |
| Slide | `.pptx` | `student` |
| Appunti | `.md` | tutti (letteura diretta, nessuna libreria) |

## Interfaccia `IngestionStrategy`

```python
from typing import Protocol
from pathlib import Path

class IngestionStrategy(Protocol):
    """Converte un file sorgente in testo Markdown."""
    name: str  # identificatore unico per il registry
    library: str  # nome della libreria sottostante
    supported_extensions: list[str]

    def convert(self, source_path: Path, **params) -> str:
        """Restituisce il contenuto del file come Markdown."""
        ...
```

Ogni strategy si registra nel registry globale (`knowledge_base.strategies.ingestion`) tramite decoratore `@register("ingestion", name)`. Il `BaseConfigLoader` (Step 3) restituisce il nome della library dal TOML; il manager cerca l'istanza nel registry.

## Librerie supportate

### Docling

| | |
|---|---|
| **Manutentore** | IBM / DS4SD |
| **Licenza** | MIT |
| **Formati** | PDF, DOCX, PPTX, HTML, xHTML, immagini, ASCIIDOC |
| **Focus** | Document understanding profondo, layout model, tabelle, OCR |
| **Dipendenze** | Pesanti (torch, modelli CV opzionali) |
| **Velocità** | Lenta senza GPU; OK con GPU |

Parametri TOML (`[ingestion]`):

```toml
[ingestion]
library = "docling"
params.do_ocr = false              # abilita OCR su immagini incorporate
params.do_table_structure = true    # riconoscimento struttura tabelle
params.table_mode = "accurate"     # "accurate" | "fast"
params.generate_page_images = false
params.image_export = "reference"  # "reference" | "embedded" | "none"
```

**Quando usare**: paper accademici (layout a colonne, formule, tabelle), documenti PDF complessi. Profilo `researcher`.

### PyMuPDF4LLM

| | |
|---|---|
| **Manutentore** | Artifex (PyMuPDF) |
| **Licenza** | ⚠️ **AGPL-3.0** (PyMuPDF) — ok per tesi/accademico, valuta se redistribuisci |
| **Formati** | Solo PDF |
| **Focus** | PDF → Markdown veloce, multi-colonna, TOC |
| **Dipendenze** | Leggere (C extension) |
| **Velocità** | Molto veloce |

Parametri TOML:

```toml
[ingestion]
library = "pymupdf4llm"
params.page_chunks = false         # output come lista di pagine separate
params.write_images = false        # estrai immagini come file
params.extract_mode = "standard"   # "standard" | "multicolumn"
params.margins = 5                 # margini in px per rilevamento colonne
params.show_progress = false
```

**Quando usare**: PDF lunghi a capitoli (libri di testo), multi-colonna. Profilo `student`.

### markitdown

| | |
|---|---|
| **Manutentore** | Microsoft |
| **Licenza** | MIT |
| **Formati** | PPTX, DOCX, PDF, XLSX, XLS, HTML, TXT, CSV, JSON, XML, immagini, audio¹ |
| **Focus** | Normalizzazione multi-formato light |
| **Dipendenze** | Leggere (mammoth, pdfminer.six) |
| **Velocità** | Veloce |

¹ Audio via extra opzionale.

Parametri TOML:

```toml
[ingestion]
library = "markitdown"
# params minimi: markitdown non espone molti parametri nativamente
params.plugins = []                # percorsi a plugin custom opzionali
```

**Quando usare**: slide PPTX, documenti Office, formati eterogenei. Profilo `student` (per PPTX).

### Alternative leggere (registrate come strategie, non default)

- **`pypdf`** (MIT, puro Python, solo estrazione testo grezzo) — fallback per PDF senza layout complesso. Nessun parametro significativo.
- **`pdfplumber`** (MIT, estrazione testo con coordinate) — utile per profilo `legal` quando serve estrarre testo da PDF con struttura basata su coordinate/layout (es. articoli di legge). Parametri: `pages`, `laparams`, `extract_tables`.

## Mappa profili → library

| Profilo | Library | Formato target | Note |
|---------|---------|----------------|------|
| `researcher` | `docling` | PDF (paper) | GPU raccomandata |
| `legal` | `docling` | PDF/TXT | Docling copre OCR + tabelle. Alternativa: `pdfplumber` (layout coordinate) |
| `student` | `pymupdf4llm` | PDF (testi) | Veloce, multi-colonna |
| `student` | `markitdown` | PPTX (slide) | Unica opzione per PPTX |
| tutti | — (lettura diretta) | MD | Nessuna libreria, copia del testo |

## Fasi di implementazione

- **F0 — Interfaccia e registry**: definire `IngestionStrategy` (Protocol), creare modulo `knowledge_base/strategies/ingestion.py`, registrare `identity` (per MD/TXT, copia file) come strategia built-in.
- **F1 — Docling strategy**: incapsulare `docling.document_converter.DocumentConverter` con opzioni `PipelineOptions`. Test con PDF di esempio.
- **F2 — PyMuPDF4LLM strategy**: incapsulare `pymupdf4llm.to_markdown` con parametri. Test con PDF multi-colonna.
- **F3 — markitdown strategy**: incapsulare `markitdown.MarkItDown.convert`. Test con PPTX.
- **F4 — Fallback e alternative**: registrare `pypdf`, `pdfplumber` come strategie aggiuntive.
- **F5 — Validazione formati**: in `KnowledgeBaseManager.add_file`, controllo estensione vs `[ingestion].library` supportate. Rifiuto esplicito per formati non supportati.
- **F6 — Test**: test unit per ogni strategy con file di esempio in `tests/data/synthetic/`. Test di robustezza: file corrotto, PDF vuoto, estensione sconosciuta.

## Test

| Test | Cosa verifica |
|------|---------------|
| Docling PDF | Output Markdown non vuoto, testo preservato |
| PyMuPDF4LLM multi-col | Output colonne non mescolate |
| Markitdown PPTX | Titolo/bullet/tabelle preservati |
| Pypdf fallback | Funziona su PDF semplice |
| Estensione sconosciuta | Errore esplicito |
| Libreria non registrata | Errore di config |

---

*Ultimo aggiornamento: 21 luglio 2026*