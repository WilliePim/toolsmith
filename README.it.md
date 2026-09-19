# toolsmith

*Italiano · [English](README.md)*

Un agente che parte con due strumenti — una calcolatrice e la data di oggi — e **ne scrive un terzo quando incontra un compito che i primi due non risolvono**. Lo strumento che scrive è un normale file Python su disco; il compito successivo dello stesso tipo lo richiama, invece di riscriverlo.

Non è "genera del codice ed eseguilo". Uno strumento scritto dal modello attraversa quattro cancelli prima di poter essere chiamato:

1. una **guardia statica** legge il sorgente e lo rifiuta con una motivazione, oppure lo lascia passare;
2. un **sandbox** lo esegue in un sottoprocesso blindato, contro i test del modello *e* contro input che non ha mai visto;
3. un **registro** salva lo strumento che passa come `generated/<nome>.py`;
4. lo strumento salvato entra nella lista degli strumenti del modello **già al round successivo**, a metà conversazione.

Il progetto è ricostruito da zero a partire dal tutorial *"Build an Agent That Writes Its Own Tools"*, la cui seconda metà era dietro un paywall. I moduli mancanti sono stati progettati dal diagramma dell'architettura e dai vincoli dichiarati, poi provati con una suite di red-team. La dipendenza da Groq del tutorial è sostituita da un livello neutrale con adattatori **Gemini** e **Claude**.

## Che aspetto ha

```
$ uv run python -m src.main run gstin_1
──────────────────────────── gstin_1  (GSTIN check character) ────────────────────────────
  r1 write_tool 'gstin_check_char': registered
  r2 gstin_check_char(prefix='16TEUYJ4263R1Z') -> 'K'
  r2 gstin_check_char(prefix='14ELRKY8914Q4Z') -> 'X'
  r2 gstin_check_char(prefix='03ZPVMA6122X3Z') -> 'M'
  r2 gstin_check_char(prefix='07RJXDS8075B1Z') -> 'S'
  r3 submit_answer -> 'KXMS' correct
```

Lanciando poi `gstin_2`, richiama lo strumento che ha già, con una frazione dei token.

## Avvio rapido

Servono [Python 3.12+](https://www.python.org/) e [uv](https://docs.astral.sh/uv/).

```bash
uv sync                              # installa le dipendenze bloccate
cp .env.example .env                 # poi incolla una chiave Gemini in .env
```

Una chiave API Gemini gratuita si ottiene da [aistudio.google.com/apikey](https://aistudio.google.com/apikey) (senza carta di credito). Incollala in `.env` come `GEMINI_API_KEY=...`. Per usare Claude, imposta `PROVIDER=claude` e `ANTHROPIC_API_KEY=...` (a consumo, da [console.anthropic.com](https://console.anthropic.com); un abbonamento a Claude.ai non è accesso API).

```bash
uv run python -m src.main redteam            # prova i due livelli di sicurezza — senza chiave
uv run python -m src.main run gstin_1        # risolve un compito
uv run python -m src.main run --all          # tutto il set core
uv run python -m src.main run --all --set finance
uv run python -m src.main tools              # elenca gli strumenti scritti dall'agente
uv run python -m src.main show gstin_check_char
uv run python -m src.main reset              # svuota la cassetta degli attrezzi
```

Aggiungi `--provider claude` a un `run` per cambiare modello per quel comando.

## I compiti

Due **set** di compiti, ciascuno con due **famiglie**, ogni famiglia con due compiti perché il secondo riusi lo strumento del primo. Le famiglie sono scelte per sollecitare ogni parte della macchina; vedi [docs/it/task-sets.md](docs/it/task-sets.md).

| Set | Famiglia | La regola | Il caso limite nascosto |
|---|---|---|---|
| `core` | carattere di controllo GSTIN | un checksum base-36 su 14 caratteri | un carattere di controllo che è una cifra, non una lettera |
| `core` | etichetta di settimana ISO | `YYYY-Www-D` da una data | una data la cui settimana ISO appartiene all'anno vicino |
| `finance` | cifra di controllo ISIN | lettere → cifre, poi Luhn | le lettere nel corpo spostano il raddoppio di Luhn |
| `finance` | seduta di borsa | l'n-esima seduta dopo una data | un giorno di chiusura dentro l'intervallo |

Ogni file di compiti è generato da codice di riferimento (`src/taskgen.py`, `src/taskgen_finance.py`); le risposte finance sono verificate con `python-stdnum` ed `exchange-calendars`.

## Com'è costruito

Ogni modulo ha una autoverifica `__main__` eseguibile da sola (`uv run python -m src.<modulo>`). I livelli di sicurezza sono provati senza chiamate API:

```bash
uv run python -m src.redteam     # 36 attacchi contenuti, 7 strumenti benigni passano
```

Per saperne di più:

- [docs/it/build-journal.md](docs/it/build-journal.md) — ogni passo, perché è stato costruito così, e gli errori fatti lungo la strada (il punto migliore da cui partire).
- [docs/it/architecture.md](docs/it/architecture.md) — il ciclo, i quattro cancelli, i due livelli di sicurezza, come diagrammi.
- [docs/it/security.md](docs/it/security.md) — la guardia, il sandbox, cosa ciascuno vede e non vede, e i limiti noti.
- [docs/it/task-sets.md](docs/it/task-sets.md) — perché queste famiglie, lo schema del file di compiti, come aggiungere un set.
- [docs/it/design.md](docs/it/design.md) — le decisioni di progetto dietro la costruzione.

## Struttura

```
src/
  config.py             ogni impostazione in un unico posto
  taskgen.py            costruisce data/tasks.json (set core)
  taskgen_finance.py    costruisce data/tasks_finance.json (set finance)
  tools.py              i due strumenti iniziali (calc, today)
  llm.py                una sola porta verso il modello
  providers/            gemini.py, claude.py e le forme neutrali in base.py
  protocol.py           preambolo, footer e lettura dei risultati del sandbox
  sandbox.py            esegue uno strumento in un sottoprocesso blindato
  guard.py              il livello statico (AST)
  registry.py           la cassetta degli attrezzi che cresce, come file
  smith.py              scrivi, controlla, registra
  tasks.py, prompts.py  compiti tipizzati e ciò che viene detto al modello
  agent.py              il ciclo dei round e "la riga"
  attacks.py, redteam.py  la prova adversariale
  main.py               la riga di comando
```

## Nota di sicurezza

Il sandbox nega accessi a sistema operativo, filesystem e rete tramite un audit hook di Python, ed esegue ogni strumento in un sottoprocesso isolato con un ambiente ripulito (nessuna chiave API), un timeout e un tetto sull'output. Su POSIX imposta anche limiti rigidi di CPU e memoria; su Windows la memoria è limitata solo dal timeout. È una barriera solida per una demo, non la pretesa di un isolamento perfetto — non puntarlo su input non fidati su una macchina che non puoi permetterti di perdere. Vedi [docs/it/security.md](docs/it/security.md).
