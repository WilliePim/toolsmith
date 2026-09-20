# toolsmith

*Italiano · [English](README.md)*

**Un agente che scrive, verifica e riusa i propri strumenti Python — e un'impalcatura di
misura che dice quanto questo valga davvero.**

Quando un compito applica una regola su molti input, l'agente smette di risolverlo dentro
la conversazione e si scrive un piccolo programma. Quel programma viene controllato,
eseguito in sandbox, salvato su disco, e diventa uno strumento disponibile già dal round
successivo.

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

## Il risultato

Stesso modello, stessi compiti, 10 ripetizioni ciascuno. L'unica differenza è se l'agente
può scrivere strumenti.

<!-- GENERATED:bench-conditions:START -->
| condizione | run | risolti | accuratezza | token in (media) | token out (media) | costo totale (USD) |
|---|---|---|---|---|---|---|
| tools | 80 | 80 | 100% | 7,795 | 697 | $0.68 |
| baseline | 80 | 66 | 82% | 12,659 | 2,916 | $1.63 |
<!-- GENERATED:bench-conditions:END -->

<!-- GENERATED:bench-header:START -->
Modello **gemini-3.8-flash**, temperatura *provider default (unset)*, commit `f292c9f+dirty`, eseguito il 2026-09-19. 10 ripetizioni per compito e condizione: 160 esecuzioni, 289,046 token in uscita, costo totale $2.31. Errori del provider rilanciati: 0. Escluse dalle medie 5 esecuzioni fuori disegno, raccolte dopo per catturare una traccia.
<!-- GENERATED:bench-header:END -->

> **Questa è la dimostrazione di un meccanismo, non un benchmark.** Esegue 8 compiti in
> 4 famiglie: abbastanza per mostrare che il ciclo, la guardia, il sandbox e il riuso
> funzionano, e ben lontano dal permettere generalizzazioni su agenti, modelli o tipi di
> compito.
>
> Ogni cifra in questo file è generata da `src/report.py` dai file in `results/`; nessuna
> è scritta a mano. Si riproducono con
> `uv run python -m src.bench --repeats 10 && uv run python -m src.report`.

## Come funziona

L'agente parte con la cassetta degli attrezzi di un assistente qualunque: una calcolatrice
e la data di oggi. Sono deliberatamente *quasi* giusti — un checksum è aritmetica, una
settimana ISO è una data — e nessuno dei due risolve davvero il suo compito, perché `calc`
valuta una sola espressione per round. È quello scarto a trasformare "scrivi uno
strumento" in una decisione invece che in un passaggio da copione.

Uno strumento scritto dal modello supera quattro cancelli prima di poter essere chiamato:

| Cancello | Cosa fa | Costo di un rifiuto |
|---|---|---|
| **1. Specifica** | lo strumento deve prendere i parametri esatti della famiglia, con almeno due test | un turno di riparazione |
| **2. Guardia statica** | legge il sorgente come AST e rifiuta nomi, import e costrutti non sicuri | un turno di riparazione |
| **3. Sandbox** | lo esegue isolato contro i test del modello **e contro input che il modello non vede mai** | un turno di riparazione |
| **4. Registro** | lo salva come `generated/<nome>.py` + `.json`, ricontrollato a ogni caricamento | — |

Il terzo è quello interessante: uno strumento che supera i propri test può essere
comunque sottilmente sbagliato, ed è esattamente ciò che il controllo nascosto esiste per
cogliere. Al modello viene detto solo *quanti* lotti nascosti sono falliti, più un
indizio — mai gli input, i valori attesi, o un messaggio d'errore che potrebbe
rimandarne indietro uno.

Poi **la riga**: l'array degli strumenti viene ricostruito *dentro* il ciclo dei round,
quindi uno strumento scritto al round *N* è chiamabile al round *N+1*, a conversazione in
corso.

Diagrammi e dettaglio modulo per modulo: [docs/it/architecture.md](docs/it/architecture.md).

## Sicurezza, misurata

Entrambi i livelli sono provati da una suite adversariale che **non richiede chiavi API**:

```bash
uv run python -m src.redteam --json results/sandbox_$(uname -s).json
```

Gli attacchi coprono lettura fuori dalla cartella permessa, scrittura su disco, accesso
alla rete, avvio di processi, cicli infiniti, uso eccessivo di memoria, import vietati,
fughe dall'interprete, e l'ingoiare la violazione del sandbox. Gli attacchi al runtime
sono inviati **oltre la guardia di proposito**, per dimostrare che l'audit hook regge da
solo.

<!-- GENERATED:sandbox:START -->
| piattaforma | tetto memoria | attacchi | contenuti | dalla guardia | dal sandbox | limiti dichiarati | fughe non dichiarate |
|---|---|---|---|---|---|---|---|
| Windows | none (Windows: only the watchdog timeout) | 42 | 41/42 | 27 | 14 | memory bomb (4 GB) | none |
<!-- GENERATED:sandbox:END -->

