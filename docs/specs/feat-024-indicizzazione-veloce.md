# Feature 024 — Indicizzazione più veloce

- **Autore:** master
- **Tipo:** feature
- **Stato:** proposta (non implementata)
- **Priorità:** media

## Goal

Ridurre i tempi di indicizzazione dei documenti nuovi (e dei reindex) senza cambiare i risultati.

## Numeri misurati (host, CPU, 2026-08-18)

- Conversione markitdown PDF 112 pagine (codice civile): **29,9s**; overhead fisso ~1s/file
- Embedding bge-m3 chunk 2048 char: **3,3s/chunk** su CPU → codice civile ≈ 283 chunk ≈ **~15 min di solo embedding**
- Il collo di bottiglia è l'embedding (~97% del tempo), non la conversione

## Implementazione

1. **Backend ONNX (leva principale)** — `[embedding] backend = "onnx"` (default `"torch"`): con `optimum` si esporta/carica il modello in ONNX quantizzato int8 alla prima richiesta (cache HuggingFace), fallback silenzioso a torch se optimum manca o l'export fallisce. Atteso 2-4x su CPU (bge-m3 3,3s → ~1s/chunk), RAM dimezzata. `LocalEmbedding._load_model` prova ONNX solo se `backend == "onnx"`; i vettori restano float32 (si de-quantizza in uscita), stesse dimensioni → nessuna incompatibilità con le collection esistenti.
2. **Conversione in parallelo** — `[ingestion] workers = 4` (default 1): `ProcessPoolExecutor` per la sola conversione markitdown dei file nuovi (funzione pura, worker senza modello → memoria contenuta). L'embedding resta nel processo principale (già batch per file). Utile con molti file piccoli (23 file ≈ 23s → ~6s).
3. **Cache vettori per chunk** — `<base>/.knowledge-space/vectors.npz` (`{chunk_id: vector}`): a ogni ingest si salvano i vettori nuovi; il reindex riusa il vettore se `content_hash` del chunk è invariato (ri-embeddare solo i chunk cambiati). `ks reindex` con niente cambiato → ~0s di embedding.

## Files to touch

| Path | Cambio |
|---|---|
| `packages/knowledge-base/src/knowledge_base/strategies/embedding.py` | backend onnx in `LocalEmbedding._load_model` + export cache |
| `packages/knowledge-base/src/knowledge_base/base_config.py` | chiavi `[embedding] backend`, `[ingestion] workers` + template TOML |
| `packages/knowledge-base/src/knowledge_base/knowledge_base_manager.py` | ProcessPool per la conversione; salvataggio/caricamento vectors.npz |
| `docs/50-ingestion.md`, `docs/70-embedding.md`, `README.md` | documentazione nuove chiavi |
| `packages/knowledge-base/tests/` | test backend onnx (mock optimum), workers (ProcessPool con 1 file), cache vettori |

## Verifica

```bash
uv run pytest packages/knowledge-base/tests/ -q
# su dataset_legale_small con bge-m3:
time ks ingest -b legislazione          # backend torch (baseline)
ks config set embedding.backend onnx
time ks ingest -b legislazione --force  # atteso 2-4x
ks config set ingestion.workers 4
time ks ingest -b clienti               # molti file piccoli
time ks reindex -a --model-change && time ks reindex -a --model-change   # seconda ~0s embedding
```
