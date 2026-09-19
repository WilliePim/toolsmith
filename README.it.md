# toolsmith

*Italiano · [English](README.md)*

Un agente che parte con due strumenti — una calcolatrice e la data di oggi — e **ne scrive un terzo quando incontra un compito che i primi due non risolvono**. Lo strumento che scrive è un normale file Python su disco; il compito successivo dello stesso tipo lo richiama invece di riscriverlo.

Uno strumento scritto dal modello attraversa quattro cancelli prima di poter essere chiamato:

1. una **guardia statica** legge il sorgente e lo rifiuta con una motivazione, oppure lo lascia passare;
2. un **sandbox** lo esegue in un sottoprocesso blindato, contro i test del modello *e* contro input che non ha mai visto;
3. un **registro** salva lo strumento che passa come `generated/<nome>.py`;
4. lo strumento salvato entra nella lista degli strumenti **già al round successivo**, a metà conversazione.

> ### Cos'è, e cosa non è
>
> Questa è la **dimostrazione di un meccanismo, non un benchmark.** Esegue 8 compiti
> in 4 famiglie. Basta a mostrare che il ciclo, la guardia, il sandbox e il riuso
> funzionano, ed è ben lontano dal permettere un'affermazione generale su agenti,
> modelli o tipi di compito. I numeri qui sotto vengono da esecuzioni ripetute di
> quegli 8 compiti soltanto.
>
> Ogni cifra in questo file è generata da `src/report.py` a partire dai file in
> `results/`. Nessuna è scritta a mano. Si riproducono con un comando:
> `uv run python -m src.bench --repeats 10 && uv run python -m src.report`.

<!-- GENERATED:bench-header:START -->
<!-- GENERATED:bench-header:END -->

## Che aspetto ha

```
$ uv run python -m src.main run gstin_1
────────────────── gstin_1  (GSTIN check character) ──────────────────
  r2 write_tool 'gstin_check_char': registered
  r3 gstin_check_char(prefix='16TEUYJ4263R1Z') -> 'K'
  r3 gstin_check_char(prefix='14ELRKY8914Q4Z') -> 'X'
  r3 gstin_check_char(prefix='03ZPVMA6122X3Z') -> 'M'
  r3 gstin_check_char(prefix='07RJXDS8075B1Z') -> 'S'
  r4 submit_answer -> 'KXMS' correct
```

## Scrivere strumenti conviene davvero?

Il modo onesto di rispondere è eseguire gli stessi compiti molte volte, in due
condizioni, e riportare la dispersione invece di una corsa fortunata.

**Con strumenti** l'agente può scrivere, registrare e chiamare strumenti. **Baseline** è
lo stesso modello, gli stessi compiti e lo stesso prompt *meno le righe sulla scrittura
degli strumenti*: un prompt che descrivesse uno strumento che quella condizione non può
usare la penalizzerebbe, invece di misurarla.

<!-- GENERATED:prompt-diff:START -->
<!-- GENERATED:prompt-diff:END -->

### Accuratezza e costo, per condizione

<!-- GENERATED:bench-conditions:START -->
<!-- GENERATED:bench-conditions:END -->

### Riuso: quanto costa il secondo compito di una famiglia

Ogni famiglia ha due compiti. Il primo deve scrivere lo strumento; il secondo può
limitarsi a chiamarlo. Misurato per ogni ripetizione, poi riportato come media e
intervallo — una coppia sola è un aneddoto.

<!-- GENERATED:bench-reuse:START -->
<!-- GENERATED:bench-reuse:END -->

### Per compito

<!-- GENERATED:bench-tasks:START -->
<!-- GENERATED:bench-tasks:END -->

## Dove sbaglia

I fallimenti sono elencati, non nascosti e non rilanciati finché passano. Ogni
esecuzione qui sotto è in `results/runs/` con il suo record completo.

<!-- GENERATED:bench-failures:START -->
<!-- GENERATED:bench-failures:END -->

## Il sandbox, misurato

`src/attacks.py` contiene strumenti ostili nelle categorie qui sotto; `src/redteam.py`
esegue ciascuno e registra quale livello l'ha fermato. Gli attacchi diretti al runtime
sono inviati **oltre la guardia di proposito**, per dimostrare che l'audit hook regge da
solo. Non servono chiamate API, quindi chiunque può riprodurlo in pochi secondi:

```bash
uv run python -m src.redteam --json results/sandbox_$(uname -s).json
```

Categorie coperte: lettura fuori dalla cartella permessa, scrittura su disco, accesso
alla rete, avvio di processi, cicli infiniti, uso eccessivo di memoria, import di moduli
vietati, fuga dall'interprete, e ingoiare la violazione del sandbox.

<!-- GENERATED:sandbox:START -->
<!-- GENERATED:sandbox:END -->

**Un limite dichiarato, non corretto.** Su Windows una singola allocazione da 4 GB *non*
viene contenuta: non esiste un tetto allo spazio di indirizzamento, e l'allocazione
finisce ben prima del timeout del watchdog. Su Linux il sandbox imposta `RLIMIT_AS`, e
lo stesso attacco viene rifiutato. Lo riportiamo invece di correggerlo in silenzio,
perché una suite che nasconde le proprie mancanze non vale nulla.

## Avvio rapido