**Un attacco non viene contenuto, ed è dichiarato invece che corretto in silenzio.** Su
Windows una singola allocazione da 4 GB riesce: non c'è tetto allo spazio di
indirizzamento e finisce entro il timeout del watchdog. Su Linux il sandbox imposta
`RLIMIT_AS` e lo stesso attacco è rifiutato. La suite fallisce su qualsiasi fuga *non
dichiarata*; un limite documentato viene riportato, così il segnale resta utile.
Dettagli e altri limiti: [docs/it/security.md](docs/it/security.md).

## Dove sbaglia

I fallimenti sono elencati, non nascosti e non rilanciati finché passano.

Ogni fallimento in queste esecuzioni è un fallimento del **baseline**, e una traccia
spiega lo schema meglio della tabella: il baseline non sbaglia il metodo — calcola
correttamente la settimana ISO — ma spende un round intero per ogni passaggio aritmetico
e finisce i round. Uno strumento scritto fa tutti e quattro gli input in un round solo.

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

## Avvio rapido

Python 3.12+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync
cp .env.example .env          # incolla una chiave Gemini da aistudio.google.com/apikey
```

```bash
uv run python -m src.main redteam      # i due livelli di sicurezza, senza chiave
uv run python -m src.main run gstin_1  # risolve un compito
uv run python -m src.main run --all --set finance
uv run python -m src.main tools        # cosa ha scritto l'agente
uv run python -m src.main show gstin_check_char
```

Imposta `PROVIDER=claude` e `ANTHROPIC_API_KEY` per girare su Claude: l'adattatore è
scritto e verificato offline, e il livello del modello è neutrale rispetto al provider.

## I compiti

Due set, ciascuno con due famiglie, ogni famiglia con due compiti perché il secondo riusi
lo strumento del primo. Ogni famiglia nasconde un caso limite solo negli input riservati.

| Set | Famiglia | Regola | Caso limite nascosto |
|---|---|---|---|
| `core` | carattere di controllo GSTIN | checksum base-36 su 14 caratteri | un carattere di controllo che è una cifra, non una lettera |
| `core` | etichetta settimana ISO | `YYYY-Www-D` da una data | una data la cui settimana ISO appartiene all'anno vicino |
| `finance` | cifra di controllo ISIN | lettere → cifre, poi Luhn | le lettere nel corpo spostano il raddoppio di Luhn |
| `finance` | seduta di borsa | l'n-esima seduta dopo una data | un giorno di chiusura dentro l'intervallo |

Entrambi i file dei compiti sono **generati da codice di riferimento**, mai battuti a
mano: `src/taskgen.py` e `src/taskgen_finance.py`, quest'ultimo verificato con
`python-stdnum` ed `exchange-calendars`. `--check` dimostra che il file committato
combacia ancora con il suo generatore. Perché queste famiglie, e come aggiungerne:
[docs/it/task-sets.md](docs/it/task-sets.md).

## Metodo

Il confronto vale solo se il baseline è leale. **Baseline** è lo stesso modello, gli
stessi compiti e lo stesso system prompt con *solo* le righe sulla scrittura degli
strumenti rimosse: un prompt che descrivesse uno strumento che quella condizione non può
usare la penalizzerebbe, invece di misurarla.

<details>
<summary>La differenza esatta fra i due prompt (generata)</summary>

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
</details>

Ogni ripetizione parte da una **cassetta degli attrezzi vuota e isolata**, così "il primo
compito scrive, il secondo riusa" resta ciò che si misura. Gli errori del provider (429,
5xx, rete) vengono rilanciati con attesa crescente e contati a parte; tutto ciò che ha
fatto l'agente — una risposta sbagliata, uno strumento respinto, i round esauriti — è
registrato com'è accaduto. Ogni esecuzione salva modello, temperatura, hash del prompt e
commit del codice. Il runner è riprendibile, così una quota giornaliera esaurita si può
aspettare.

### Riuso: quanto costa il secondo compito di una famiglia

<!-- GENERATED:bench-reuse:START -->
| famiglia | coppie | token out primo task (media) | secondo (media) | risparmio medio | coppia peggiore | coppia migliore |
|---|---|---|---|---|---|---|
| gstin | 10 | 508 | 272 | 1.8x in meno | 1.4x in piu | 3.3x in meno |
| isin | 10 | 988 | 250 | 3.7x in meno | 1.6x in meno | 6.8x in meno |
| isoweek | 10 | 453 | 166 | 2.5x in meno | 2.1x in meno | 4.6x in meno |
| sessions | 10 | 1,648 | 1,288 | 1.3x in meno | 1.2x in meno | 1.4x in meno |
<!-- GENERATED:bench-reuse:END -->

Il riuso non è denaro gratis, e la tabella lo dice: per `sessions` il risparmio è modesto,
perché ogni chiamata porta comunque l'elenco delle festività della borsa, e per `gstin`
almeno una ripetizione ha speso *di più* sul secondo compito che sul primo. Ciò che regge
in tutte e quattro le famiglie è l'accuratezza, non uno sconto fisso.

### Dove i quattro cancelli sono scattati davvero

<!-- GENERATED:bench-refusals:START -->
| cancello che ha respinto uno strumento | volte |
|---|---|
| own_tests | 3 |
| tests | 2 |

45 tentativi di scrittura in totale; 5 respinti e 3 esecuzioni hanno poi registrato uno strumento riparato.
<!-- GENERATED:bench-refusals:END -->

Va letta con rigore: i rifiuti vengono dai test *propri* del modello e dal controllo della
specifica, e **il controllo su input nascosti non ha mai dovuto respingere uno strumento
in queste esecuzioni** — ha girato ogni volta e ha approvato ogni volta. Il suo valore è
quindi dimostrato per costruzione, non da questo campione: `uv run python -m src.smith`
costruisce uno strumento GSTIN volutamente sbagliato che supera i propri test, e mostra il
controllo nascosto che lo coglie rivelando solo un conteggio e un indizio.

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

## Cosa viene dal riferimento, e cosa è nuovo qui

Il progetto segue un tutorial sulla costruzione di un agente che estende sé stesso, la cui
seconda metà era dietro un paywall. *Riferimento: (segnaposto — da inserire).* Nulla di
esso è riprodotto qui: né testo, né figure, né tabelle — solo una descrizione, con parole
mie, di quali idee venissero dalla metà leggibile.

**Dal riferimento, reimplementato:** la forma generale — ricostruire la lista degli
strumenti dentro il ciclo dei round, dividere la sicurezza fra una lettura statica e
un'esecuzione in sandbox, verificare uno strumento generato contro input che il modello
non può vedere, tenere gli strumenti come file semplici, e partire da due strumenti
deliberatamente quasi-pertinenti. La famiglia GSTIN e il suo esempio svolto vengono da lì;
il file dei compiti è rigenerato da un'implementazione di riferimento, perché la risposta
d'esempio del riferimento per un input nascosto non tornava.

**Nuovo qui:** ogni modulo dopo la metà — l'esecutore del sandbox e il suo watchdog, la
guardia statica, il registro, il percorso scrivi-controlla-registra, i prompt, il ciclo
dell'agente, il corpus di red-team e la CLI. Inoltre: un livello del modello neutrale con
adattatori Gemini e Claude; un nonce per esecuzione perché uno strumento non possa
falsificare i propri risultati; il precaricamento dei moduli perché l'audit hook non rompa
gli import ordinari; la normalizzazione dei percorsi nella regola di apertura file;
un'interfaccia degli strumenti per famiglia che permette al controllo nascosto di chiamare
uno strumento con input nascosti; un secondo set di compiti verificato con librerie
esterne; e l'intera impalcatura di misura da cui vengono i numeri di questo README.

## Struttura

```
src/
  config.py             ogni impostazione in un unico posto
  tools.py              i due strumenti iniziali
  llm.py + providers/   una porta verso Gemini o Claude; non solleva mai
  protocol.py           preambolo + sorgente + footer, e lettura dei risultati
  sandbox.py            il sottoprocesso blindato e il suo watchdog
  guard.py              il livello statico (AST)
  registry.py           la cassetta degli attrezzi che cresce, come file
  smith.py              scrivi, controlla, registra
  tasks.py, prompts.py  compiti tipizzati e ciò che viene detto al modello
  agent.py              il ciclo dei round e "la riga"
  attacks.py, redteam.py  la prova adversariale
  taskgen*.py           costruiscono i file dei compiti da codice di riferimento
  bench.py, report.py   l'impalcatura di misura dietro ogni numero qui
  main.py               la riga di comando
results/                record delle esecuzioni, cassette, prompt, summary.json
docs/{en,it}/           architettura, sicurezza, set di compiti, progetto, diario
```

Ogni modulo ha un'autoverifica `__main__`: `uv run python -m src.<modulo>`.
La CI le esegue, insieme ai due generatori e alla suite di red-team su Linux.

## Per approfondire

- [docs/it/build-journal.md](docs/it/build-journal.md) — ogni passo, perché è stato costruito così, e gli errori lungo la strada, incluse due affermazioni che i dati hanno ritirato.
- [docs/it/architecture.md](docs/it/architecture.md) · [security.md](docs/it/security.md) · [task-sets.md](docs/it/task-sets.md) · [design.md](docs/it/design.md)

## Nota di sicurezza

Il sandbox nega accessi a sistema operativo, filesystem e rete tramite un audit hook di
Python ed esegue ogni strumento in un sottoprocesso isolato con ambiente ripulito (nessuna
chiave API), timeout e tetto sull'output; su POSIX imposta anche limiti rigidi di CPU e
memoria. È una barriera solida per una demo, non la pretesa di un isolamento perfetto —
vedi il limite misurato qui sopra. Non puntarlo su input non fidati su una macchina che
non puoi permetterti di perdere.
