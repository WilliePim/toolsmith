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
Modello **gemini-3.8-flash**, temperatura *provider default (unset)*, commit `f292c9f+dirty`, eseguito il 2026-09-19. 10 ripetizioni per compito e condizione: 160 esecuzioni, 289,046 token in uscita, costo totale $2.31. Errori del provider rilanciati: 0. Escluse dalle medie 5 esecuzioni fuori disegno, raccolte dopo per catturare una traccia.
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
Vengono tolte solo le righe sugli strumenti; l'apertura e l'istruzione finale sono identiche byte per byte nelle due condizioni.

```diff
--- with tools
+++ baseline
@@ -2,11 +2,2 @@
 
-You have a calculator and today's date to start with. When a task applies one rule across many inputs, do not work it out by hand: write a tool with write_tool, then call it. A written tool is exact and reusable, and a later task of the same kind can just call it.
-
-When you write a tool, follow this contract exactly:
-- Define one function, run(...), taking exactly the parameters the task states, and returning a string.
-- Use only the Python standard library, and only these modules: calendar, collections, datetime, decimal, functools, itertools, json, math, re, string, typing. Do not read files, write files, use the network, or print anything you need - return it.
-- Work out each test's expected result from the worked example in the task, by hand, before you write the code. If you cannot, you do not yet understand the rule.
-- Give at least two tests. The tool is also checked against inputs you cannot see, so make run() follow the rule in general, not just for your tests.
-
-If a tool is refused, read the reason and repair it: a refusal is a step, not the end.
- When you have the final answer, call submit_answer with exactly the format the task asks for. Do not call submit_answer until you are sure.
+You have a calculator and today's date to start with. When you have the final answer, call submit_answer with exactly the format the task asks for. Do not call submit_answer until you are sure.
```
<!-- GENERATED:prompt-diff:END -->

### Accuratezza e costo, per condizione

<!-- GENERATED:bench-conditions:START -->
| condizione | run | risolti | accuratezza | token in (media) | token out (media) | costo totale (USD) |
|---|---|---|---|---|---|---|
| tools | 80 | 80 | 100% | 7,795 | 697 | $0.68 |
| baseline | 80 | 66 | 82% | 12,659 | 2,916 | $1.63 |
<!-- GENERATED:bench-conditions:END -->

### Riuso: quanto costa il secondo compito di una famiglia

Ogni famiglia ha due compiti. Il primo deve scrivere lo strumento; il secondo può
limitarsi a chiamarlo. Misurato per ogni ripetizione, poi riportato come media e
intervallo — una coppia sola è un aneddoto.

<!-- GENERATED:bench-reuse:START -->
| famiglia | coppie | token out primo task (media) | secondo (media) | risparmio medio | coppia peggiore | coppia migliore |
|---|---|---|---|---|---|---|
| gstin | 10 | 508 | 272 | 1.8x in meno | 1.4x in piu | 3.3x in meno |
| isin | 10 | 988 | 250 | 3.7x in meno | 1.6x in meno | 6.8x in meno |
| isoweek | 10 | 453 | 166 | 2.5x in meno | 2.1x in meno | 4.6x in meno |
| sessions | 10 | 1,648 | 1,288 | 1.3x in meno | 1.2x in meno | 1.4x in meno |
<!-- GENERATED:bench-reuse:END -->

Il riuso non è denaro gratis, e la tabella lo dice: per `sessions` il risparmio è
modesto, perché ogni chiamata porta comunque l'elenco delle festività della borsa, e per
`gstin` almeno una ripetizione ha speso *di più* sul secondo compito che sul primo. Ciò
che regge in tutte e quattro le famiglie è l'accuratezza, non uno sconto fisso.

### Dove i quattro cancelli sono scattati davvero

Uno strumento viene registrato solo dopo che la guardia l'ha letto e il sandbox l'ha
eseguito su input che il modello non vede mai. Ecco quante volte questo ha respinto
qualcosa durante queste esecuzioni:

Quella tabella va letta con rigore. I rifiuti vengono dai test *propri* del modello e dal
controllo della specifica, e **il controllo su input nascosti non ha mai dovuto respingere
uno strumento in queste 160 esecuzioni**: ha girato ogni volta e ha approvato ogni volta.
Il suo valore è quindi dimostrato per costruzione, non da queste esecuzioni:
`uv run python -m src.smith` costruisce uno strumento GSTIN volutamente sbagliato che
supera i propri test, e mostra il controllo nascosto che lo coglie rivelando solo un
conteggio e un indizio. Un'esecuzione in cui un modello scriva da sé uno strumento simile
non è in questo campione.

<!-- GENERATED:bench-refusals:START -->
| cancello che ha respinto uno strumento | volte |
|---|---|
| own_tests | 3 |
| tests | 2 |

45 tentativi di scrittura in totale; 5 respinti e 3 esecuzioni hanno poi registrato uno strumento riparato.
<!-- GENERATED:bench-refusals:END -->

### Per compito

