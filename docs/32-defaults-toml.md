# 32 — Esempio di `defaults.toml`

Configurazione predefinita per tutte le basi del workspace. Vedi [30-configuration.md](30-configuration.md) per la struttura completa.

```toml
# Default per tutte le basi del workspace

[ingestion]
library = "docling"
params.use_gpu = false       # true per accelerare con GPU (docling, embedding)

[chunking]
method = "fixed_size"
chunk_size = 1000
chunk_overlap = 200
separator = "\n\n"

[embedding]
model = "sentence-transformers/all-mpnet-base-v2"
# device = "cpu"

[graph]
# Configurazione del grafo della conoscenza (vedi docs/40-graph.md).
# I parametri di connessione al DB (bolt_uri, credenziali) sono a livello
# workspace in <workspace>/.knowledge-space/graph/graph.json, perché il
# grafo è uno per workspace; qui restano solo i comportamenti per-base.
schema = "manuale"          # "manuale" | "EXTRACTED" | "FREE"
resolver = "semantic"      # "semantic" (default, extra [nlp]) | "exact" | "fuzzy" (extra [fuzzy-matching]) | "none"
on_chunk_change = "eager"  # "eager" (default, ri-estrazione LLM sui chunk cambiati) | "lazy" (solo Chroma update)
chunk_embedding_property = "embedding"   # nome della proprietà vettore nel nodo Chunk

# Node/relationship types + patterns. Ignorati se schema = "EXTRACTED" o "FREE".
# Si possono anche materializzare in <workspace>/.knowledge-space/schema.json
# (vedi docs/40-graph.md §6-bis: caricato, non ricreato).
node_types = ["Person", "Organization", "Concept"]
relationship_types = ["WORKS_FOR", "RELATED_TO"]
patterns = [
    ["Person", "WORKS_FOR", "Organization"],
    ["Concept", "RELATED_TO", "Concept"],
]

# --- Retrieval (fase di ricerca, vedi docs/40-graph.md §14) ---
# Metodo di ricerca GraphRAG usato dall'app per le query su questa base.
# L'utente può specificare uno qualsiasi tra quelli supportati da
# neo4j-graphrag; l'app istanzia il retriever corrispondente.
retriever = "hybrid_cypher"   # vedi tabella in docs/40-graph.md §14
top_k = 5                     # numero di risultati (default del retriever)
# Nome del vector index Neo4j (Topic/Chunk) usato dai retriever vettoriali.
vector_index = "chunk-embeddings"
# Nome del full-text index Neo4j (BM25). Obbligatorio per i retriever "hybrid*".
fulltext_index = "chunk-text"
# Query Cypher di arricchimento eseguita dopo la similarità. Usata dai
# retriever "*_cypher" per arricchire i match con traversal del grafo.
# Variabili in scope: `node` (nodo matchato) e `score` (similarità).
retrieval_query = """
RETURN node.id            AS chunk_id,
       node.text          AS text,
       node.base_name     AS base_name,
       node.file_name     AS file_name,
       node.chunk_index   AS chunk_index,
       score
"""
# Proprietà dei nodi da ritornare inoltre (per i retriever vettoriali puri).
return_properties = ["chunk_id", "text"]

# --- Pipeline di retrieval (Step 8 — docs/91b-roadmap-fase1-ricerca.md) ---
# Tre step sequenziali: pre-retrieval -> retrieval -> post-retrieval.
# Ogni step accetta method = "identity" come NO-OP esplicito (i dati passano
# through, senza istanziare LLM/reranker): pipeline sempre omogenea e
# intento dell'utente dichiarato nel TOML (es. consulente: nulla viene riassunto).

[pre_retrieval]
# Query rewriting. "identity" = nessuna riscrittura (1:1).
method = "identity"
# params = { n_queries = 3 }  # es. per multi_query

[retrieval]
# Metodo di ricerca: "dense" | "sparse" | "hybrid".
# - dense: similarity search sul vector store (sempre disponibile).
# - sparse: BM25-like. Se il modello embedding espone embed_sparse
#   (es. bge-m3) viene usato nativamente; altrimenti la manager monta
#   automaticamente un BM25 esterno (rank_bm25) sul testo grezzo dei chunk,
#   con un warning di log all'avvio.
# - hybrid: ensemble dense + sparse; la fusione e' controllata da `fusion`.
method = "dense"
fusion = "rrf"   # "rrf" (default, robusto) | "weighted_sum" (richiede pesi)

[post_retrieval]
# Numero di risultati finali passati al LLM generatore.
top_k = 10
# Reranking: riordino dei top-N prima della compression.
# "identity" = nessun rerank (l'ordine del retrieval resta tale).
reranker = "identity"
# reranker_model = "BAAI/bge-reranker-v2-m3"   # solo se reranker != "identity"
# Compression: sintesi/riduzione dei contenuti passati all'LLM.
# "identity" = testo originale as-is (nessun riassunto).
# Utile per il profilo consulente: passare i documenti non riassunti al LLM.
compressor = "identity"
```

---

*Ultimo aggiornamento: 21 luglio 2026*
