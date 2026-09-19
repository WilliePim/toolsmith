# Architettura

*Italiano · [English](../en/architecture.md)*

Cinque immagini. Parti dalla prima — tutto il resto è macchina al suo servizio.

## 0. Cos'è uno "strumento"

Uno strumento ha due metà. Il modello vede e scrive sempre e solo **JSON**. Il **Python** gira sulla tua macchina, dentro questo programma.

```
 ┌────────────────────────────────────────┐   ┌──────────────────────────────────┐
 │ DESCRIZIONE (JSON) - vista dal modello │   │ CODICE (Python) - gira sul tuo PC│
 │ {"name": "gstin_check_char",           │   │ def run(prefix):                 │
 │  "description": "GSTIN check char",    │   │     ...                          │
 │  "parameters": {"prefix": "string"}}   │   │     return "K"                   │
 └────────────────────────────────────────┘   └──────────────────────────────────┘
   il modello la legge e risponde con         il modello non esegue nulla:
   una *richiesta* JSON: nome + argomenti     il nostro programma lo esegue e riferisce
```

È un **ciclo, non ricorsione.** Il modello è senza stato. A ogni round il nostro programma rispedisce l'intera conversazione; il modello risponde con chiamate a strumenti; noi le eseguiamo e aggiungiamo i risultati; comincia il round successivo.

```
 round 1  inviamo:  [system, task]                 strumenti: calc, today, write_tool, submit_answer
          modello:  write_tool({name: "gstin_check_char", source: "def run(prefix): ...", tests: [...]})
          noi:      guardia OK, sandbox OK, salva .py + .json -> aggiungi "registered gstin_check_char"
 round 2  inviamo:  [system, task, chiamata 1, risultato 1]  strumenti: ... + gstin_check_char <- nuovo
          modello:  quattro chiamate: gstin_check_char({prefix: "16TEUYJ4263R1Z"}), ...
          noi:      esegui il .py nel sandbox -> aggiungi "K", "X", "M", "S"
 round 3  modello:  submit_answer({answer: "KXMS"})   ->  lo valutiamo con la chiave delle risposte
```

Dove vive ciascuna metà:

| Strumento | Metà codice | Metà descrizione | Dove gira |
|---|---|---|---|
| `calc`, `today` | `src/tools.py` | `src/tools.py` (`SCHEMAS`) | nel processo (fidato) |
| `write_tool`, `submit_answer` | `agent.py` / `smith.py` | `src/prompts.py` | nel processo |
| scritto dal modello | `generated/<nome>.py` | `generated/<nome>.json` | sottoprocesso sandbox |

## 1. Un compito, dall'inizio alla fine

```
 data/tasks*.json ── prompt del task ─┐
                                      v
 ┌─────────────────────────────────────────────────────────────┐
 │ CICLO DEI ROUND (max 10 round)                              │
 │  strumenti = calc, today                                    │
 │            + ogni strumento salvato in generated/  <- "la riga" │
 │            + write_tool, submit_answer               ricostruita │
 │  risposta = llm.complete(messages, strumenti)        OGNI round │
 └──────────────────────────────┬──────────────────────────────┘
                                │ il modello chiama gli strumenti
     ┌────────────────┬─────────┴──────┬─────────────────┐
     v                v                v                 v
 calc / today   strumento generato write_tool      submit_answer
 nel processo   nel sandbox        smith.forge     (termina il task)
     └────────────────┴───────┬────────┘                 │
                              v                           v
              testo del risultato aggiunto ai messaggi  risposta vs attesa
              -> round successivo                        -> tabella risultati
```

## 2. Cosa attraversa `write_tool` (`smith.forge`)

```
 write_tool(name, description, source, tests)
        │
        ├─ 1. VALIDA la specifica ─✗─► "questo strumento deve prendere: prefix (string)"
        ├─ 2. GUARDIA sul sorgente ✗─► "line 4: import of 'os' is not allowed"
        ├─ 3. SANDBOX una volta: i tuoi test + ogni batch nascosto
        │        ─✗ test proprio ──► "run({...}) ha reso 'X', atteso 'W'"
        │        ─✗ nascosto ──────► "falliti 2 su 3 controlli nascosti" + indizio
        │                            (nessun input, nessun valore, solo un conteggio)
        └─ 4. REGISTRO lo salva ───► generated/<nome>.py + <nome>.json
                                     -> entra nell'array degli strumenti al round dopo

 ✗ = il messaggio torna al modello come risultato di strumento: un tentativo di
     riparazione, non la fine del task (primo tentativo + 3 riparazioni per task).
```

## 3. Dentro un'esecuzione del sandbox (`protocol.py` + `sandbox.py`)

```
 PADRE (processo dell'agente)               FIGLIO: python -I -S -B -X utf8 tool.py
                                            (cartella temp nuova, ambiente senza chiavi API)
                                           ┌───────────────────────────────────────┐
 chiamate, un JSON per riga                │ PREAMBOLO  audit hook, non annullabile │
 {"prefix": "16TEUYJ4263R1Z"} ── stdin ──► │ SORGENTE   il def run(...) del modello │
 {"prefix": "14ELRKY8914Q4Z"}              │ FOOTER     per ogni riga: run(**args)  │
                                           └───────────────────┬───────────────────┘
 parse_lines()  ◄────────── stdout ─────────────────────────── ┘
   @@TOOLSMITH@@<nonce>{"ok": true, "value": "K"}   -> risultato
   debug: checking 16TEU...                          -> output vagante, mai interpretato

 watchdog: ogni 20 ms, uccide il figlio se gira > 10 s o stampa > 256 KB
 audit hook nega: chiamate a SO/processi/rete, scritture su file, letture fuori dalla stdlib
```

## 4. I due livelli di sicurezza

| | Guardia statica (`guard.py`) | Sandbox a runtime (`sandbox.py`) |
|---|---|---|
| Quando | prima che qualcosa giri | mentre il codice gira |
| Vede | **nomi** nel sorgente | **valori e tempo** |
| Blocca | `import os`, `eval`, `open`, `__class__`, `except` nudo, trucchi `.format` | SO/processi/rete, scritture, letture fuori dalla stdlib, cicli infiniti, alluvioni di output |
| Cieca a | cicli infiniti, alluvioni di stampe | nulla su cui è agganciata |
| Costo di un blocco | un turno di riparazione | una chiamata fallita |

`redteam.py` attacca ogni livello separatamente, inclusi attacchi inviati dritti al sandbox con la guardia saltata. Vedi [security.md](security.md).

## I moduli

```
config       ogni impostazione; il registro dei set di compiti
tasks        carica un file di compiti in oggetti Task + Family tipizzati
taskgen[_finance]  costruiscono i file di compiti da codice / librerie di riferimento
tools        calc, today; la forma neutrale SCHEMAS
llm + providers/   una porta verso Gemini o Claude; non solleva mai
protocol     build_script() (preambolo + sorgente + footer), parse_lines()
sandbox      run_calls(): il sottoprocesso blindato e il suo watchdog
guard        check(): il livello statico (AST)
registry     i file .py + .json, load/save/call/reset
smith        forge(): il percorso a quattro cancelli scrivi-controlla-registra
prompts      il system prompt, la riga d'interfaccia, i meta strumenti
agent        solve(): il ciclo dei round e la riga
attacks + redteam  la prova adversariale, senza chiamate API
main         la riga di comando
```
