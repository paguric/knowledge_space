# Strategie di ingestion

> **Stato:** implementato | **Step:** 4 | **Fase:** 1A | **Aggiornato:** 22 luglio 2026

## Panoramica

Conversione dei file sorgenti nei formati supportati in testo Markdown strutturato, pronto per il chunking. Ogni strategia incapsula una libreria di conversione e ne espone i parametri configurabili via TOML (`[ingestion].params`).

## Scelte

| Library | Formati | Profilo | GPU |
|---------|---------|---------|-----|
| `docling` | PDF, DOCX, PPTX, HTML | ricercatore | Sì |
| `pymupdf4llm` | PDF | consulente | No |
| `markitdown` | PPTX, DOCX, PDF, HTML, TXT | studente | No |
| `identity` | MD, TXT | tutti | No |

| Aspetto | Scelta |
|---------|--------|
| Insieme formati | **Chiuso**: formato non in lista → errore esplicito |
| Fallback MD/TXT | Se la library configurata non supporta `.md`/`.txt`, si usa automaticamente `identity` (lettura diretta) |
| GPU | `use_gpu` globale (default `false`), ogni libreria decide se usarla |

## Dettagli

### Formati supportati

| Formato | Estensioni | Profilo d'uso prevalente |
|---------|-----------|--------------------------|
| Paper accademici | `.pdf` | `ricercatore` |
| Testi normativi | `.pdf`, `.txt` | `consulente` |
| Libri di testo | `.pdf` | `consulente` |
| Slide | `.pptx` | `studente` |
| Preventivi / contratti | `.docx` | `consulente` |
| Appunti | `.md` | tutti (lettura diretta, nessuna libreria) |

### Interfaccia `IngestionStrategy`

```python
from typing import Protocol
from pathlib import Path

class IngestionStrategy(Protocol):
    """Converte un file sorgente in testo Markdown."""
    name: str
    library: str
    supported_extensions: list[str]

    def convert(self, source_path: Path, **params) -> str:
        """Restituisce il contenuto del file come Markdown."""
        ...
```

Ogni strategy si registra nel registry globale (`knowledge_base.strategies.ingestion`) tramite decoratore `@register("ingestion", name)`.

### Librerie supportate

**Docling** (IBM/DS4SD, MIT): PDF, DOCX, PPTX, HTML, xHTML, immagini, ASCIIDOC. Focus su document understanding profondo, layout model, tabelle, OCR. Dipendenze pesanti (torch, modelli CV opzionali). Lenta senza GPU, OK con GPU.

```toml
[ingestion]
library = "docling"
params.use_gpu = false
params.do_ocr = false
params.do_table_structure = true
params.table_mode = "accurate"     # "accurate" | "fast"
params.generate_page_images = false
params.image_export = "reference"  # "reference" | "embedded" | "none"
```

**PyMuPDF4LLM** (Artifex, ⚠️ AGPL-3.0): solo PDF. PDF → Markdown veloce, multi-colonna, TOC. Dipendenze leggere (C extension). Molto veloce.

```toml
[ingestion]
library = "pymupdf4llm"
params.page_chunks = false
params.write_images = false
params.extract_mode = "standard"   # "standard" | "multicolumn"
params.margins = 5
params.show_progress = false
```

**markitdown** (Microsoft, MIT): PPTX, DOCX, PDF, XLSX, XLS, HTML, TXT, CSV, JSON, XML, immagini, audio. Normalizzazione multi-formato light. Dipendenze leggere (mammoth, pdfminer.six). Veloce.

```toml
[ingestion]
library = "markitdown"
params.plugins = []
```

**identity**: lettura diretta per MD/TXT, nessuna libreria, copia del testo.

### Mappa profili → library

| Profilo | Library | Formato target | Note |
|---------|---------|----------------|------|
| `ricercatore` | `docling` | PDF (paper, legal) | GPU raccomandata per layout complesso |
| `consulente` | `pymupdf4llm` | PDF (testi, norme) | Veloce, multi-colonna, TOC |
| `studente` | `markitdown` | PDF semplici, PPTX, MD | Leggero, multi-formato |
| tutti | — (lettura diretta) | MD | Nessuna libreria, copia del testo |

### Test

| Test | Cosa verifica |
|------|---------------|
| Docling PDF | Output Markdown non vuoto, testo preservato |
| PyMuPDF4LLM multi-col | Output colonne non mescolate |
| Markitdown PPTX | Titolo/bullet/tabelle preservati |
| Estensione sconosciuta | Errore esplicito |
| Libreria non registrata | Errore di config |

## Dipendenze

| Dipende da | Usato da |
|------------|----------|
| Step 3 (BaseConfig, strategy registry) | Step 7 (KnowledgeBaseManager) |