Servono [Python 3.12+](https://www.python.org/) e [uv](https://docs.astral.sh/uv/).

```bash
uv sync                              # installa le dipendenze bloccate
cp .env.example .env                 # poi incolla una chiave Gemini in .env
```

Una chiave API Gemini gratuita si ottiene da [aistudio.google.com/apikey](https://aistudio.google.com/apikey). Incollala in `.env` come `GEMINI_API_KEY=...`. Per usare Claude, imposta `PROVIDER=claude` e `ANTHROPIC_API_KEY=...` (a consumo; un abbonamento a Claude.ai non è accesso API).

```bash
uv run python -m src.main redteam            # prova i due livelli di sicurezza — senza chiave
uv run python -m src.main run gstin_1        # risolve un compito
uv run python -m src.main run --all          # tutto il set core
uv run python -m src.main run --all --set finance
uv run python -m src.main tools              # elenca gli strumenti scritti dall'agente
uv run python -m src.main show gstin_check_char
uv run python -m src.main reset              # svuota la cassetta degli attrezzi
```

Riprodurre le misure (consuma quota API, e riprende se viene interrotto):

```bash
uv run python -m src.bench --repeats 10      # ogni compito, entrambe le condizioni
uv run python -m src.report                  # rigenera ogni tabella qui sopra
```

## I compiti

Due **set** di compiti, ciascuno con due **famiglie**, ogni famiglia con due compiti
perché il secondo riusi lo strumento del primo. Le famiglie sono scelte per sollecitare
ogni parte della macchina; vedi [docs/it/task-sets.md](docs/it/task-sets.md).

| Set | Famiglia | La regola | Il caso limite nascosto |
|---|---|---|---|
| `core` | carattere di controllo GSTIN | un checksum base-36 su 14 caratteri | un carattere di controllo che è una cifra, non una lettera |
| `core` | etichetta di settimana ISO | `YYYY-Www-D` da una data | una data la cui settimana ISO appartiene all'anno vicino |
| `finance` | cifra di controllo ISIN | lettere → cifre, poi Luhn | le lettere nel corpo spostano il raddoppio di Luhn |
| `finance` | seduta di borsa | l'n-esima seduta dopo una data | un giorno di chiusura dentro l'intervallo |

Ogni file di compiti è generato da codice di riferimento (`src/taskgen.py`, `src/taskgen_finance.py`); le risposte finance sono verificate con `python-stdnum` ed `exchange-calendars`.

## Cosa viene dal riferimento, e cosa è nuovo qui

Il progetto segue un tutorial sulla costruzione di un agente che estende sé stesso, la
cui seconda metà era dietro un paywall. *Riferimento: (segnaposto — da inserire).* Nulla
di esso è riprodotto qui: né testo, né figure, né tabelle. Quella che segue è una
descrizione con parole mie di quali idee venissero dalla metà leggibile, e quali siano
state progettate per questo repository.

**Dal riferimento (idee, reimplementate):** la forma generale — un agente la cui lista di
strumenti viene ricostruita dentro il ciclo dei round; dividere la sicurezza in una
lettura statica del sorgente e un'esecuzione in sandbox; verificare uno strumento
generato contro input che il modello non può vedere; tenere gli strumenti come file
semplici perché sopravvivano alla conversazione; e i due strumenti iniziali scelti per
essere deliberatamente quasi-pertinenti. La famiglia GSTIN e il suo esempio svolto
vengono dal riferimento; il file dei compiti qui è rigenerato da un'implementazione di
riferimento, perché la risposta d'esempio del riferimento per un input nascosto non
tornava.

**Nuovo qui:** ogni modulo dopo la metà è stato progettato da zero — l'esecutore del
sandbox e il suo watchdog, la guardia statica, il registro, il percorso
scrivi-controlla-registra, i prompt, il ciclo dell'agente, il corpus di red-team e la
CLI. Inoltre: un livello del modello neutrale con adattatori Gemini e Claude al posto del
singolo provider del riferimento; un nonce per esecuzione perché uno strumento non possa
falsificare i propri risultati; il precaricamento dei moduli perché l'audit hook non
rompa gli import ordinari; la normalizzazione dei percorsi nella regola di apertura file;
un'interfaccia degli strumenti per famiglia che permette al controllo nascosto di
chiamare uno strumento con input nascosti; un secondo set di compiti verificato con
librerie esterne; e l'intera impalcatura di misura da cui vengono i numeri di questo
README.

## Com'è costruito

Ogni modulo ha una autoverifica `__main__` eseguibile da sola (`uv run python -m src.<modulo>`).

Per saperne di più:

- [docs/it/build-journal.md](docs/it/build-journal.md) — ogni passo, perché è stato costruito così, e gli errori fatti lungo la strada.
- [docs/it/architecture.md](docs/it/architecture.md) — il ciclo, i quattro cancelli, i due livelli di sicurezza.
- [docs/it/security.md](docs/it/security.md) — la guardia, il sandbox, e i limiti noti.
- [docs/it/task-sets.md](docs/it/task-sets.md) — perché queste famiglie, lo schema, come aggiungere un set.
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
  bench.py, report.py   l'impalcatura di misura dietro ogni numero qui sopra
  main.py               la riga di comando
results/
  runs/                 un record JSON per esecuzione
  toolboxes/            gli strumenti scritti da ogni ripetizione
  prompts/              i system prompt esatti usati, entrambe le condizioni
  summary.json          ciò che calcola report.py; la fonte di ogni tabella
```

## Nota di sicurezza

Il sandbox nega accessi a sistema operativo, filesystem e rete tramite un audit hook di
Python, ed esegue ogni strumento in un sottoprocesso isolato con un ambiente ripulito
(nessuna chiave API), un timeout e un tetto sull'output. Su POSIX imposta anche limiti
rigidi di CPU e memoria; su Windows la memoria è limitata solo dal timeout — vedi il
limite misurato qui sopra. È una barriera solida per una demo, non la pretesa di un
isolamento perfetto. Non puntarlo su input non fidati su una macchina che non puoi
permetterti di perdere. Vedi [docs/it/security.md](docs/it/security.md).
