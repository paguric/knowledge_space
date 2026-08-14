---
name: knowledge-space-mcp
description: Consulta i documenti personali dell'utente indicizzati in Knowledge Space tramite il server MCP (http://127.0.0.1:8456/knowledge-space/mcp). Usala quando l'utente chiede informazioni contenute nei suoi documenti gestiti da knowledge-space (PDF, DOCX, note, leggi, fatture, appunti...). Vietato usare la CLI `ks` e vietato leggere direttamente i file del workspace.
---

# Knowledge Space MCP

L'utente gestisce i propri documenti con **Knowledge Space** (`knowledge-space`): un
programma che indicizza i documenti in workspace/basi/domini e li espone in sola
lettura via server MCP sul workspace attivo.

## Quando usarla

Usa gli strumenti MCP di knowledge-space ogni volta che l'utente fa domande sui
**suoi documenti personali** (contenuti di PDF, DOCX, note, leggi, fatture,
appunti, ecc.) — anche se la domanda non nomina esplicitamente knowledge-space.

## Come procedere

1. (Opzionale) Orientati: `domain_list` e `base_list` per vedere domini e basi
   disponibili del workspace attivo.
2. Cerca con `search` usando query mirate al contenuto richiesto. Se il primo
   tentativo non dà risultati, riprova con sinonimi o termini chiave diversi.
3. Rispondi basandoti **solo** sui chunk restituiti dal server (testo e metadati).
   Cita il file/base di provenienza quando disponibile.

## Guardrail assoluti

1. **Mai usare la CLI `ks`.** La CLI di knowledge-space è riservata all'utente:
   non usarla per cercare, cambiare configurazione, né per attivare/disattivare
   basi, domini, documenti o workspace.
2. **Mai leggere direttamente i file di un workspace gestito da knowledge-space.**
   Non usare `read`, `grep`, `find`, `ls` o altri strumenti sui file e cartelle
   dentro un workspace (es. `~/ws-test2`, `/home/utente/documenti`). Regola
   pratica: **se una cartella contiene `.knowledge-space/` è off-limits** — la
   compartimentalizzazione imposta dal programma va rispettata. L'unica via è il
   server MCP.

## Nessun risultato rilevante

Se la ricerca nel server non restituisce chunk rilevanti, **non inventare**
risposte e **non cercare altrove**: rispondi che non hai trovato informazioni
valide.

Esempio: se l'utente chiede informazioni su "Mario Rossi" e da knowledge-space
non arrivano chunk che parlano di Mario Rossi, rispondi che non hai trovato
informazioni riguardanti quella persona.

Puoi aggiungere che la persona potrebbe trovarsi in un dominio o base che
l'utente non ha attivato, e chiedere se vuole verificare (l'attivazione la fa
l'utente, non l'agente).

## Riferimenti

- Endpoint MCP: `http://127.0.0.1:8456/knowledge-space/mcp`
- Tool disponibili: `base_list`, `domain_list`, `search` (solo lettura, sempre sul
  workspace attivo)
- Documentazione: `docs/86-mcp-server.md`, sezione "Client MCP" del README
