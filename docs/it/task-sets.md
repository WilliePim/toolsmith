# Set di compiti

*Italiano · [English](../en/task-sets.md)*

Le famiglie di compiti sono il **percorso di prova**, non il prodotto. Il prodotto è la macchina — il ciclo, la guardia, il sandbox, il registro. Ogni famiglia è sagomata come un cono di un percorso d'esame, messa per sollecitare una parte di quella macchina.

Perché una famiglia si guadagni il posto, il suo compito deve:

| Il compito deve… | così da poter testare… |
|---|---|
| essere servito male da `calc`/`today` | che l'agente decida di **scrivere uno strumento** |
| enunciare la regola + un esempio svolto | che il modello sappia scrivere lo strumento **e i propri test** |
| avere una sola risposta esatta | la **valutazione automatica** (corretto / sbagliato) |
| nascondere un caso limite solo negli input riservati | che il **controllo nascosto** colga uno strumento che passa i propri test ma è sbagliato |
| venire in coppie (`_1`, `_2`) | il **riuso**: il secondo compito chiama lo strumento salvato |

## I due set

`core` (`data/tasks.json`) è fedele al tutorial. `finance` (`data/tasks_finance.json`) è un secondo set, scelto con `--set finance`, che mostra la stessa macchina gestire regole diverse.

### `core` — GSTIN e settimana ISO

- **Carattere di controllo GSTIN** è una trappola *aritmetica*: un checksum base-36 su 14 caratteri. Il caso limite nascosto è un carattere di controllo che esce come **cifra**, non lettera — uno strumento che mappa sempre attraverso la tabella delle lettere passa i suoi test visibili a risposta-lettera e fallisce lì.
- **Etichetta di settimana ISO** è una trappola *concettuale*. Il naïf `f"{d.year}-W{week}"` passa ogni compito visibile ma fallisce su una data come 2024-12-30, la cui settimana ISO è `2025-W01-1` perché quella settimana appartiene al 2025. Il controllo nascosto lo coglie; il modello riceve solo l'indizio e ripara lo strumento con `isocalendar()`. Quel ciclo scrivi → rifiuta → ripara è il momento chiave del progetto.

### `finance` — ISIN e sedute di borsa

- **Cifra di controllo ISIN**: ogni lettera diventa due cifre, quindi una lettera nel corpo sposta il raddoppio di Luhn per tutto ciò che sta alla sua sinistra. I codici visibili hanno solo cifre; quelli nascosti mettono lettere in posizioni sia pari sia dispari del corpo, così un errore nel conteggio delle posizioni non passa per fortuna. Le risposte sono verificate con `python-stdnum`.
- **Seduta di borsa**: l'n-esima seduta dopo una data, dato l'elenco delle chiusure del mercato **come parametro**. Ogni input di Stoccolma visibile cade su una festività USA che è una normale seduta a Stoccolma, quindi uno strumento che usa l'elenco NYSE sbaglia tutti e sei. Un batch nascosto passa l'elenco di Stoccolma *durante il task NYSE*, quindi uno strumento che ignora il suo argomento `closures` è rifiutato alla registrazione. Le risposte sono verificate con `exchange-calendars`.

Gli elenchi confermati completi sono in [design.md](design.md), Appendice A.

## Lo schema del file di compiti

```json
{ "set": "core",
  "generated_by": "src/taskgen.py",
  "families": [{
    "family": "gstin",
    "label": "GSTIN check character",
    "contract": "la regola + un esempio svolto, byte-identico in ogni compito",
    "returns": "come si unisce la risposta dell'intero compito",
    "tool_params": {"prefix": {"type": "string", "description": "..."}},
    "tool_returns": "cosa restituisce una chiamata run()",
    "joiner": "",
    "holdout_hint": "some have a check character that is a digit ...",
    "tasks":   [{"id": "gstin_1", "prompt": "...", "calls": [{"prefix": "16TEUYJ4263R1Z"}], "answer": "KXMS"}],
    "holdout": [{"calls": [{"prefix": "..."}], "expect": "..."}]
  }]
}
```

- **`contract`** è byte-identico tra i compiti di una famiglia — è ciò che rende uno strumento riusabile. Se la formulazione slittasse tra il compito uno e il due, un conteggio di "riuso" misurerebbe lo slittamento del prompt, non una cassetta degli attrezzi.
- **`tool_params`** dichiara la firma esatta di `run()` che lo smith impone. È il motivo per cui il controllo nascosto può chiamare uno strumento con input nascosti, e costringe lo strumento delle sedute a *ricevere* il suo elenco di chiusure invece di scriverlo dentro.
- **`calls`** sono gli input in forma macchina. Non sono mai mostrati al modello — il modello legge il prompt. Guidano la valutazione e il controllo nascosto.
- **`holdout`** i batch non lasciano mai la macchina. Un fallimento è riportato solo come conteggio più `holdout_hint`.

## Aggiungere un set

Un nuovo set è un nuovo file più una riga in `config.TASK_SETS`. Il file core non cambia mai. Questo tiene pulite tre cose:

1. Le dipendenze pesanti del solo generatore (il set finance tira dentro pandas via `exchange-calendars`) vivono in un gruppo `taskgen` separato e non raggiungono mai l'agente.
2. Chi legge vede un file e un generatore per set.
3. Gli id delle famiglie devono essere unici tra i set; il loader lo controlla.

Per aggiungerne uno:

1. Scrivi `src/taskgen_<nome>.py` che costruisce il file da codice di riferimento — mai risposte battute a mano. Verifica con una libreria esterna dove esiste.
2. Aggiungi `"<nome>": DATA_DIR / "tasks_<nome>.json"` a `config.TASK_SETS`.
3. Generalo, committa il JSON, ed esegui `--set <nome>`.

Entrambi i generatori supportano `--check` (confronta il file committato byte per byte con una nuova costruzione), così un file di compiti non può mai slittare in silenzio dal codice che l'ha prodotto.