<!-- GENERATED:bench-tasks:START -->
| task | condizione | run | risolti | tool respinti | riparati | round (media) | token out media (min-max) |
|---|---|---|---|---|---|---|---|
| gstin_1 | baseline | 10 | 8/10 | 0 | 0 | 8.8 | 4,292 (982-5,266) |
| gstin_2 | baseline | 10 | 8/10 | 0 | 0 | 9.8 | 4,780 (1,961-5,875) |
| isoweek_1 | baseline | 10 | 4/10 | 0 | 0 | 8.8 | 895 (289-3,079) |
| isoweek_2 | baseline | 10 | 10/10 | 0 | 0 | 6.3 | 1,624 (100-4,099) |
| isin_1 | baseline | 10 | 6/10 | 0 | 0 | 8.9 | 2,286 (385-5,185) |
| isin_2 | baseline | 10 | 10/10 | 0 | 0 | 8.3 | 3,680 (3,064-5,115) |
| sessions_1 | baseline | 10 | 10/10 | 0 | 0 | 1.2 | 2,890 (2,404-3,266) |
| sessions_2 | baseline | 10 | 10/10 | 0 | 0 | 1.3 | 2,885 (2,178-3,924) |
| gstin_1 | tools | 10 | 10/10 | 0 | 0 | 4.2 | 508 (400-990) |
| gstin_2 | tools | 10 | 10/10 | 0 | 0 | 5.1 | 272 (138-606) |
| isoweek_1 | tools | 10 | 10/10 | 5 | 3 | 4.7 | 453 (350-764) |
| isoweek_2 | tools | 10 | 10/10 | 0 | 0 | 2.7 | 166 (166-166) |
| isin_1 | tools | 10 | 10/10 | 0 | 0 | 4.1 | 988 (599-1,437) |
| isin_2 | tools | 10 | 10/10 | 0 | 0 | 6.5 | 250 (210-610) |
| sessions_1 | tools | 10 | 10/10 | 0 | 0 | 4.9 | 1,648 (1,537-1,698) |
| sessions_2 | tools | 10 | 10/10 | 0 | 0 | 5.1 | 1,288 (1,202-1,403) |
<!-- GENERATED:bench-tasks:END -->

## Dove sbaglia

I fallimenti sono elencati, non nascosti e non rilanciati finché passano. Ogni
esecuzione qui sotto è in `results/runs/` con il suo record completo.

Ogni fallimento in queste esecuzioni è un fallimento del **baseline**, e una traccia
spiega lo schema meglio della tabella. Il baseline non sbaglia il metodo — calcola
correttamente la settimana ISO — ma spende un round intero per ogni passaggio aritmetico,
e finisce i round prima di arrivare alla risposta. Uno strumento scritto fa tutti e
quattro gli input in un round solo.

<!-- GENERATED:bench-trace:START -->
`core__baseline__isoweek_1__r14` - isoweek_1, baseline, finita *unfinished* dopo 10 round:

```
r1 calc(expression='0') -> '0'
r2 calc(expression='(2027 + 2027//4 - 2027//100 + 2027//400) % 7') -> '5'
r3 calc(expression='31+28+31+30+31+30+31+7') -> '219'
r4 calc(expression='(219 + 4) // 7') -> '31'
r5 calc(expression='(5 + 219 - 1) % 7') -> '6'
r6 calc(expression='31+28+31+30+31+30+31+31+28') -> '271'
r7 calc(expression='(271 + 7 - 5) // 7') -> '39'
r8 calc(expression='31+16') -> '47'
r9 calc(expression='(47 + 2) // 7') -> '7'
r10 calc(expression='31+28+31+30+31+11') -> '162'
r10 out of rounds
```
<!-- GENERATED:bench-trace:END -->

<!-- GENERATED:bench-failures:START -->
| run | task | condizione | cosa è successo | risposta data |
|---|---|---|---|---|
| `core__baseline__gstin_1__r02` | gstin_1 | baseline | unfinished | `-` |
| `core__baseline__gstin_1__r05` | gstin_1 | baseline | unfinished | `-` |
| `core__baseline__gstin_2__r01` | gstin_2 | baseline | unfinished | `-` |
| `core__baseline__gstin_2__r04` | gstin_2 | baseline | unfinished | `-` |
| `core__baseline__isoweek_1__r01` | isoweek_1 | baseline | unfinished | `-` |
| `core__baseline__isoweek_1__r02` | isoweek_1 | baseline | unfinished | `-` |
| `core__baseline__isoweek_1__r04` | isoweek_1 | baseline | unfinished | `-` |
| `core__baseline__isoweek_1__r05` | isoweek_1 | baseline | unfinished | `-` |
| `core__baseline__isoweek_1__r06` | isoweek_1 | baseline | unfinished | `-` |
| `core__baseline__isoweek_1__r09` | isoweek_1 | baseline | unfinished | `-` |
| `finance__baseline__isin_1__r03` | isin_1 | baseline | wrong | `810566` |
| `finance__baseline__isin_1__r05` | isin_1 | baseline | wrong | `019517` |
| `finance__baseline__isin_1__r08` | isin_1 | baseline | unfinished | `-` |
| `finance__baseline__isin_1__r09` | isin_1 | baseline | unfinished | `-` |
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
| piattaforma | tetto memoria | attacchi | contenuti | dalla guardia | dal sandbox | limiti dichiarati | fughe non dichiarate |
|---|---|---|---|---|---|---|---|
| Windows | none (Windows: only the watchdog timeout) | 42 | 41/42 | 27 | 14 | memory bomb (4 GB) | none |
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
