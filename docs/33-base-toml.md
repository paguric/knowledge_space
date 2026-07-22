# 33 — Esempio di `<base>/.knowledge-space/base.toml`

Configurazione specifica di una base di conoscenza. I campi mancanti ereditano da [`defaults.toml`](32-defaults-toml.md). Vedi [30-configuration.md](30-configuration.md) per la struttura completa.

```toml
# Configurazione della base (es. test_kb1)
# I campi mancanti ereditano da defaults.toml

[chunking]
chunk_size = 500          # override del default del workspace
chunk_overlap = 100

[embedding]
model = "sentence-transformers/all-MiniLM-L6-v2"   # base con modello più leggero

[pre_retrieval]
method = "multi_query"
params = { n_queries = 4 }
```

---

*Ultimo aggiornamento: 21 luglio 2026*
