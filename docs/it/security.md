# Sicurezza

*Italiano · [English](../en/security.md)*

Uno strumento generato è codice scritto dal modello. Due livelli indipendenti stanno tra quel codice e la tua macchina. Nessuno dei due si fida dell'altro, e `redteam.py` prova ciascuno da solo — senza chiamate API.

## Livello 1 — la guardia statica (`guard.py`)

La guardia legge il sorgente come albero sintattico e lo rifiuta *prima che qualcosa giri*, restituendo la prima violazione come `line N: reason`. Vede **nomi**, non valori, quindi è grossolana e **default-deny**: un costrutto che nessuno ha previsto viene rifiutato, perché un rifiuto costa un turno di riparazione mentre una svista costa una risposta sbagliata o peggio.

Rifiuta:

- **Struttura** — qualunque cosa tranne un `run(<parametri dichiarati>)` di primo livello; `*args`/`**kwargs`; istruzioni di primo livello diverse da import, def, classi, assegnazioni e docstring; qualunque `async`.
- **Import** — qualunque modulo fuori dall'allowlist (`math`, `datetime`, `re`, `decimal`, `json`, `itertools`, `functools`, `collections`, `string`, `calendar`, `typing`); import relativi e con `*`.
- **Builtin pericolosi** — `eval`, `exec`, `compile`, `open`, `__import__`, la famiglia `getattr`/`setattr`, `globals`/`locals`/`vars`/`dir`, `input`, `breakpoint`, `memoryview`, e le eccezioni base `BaseException`/`SystemExit`/`KeyboardInterrupt`/`GeneratorExit`.
- **Attraversamento dunder** — qualunque `__dunder__` fuori da una piccola allowlist, bloccando `__class__`, `__subclasses__`, `__globals__`, `__dict__`, `__mro__`, `__bases__`, `__builtins__`, `__reduce__`.
- **Pivot e privati** — attributi che raggiungono l'interprete o un frame (`sys`, `modules`, `f_globals`, `gi_frame`, `tb_frame`, ...), anche via alias come `typing.sys`; attributi privati (`_x`) se non su `self`/`cls`, il che blocca `collections._sys`.
- **Attraversamento via stringa di formato** — `"{0.__class__}".format(x)` raggiunge un attributo senza alcun `getattr`; un template letterale i cui campi attraversano un `.` o `[` è rifiutato, e un ricevente `.format` non letterale del tutto.
- **Ingoiare il segnale del sandbox** — un `except:` nudo, un `except` il cui tipo è un'espressione, e `return`/`break`/`continue` dentro `finally`.
- **Il prefisso riservato** — qualunque nome che inizia con `_TS_`.

## Livello 2 — il sandbox a runtime (`sandbox.py` + `protocol.py`)

Il sandbox esegue lo strumento in un processo separato che non può influenzare:

- **`python -I -S -B -X utf8`** — isolato (niente ambiente, cartella di lavoro fuori dal percorso), niente site-packages (solo la libreria standard è leggibile), niente scritture `.pyc`, I/O in UTF-8.
- **Un ambiente ripulito** — solo `SYSTEMROOT` e un paio di variabili innocue raggiungono il figlio. **Nessuna chiave API.**
- **Una cartella temporanea nuova** come cartella di lavoro, cancellata dopo l'esecuzione.
- **Un watchdog** che controlla ogni 20 ms e uccide il figlio dopo 10 secondi o 256 KB di output.
- **Su POSIX**, anche limiti rigidi `RLIMIT_CPU` e `RLIMIT_AS` (1 GB).

Dentro il figlio, un **audit hook di Python** installato prima del codice dello strumento nega un insieme fisso di eventi: `os.system`, avvio di processi, socket, `ctypes`, accesso al registro, e ogni scrittura su filesystem. Le *letture* di file sono permesse solo dentro la libreria standard e lo script stesso, con i percorsi normalizzati prima così che l'attraversamento con `..` e i trucchi sulle maiuscole di Windows non possano allargarlo.

Due decisioni di progetto si sorreggono a vicenda. L'hook solleva `_TS_Violation`, che deriva da **`BaseException`** — così `except Exception: pass` non può ingoiarlo — e la guardia vieta l'`except:` nudo che è l'unico altro modo per catturarlo. Nessuno dei due da solo basta.

## La prova (`redteam.py`)

```bash
uv run python -m src.redteam
```

36 attacchi e 7 benigni quasi-sospetti, eseguiti senza chiamate API:

- **27 attacchi alla guardia** — import vietati e con alias, `__import__`, `eval`/`exec`/`open`/`getattr`, attraversamento dunder e mro, pivot di modulo via alias e privati, camminata sui frame, attraversamento via stringa di formato, gli ingoiatori d'eccezione, il prefisso riservato, un import con `*`, un `eval` in annotazione.
- **9 attacchi al sandbox** — un ciclo infinito, un'alluvione di stampe, ricorsione profonda, `sys.exit()` dentro `run`, un ritorno non serializzabile, e `os.system`/scrittura-file/socket/`os.listdir` **inviati dritti al sandbox con la guardia saltata**, per dimostrare che l'audit hook regge da solo.
- **7 strumenti benigni** che devono passare e restituire il valore giusto — un helper chiamato `json`, `Counter.most_common()` (il suo import pigro di `heapq`), un contesto `decimal`, una classe con `__init__`, `try/except ValueError`, `date.fromisoformat().isocalendar()`, e un matcher `re` + `string`.

La suite esce con errore se un attacco passa o un benigno è rifiutato.

## Limiti noti

È una barriera solida per una demo, non la pretesa di un isolamento perfetto.

- **Memoria su Windows.** Non c'è tetto allo spazio di indirizzamento su Windows; uno strumento può allocare finché il timeout lo uccide. Un limite di memoria via Job Object è la correzione, elencata in "cosa costruire dopo".
- **Letture sotto l'installazione di Python.** Con `-S`, il percorso del figlio include la cartella dell'interprete, quindi i file lì sono leggibili. Nulla di sensibile vi risiede, ma è una superficie di lettura più ampia della sola libreria standard.
- **Gli audit hook sono una barriera a livello Python.** Fermano gli eventi su cui sono agganciati; un'estensione nativa che aggirasse l'interprete non ne farebbe scattare uno — ed è proprio per questo che `ctypes` e affini sono nella deny list e fuori dall'allowlist degli import.

Non puntarlo su input non fidati su una macchina che non puoi permetterti di perdere.
