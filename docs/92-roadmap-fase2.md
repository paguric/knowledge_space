> ⚠️ **Deprecato.** Questo file è stato sostituito da [roadmap.md](roadmap.md). Conservato per riferimento storico. Non aggiornare.

# Fase 2 — Testing e validazione (deprecato)

Validare end-to-end la pipeline di business completa (Fase 1) tramite dataset sintetici e profili di configurazione predefiniti, prima di esporre il sistema tramite CLI/MCP/REST.

> Per la collocazione di questa fase nel piano generale: vedi [90-roadmap-overview.md](90-roadmap-overview.md).

---

### Step 9: Dataset sintetico — dominio legale svizzero/europeo

Un unico dataset focalizzato su diritto svizzero ed europeo, con documenti in italiano e inglese. Copre tutti i formati supportati (PDF, TXT, DOCX, MD) su un dominio coerente, così da validare ingestion, chunking ed embedding con contenuti reali ma riproducibili.

> Il dataset è dichiaratamente **minimale**: pochi documenti mirati, non una collezione esaustiva. L'obiettivo è validare la pipeline end-to-end, non fare benchmark su larga scala.

#### Fonti e documenti previsti

| # | Documento | Formato | Lingua | Fonte | Note |
|---|-----------|---------|--------|-------|------|
| 1 | Costituzione federale della Confederazione Svizzera (estratti: preambolo, Titolo 1, Diritti fondamentali) | PDF, TXT | IT | [fedlex.admin.ch](https://www.fedlex.admin.ch/eli/cc/1999/404/it) | Testo normativo con articoli e capoversi |
| 2 | Bundesverfassung (stessi articoli, versione tedesca) | PDF | DE | fedlex.admin.ch | Per testare multilingua oltre IT/EN |
| 3 | Swiss Code of Obligations (OR) — estratto sul contratto di lavoro (art. 319–362) | PDF, TXT | EN | [fedlex.admin.ch](https://www.fedlex.admin.ch/eli/cc/27/317_321_377/en) | Traduzione ufficiale inglese |
| 4 | GDPR (Regolamento UE 2016/679) — estratti: Capo I, II, III (art. 1–49) | PDF, TXT, DOCX | IT, EN | [eur-lex.europa.eu](https://eur-lex.europa.eu/eli/reg/2016/679/oj) | Bilingue IT+EN. Struttura articoli/commi/lettere |
| 5 | Sentenza fittizia del Tribunale federale svizzero (redatta per il dataset) | MD | IT | generata con template | Testo argomentativo con riferimenti incrociati a Costituzione e GDPR |
| 6 | Contratto di lavoro fittizio conforme al Codice delle obbligazioni | DOCX | IT | generato con template | Documento Office con tabelle (clausole, firme) |
| 7 | EU AI Act (Regolamento UE 2024/1689) — estratto: Titoli I–IV (art. 1–78) | PDF, TXT | EN | [eur-lex.europa.eu](https://eur-lex.europa.eu/eli/reg/2024/1689/oj) | Normativa recente, struttura multilivello |

Ogni documento è scaricabile da fonte pubblica ufficiale o generabile via script. I PDF sono conservati in `tests/data/synthetic/legal/pdf/`, i TXT estratti in `tests/data/synthetic/legal/txt/`, i DOCX in `tests/data/synthetic/legal/docx/`, i MD in `tests/data/synthetic/legal/md/`.

#### Query golden

Per ogni documento, definire 2–4 query con risposta attesa:

| Query | Documento target | Chunk/snippet atteso | Tipo |
|-------|-----------------|---------------------|------|
| "Quali sono i diritti fondamentali garantiti dalla Costituzione svizzera?" | Costituzione svizzera (IT) | Art. 7–36 | fattuale |
| "What are the obligations of an employer regarding working hours?" | Swiss Code of Obligations (EN) | Art. 319–321 | fattuale |
| "Come si definisce il consenso nel GDPR?" | GDPR (IT) | Art. 4, punto 11 | definizione |
| "Esiste un conflitto tra la libertà di espressione (Cost. svizzera) e la protezione dei dati (GDPR)?" | Sentenza fittizia + GDPR | Sezione della sentenza che cita entrambi | cross-document |
| "What are the high-risk AI systems under the EU AI Act?" | EU AI Act (EN) | Titolo III, Art. 6–7 | classificazione |

#### Piano di generazione

1. **Scaricare i documenti ufficiali** da fedlex.admin.ch e eur-lex.europa.eu con uno script `tests/data/synthetic/legal/fetch.py` che accetta `--force` per re-scaricare. Default: skip se il file esiste già (riproducibile senza bussare alle API ogni volta).
2. **Estrarre gli articoli rilevanti** dai PDF scaricati (es. art. 1–49 del GDPR, Titolo I della Costituzione) con uno script `tests/data/synthetic/legal/extract.py` che usa `pymupdf4llm` o `docling` per convertire in TXT e tagliare le sezioni di interesse (parametri: `--input`, `--output`, `--pages`, `--sections`).
3. **Generare i documenti fittizi** con uno script `tests/data/synthetic/legal/generate.py` che:
   - Produce la sentenza in MD italiani realistici (con template Jinja2).
   - Produce il contratto di lavoro in DOCX (con `python-docx`, tabelle, clausole numerate).
   - Accetta un seed per riproducibilità.
4. **Validare il dataset** con uno script `tests/data/synthetic/legal/validate.py` che verifica:
   - Ogni file esiste e ha formato corretto.
   - Ogni file è ingeribile da Docling, PyMuPDF4LLM, markitdown (almeno una delle tre).
   - Le query golden matchano i chunk attesi (test preliminare di integrità).
5. **Documentare** in `tests/data/synthetic/README.md`: fonti, licenze, comandi di rigenerazione.

> **Licenze**: i documenti ufficiali svizzeri (fedlex) sono in pubblico dominio (CDA — Creative Commons Zero). I documenti UE (eur-lex) sono © Unione Europea ma riutilizzabili per scopi non commerciali con attribuzione. Il dataset è solo per test interno. I documenti generati (sentenza, contratto) sono originali e senza vincoli.

---


### Step 10: Profili di configurazione predefiniti

Definire configurazioni TOML default per scenari d'uso rappresentativi. I profili sono **punti di partenza** copiabili dall'utente, non logica hardcoded.

| | `ricercatore` | `consulente` | `studente` |
|---|---|---|---|
| **Scenario** | paper accademici EN | testi normativi, GDPR, contratti, preventivi — IT+EN | slide PPTX, appunti MD, testi brevi — IT, leggero |
| **Ingestion** | `docling` | `pymupdf4llm` per PDF, `docling` per DOCX/OCR | `markitdown` (PPTX, MD, DOCX, HTML) |
| **Chunking** | `recursive` ~1200/200 | `markdown`/structure-aware (header §/Art.) | `recursive` ~800/150 |
| **Embedding** | `gte-large-en-v1.5` (ctx 8192). ⚠️ EN-only | `BAAI/bge-m3` (multilingua, ctx 8192, sparse nativo) | `intfloat/multilingual-e5-small` (dim 384). ⚠️ Non usare `all-MiniLM-L6-v2` (EN-only) |
| **Pre-retrieval** | `multi_query` o `hyde` | `identity` | `identity` |
| **Retrieval** | `hybrid` (dense + sparse) | `dense` (top-k alto, filtro metadati per articolo) | `dense` (top-k medio) |
| **Post-retrieval** | `llm_chain_extract` | `identity` (testo originale) | `identity` |

- [ ] Salvare i profili in `~/.config/knowledge-space/profiles/<name>.toml` per ciascuna colonna della tabella.
- [ ] Documentare come applicare un profilo a un workspace (`defaults.toml` del workspace = copia del profilo).
- [ ] **Per ciascun profilo, documentare nel commento TOML quali lingue supporta l'embedding scelto** e `max_context_tokens`, così l'utente può scegliere consapevolmente.

#### Scelta del retriever per profilo (GraphRAG)

| | `ricercatore` | `consulente` | `studente` |
|---|---|---|---|
| **Question type** | exploratory / synthesis | specific / lookup | specific |
| **Pipeline atomica** | `hybrid_cypher` o `tools` | `vector_cypher` o `text2cypher` | `vector` o `vector_cypher` |

### Step 11: Test end-to-end e benchmark

- [ ] Test end-to-end (in `packages/knowledge-base/tests/e2e/`):
  - Eseguire la pipeline completa (ingest → chunk → embed → retrieve) sul dataset legale per ciascun profilo (ricercatore/consulente/studente), usando la configurazione TOML corrispondente.
  - Verificare che i chunk rilevanti per le query golden vengano recuperati (recall ≥ soglia).
  - Verificare che i flag `active` vengano rispettati (disattivare un dominio → nessun risultato da quelle basi).
- [ ] ~~Benchmark comparativo~~ *(skippato — vedi nota)*:
  - Confrontare i 3 profili su metriche qualitative (recall@k, MRR, latenza ingestion, latenza query).
  - Produrre un report markdown con tabelle (es. `docs/benchmark.md`).

> **Benchmark skippato**: il benchmark comparativo tra profili è fuori scope per questa tesi. La validazione si limita ai test end-to-end (recall ≥ soglia sui query golden) e al rispetto dei flag `active`. L'analisi comparativa delle metriche (MRR, latenza, confronto tra profili) è rimandata a un eventuale futuro lavoro.
- [ ] **Strategy LLM-based**: usare stub/mock per query rewriting e compression nei test CI; opzionale un test manuale con LLM reale (skip di default).

> L'astrazione LLM è definita in [75-llm.md](75-llm.md) (Step 6-bis): `LLMStrategy` Protocol, registry, `llm_factory`. I provider reali (OpenAI, Ollama, Anthropic) sono disponibili da Fase 1B in poi. Per i test in Fase 2, usare i mock (`mock/echo`, `mock/fixed`) in CI; test opzionale con LLM reale marcato `@pytest.mark.llm`.

### Step 12: Logging su file

Aggiungere un sistema di logging su file così che, quando l'utente usa la CLI (Fase 3) e qualcosa si rompe, il traceback e il contesto siano disponibili su disco senza dover rilanciare con `-v`. Sostituisce il vecchio `ks_logging.py` legacy (rimosso nello Step 3) con un'implementazione app-level che rispetta `RuntimePaths` (XDG) e non usa variabili globali.

> **Collocazione**: in Fase 2 perché serve ai test E2E (Step 11) per ispezionare i failure e alla CLI (Fase 3) per il debug utente. `knowledge-base` **non** ha dipendenze da logging config: usa già `logging.getLogger(__name__)` ovunque (vedi `base_config.py`, `strategies/*`); basta che l'app configuri il root logger una volta all'avvio.

- [ ] Creare `knowledge_space/logging.py` con `setup_logging(runtime_paths: RuntimePaths, *, verbose: bool = False, log_level: str | None = None) -> Path`:
  - **File handler** (sempre attivo, livello DEBUG): `RotatingFileHandler` su `<runtime_paths.state_home>/logs/ks.log`, max 5 MB × 3 backup, encoding UTF-8. Crea la directory `logs/` se mancante (`runtime_paths.ensure_dirs()` già esiste).
  - **Console handler** (stderr): livello INFO di default, DEBUG se `verbose=True` (flag `--verbose`/`-v` della CLI, vedi [95-cli.md](95-cli.md)).
  - `log_level` (da `KS_LOG_LEVEL` env, vedi [30-configuration.md](30-configuration.md)) ha precedenza e imposta il livello **del root logger** (sia file che console). Valori ammessi: `DEBUG|INFO|WARNING|ERROR|CRITICAL` (case-insensitive); valore non riconosciuto → warning + fallback a INFO.
  - Formato: `%(asctime)s %(levelname)-8s %(name)s %(message)s` (data ISO-8601 con millisecondi).
  - Evita handler duplicati: se il root logger ha già un `RotatingFileHandler` per lo stesso path, non ne aggiunge un secondo (idempotente — importante perché la CLI standalone crea un `AppContext` per ogni comando).
  - Ritorna il path del file di log (utile per stampare "Log: <path>" all'utente in caso di errore).
- [ ] **Uncaught exception hook**: installare `sys.excepthook` che logga il traceback completo su file ( livello `ERROR`) prima di delegare al hook di default. così i crash della CLI finiscono nel log anche quando l'utente non ha `-v`.
- [ ] **Silenzio librerie verbose**: impostare `WARNING` sui logger di dipendenze note (es. `chromadb`, `sentence_transformers`, `urllib3`, `httpx`, `watchdog`) per non saturare il log di rumore; il logger `knowledge_base` resta al livello del root (DEBUG quando attivo).
- [ ] Integrare `setup_logging()` in `build_app_context()` ([11-app-lifecycle.md](11-app-lifecycle.md), Step 8-ter): chiamata come **prima cosa**, prima di istanziare i manager, così i warning di caricamento config (Step 3) finiscono nel log. Il `RuntimePaths` è già disponibile; `verbose` e `log_level` sono parametri opzionali della `build_app_context` (la CLI li passerà dai flag).
- [ ] **Entry point CLI** (Fase 3): il comando `ks` chiama `setup_logging()` subito dopo il parse dei flag globali (`--verbose`, `KS_LOG_LEVEL` env), prima di qualsiasi operazione. In caso di errore fatale, il messaggio finale all'utente include: `Errore: <msg>. Dettagli in: <log_path>`.
- [ ] Esportare `setup_logging` da `knowledge_space` (usato anche da MCP server e REST API in Fasi successive).
- [ ] Scrivere test in `tests/test_logging.py`:
  - File di log viene creato in `<state_home>/logs/ks.log`.
  - Messaggi a vari livelli (DEBUG/INFO/WARNING/ERROR) finiscono nel file (file sempre DEBUG).
  - Console handler rispetta `verbose` (INFO di default, DEBUG con `verbose=True`) — verificabile catturando stderr con `caplog` o `capsys`.
  - `KS_LOG_LEVEL="WARNING"` silenzia DEBUG e INFO sia su file che console.
  - Valore non riconosciuto di `KS_LOG_LEVEL` → warning + fallback INFO.
  - Idempotenza: chiamare `setup_logging()` due volte non duplica gli handler.
  - Uncaught exception: simulare un'eccezione non catturata e verificare che il traceback finisca nel file di log.

---

*Ultimo aggiornamento: 21 luglio 2026*