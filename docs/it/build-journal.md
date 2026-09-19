# Diario di costruzione

*Italiano · [English](../en/build-journal.md)*

Questa è la storia di come è stato costruito toolsmith, un passo alla volta: cosa ha fatto ogni passo, **perché** è stato fatto così, e gli errori commessi lungo la strada. È scritto per chi vuole imparare come si mette insieme un agente del genere, non solo cosa contiene il codice finale. Ogni passo si chiude con il comando che lo verifica.

Leggilo dall'inizio alla fine, oppure salta al modulo che stai guardando in `src/`.

---

## Prima di ogni riga di codice: leggere il problema

Il progetto segue un tutorial, *"Build an Agent That Writes Its Own Tools"*. Solo la prima metà era leggibile; il resto era dietro un paywall. La prima decisione è stata quindi **non tentare di recuperare il testo nascosto**, ma progettare i moduli mancanti da ciò che la prima metà fissa: il diagramma dell'architettura, l'indice e i vincoli dichiarati in prosa.

Tre cose sono state decise prima di scrivere una riga:

- **Il checksum andava verificato, non creduto.** L'esempio GSTIN del tutorial dichiara due risposte: `CW` (un esempio svolto) e `KXMS` (il primo compito). Uno script di dieci righe ha riprodotto entrambe, fissando l'algoritmo esatto. L'*esempio* di input nascosto del tutorial (`29AAGCB7383J1Z → ISUQ`) si è rivelato solo illustrativo: il vero carattere di controllo è `4`. Lezione: **gli esempi di una specifica possono essere sbagliati; un'implementazione di riferimento che puoi eseguire è la vera chiave delle risposte.** Ogni file di compiti in questo progetto è generato da codice di riferimento, mai scritto a mano.
- **Niente Groq.** Il tutorial parla con Groq. Questa costruzione è neutrale rispetto al provider, con un adattatore Gemini (il default) e uno Claude. Quella scelta si è propagata in tutto il livello del modello.
- **Il codice visibile aveva lacune di sicurezza da correggere.** Leggendo con attenzione la guardia e il sandbox del tutorial sono emersi diversi buchi — `except BaseException` che ingoia il segnale stesso del sandbox, un controllo di percorso ingannato da `..` e dalle maiuscole di Windows, l'attraversamento di attributi via stringa di formato, i pivot di modulo come `typing.sys`. Sono diventati il lavoro di irrobustimento dei passi 6–8.

C'è stato anche un giro di domande in linguaggio semplice che vale la pena registrare, perché sono il modello mentale su cui poggia tutto il progetto:

- **Uno "strumento" ha due metà.** Una *descrizione* JSON (ciò che il modello legge) e *codice* Python (ciò che il nostro programma esegue). Il modello emette sempre e solo JSON che chiede uno strumento per nome; non esegue mai nulla.
- **È un ciclo, non ricorsione.** Il modello è senza stato. A ogni round *il nostro* programma rispedisce l'intera conversazione, il modello risponde con chiamate a strumenti, noi le eseguiamo e aggiungiamo i risultati, e comincia il round successivo.
- **Le famiglie di compiti sono il percorso di prova, non il prodotto.** GSTIN e settimana ISO (e più tardi ISIN e sedute di borsa) sono i coni di un percorso d'esame: ciascuno è sagomato per sollecitare una parte della macchina.

---

## Passo 0 — Git

**Cosa.** Un `.gitignore` (`.env`, `.venv/`, `__pycache__/`, `generated/*.py|json` e il PDF del tutorial), un commit iniziale su `master`, poi `git switch -c develop` per tutto il lavoro.

**Perché.** Un branch ha bisogno di un commit da cui crescere, e il repo non ne aveva. Il `.gitignore` è venuto per primo perché questo progetto *scrive file da solo* e tiene una chiave API in `.env` — le due cose che meno vuoi committare per sbaglio.

**Verifica.** Prima del commit, `git status` mostrava solo `.gitignore`; il PDF, prima un file non tracciato, era sparito dall'elenco — prova che la regola funziona. Git su Windows stampa un innocuo avviso "LF sarà sostituito da CRLF" sui fine riga, risolto subito dopo.

---

## Passo 1 — Scaffold

**Cosa.** `uv init --bare` (solo un `pyproject.toml`, nessun file d'esempio da cancellare), Python fissato a 3.13 in locale ma `requires-python >= 3.12` così un lettore del portfolio con la 3.12 può eseguirlo. Quattro dipendenze: `anthropic`, `google-genai`, `python-dotenv`, `rich`. Cartelle `src/`, `data/`, `generated/`, `docs/en`, `docs/it`. Un `.env.example` (committato) che documenta ogni impostazione, e un `.env` reale (ignorato) per la chiave.

**Perché.** `uv.lock` registra le versioni esatte, così chi clona ottiene un'installazione identica. `generated/` riceve un `.gitkeep` perché la cartella esista in un clone anche se il contenuto è ignorato — una cartella vuota è invisibile a git.

Qui è nata una piccola ma importante abitudine: **`.gitattributes` con `* text=auto eol=lf`.** Normalizza i fine riga a LF nel repository qualunque sia il sistema operativo, così il repo è uguale ovunque e Git smette di avvisare su Windows.

**Verifica.** `uv run` ha importato i quattro pacchetti; Python 3.13.15; `git check-ignore .env` ha confermato che il file della chiave è ignorato.

---

## Passo 2 — `config.py`, ogni manopola in un posto

**Cosa.** Un modulo tiene i percorsi, il registro `TASK_SETS` (nome di un set → file), le impostazioni del provider, il budget dell'agente, i limiti del sandbox e l'allowlist degli import. `require_api_key()` fallisce subito con l'URL da cui prendere la chiave.

**Perché un file solo.** Quando un numero va cambiato, c'è un solo posto da guardare. È l'idea del tutorial, mantenuta.

**Decisioni da nominare.**

- `PROVIDER` è letto al momento della chiamata (un attributo di modulo), così il flag `--provider` della CLI può sovrascriverlo dopo.
- Il modello Gemini di default, `gemini-3.6-flash`, **non** è stato scelto a memoria. Un grep nel pacchetto `google-genai` *installato* mostra che i suoi stessi esempi usano quell'ID. È confermato sull'account reale al passo 5.
- Le manopole solo-Groq (token al minuto, un'aritmetica di prenotazione) sono state tolte. `MAX_ROUNDS = 10` è rimasto, col ragionamento del tutorial: tre strumenti rifiutati, il round che ne registra uno, il round che lo chiama, il round che risponde — sono già sei, e uno strumento a input singolo chiamato una volta per elemento ne aggiunge altri.
- Una affermazione del tutorial è stata **corretta**: là un commento dice che `uv run` su Windows non eredita l'ambiente della shell. Il vero motivo per usare `python-dotenv` è semplicemente che le chiavi stanno in un file, non nella shell. (Verificato: una `PROVIDER=claude` da shell batte davvero `.env`, perché `load_dotenv` non sovrascrive le variabili esistenti.)

**Verifica.** L'autoverifica stampa una tabella di impostazioni; `PROVIDER=claude` cambia il modello; `PROVIDER=groq` esce con 1 e "Unknown provider". Una scoperta utile: eseguire `python -m src.config` dalla radice del repo mette già la cartella corrente nel percorso di import, quindi il prefisso `PYTHONPATH=.` del tutorial qui è inutile.

---

## Passo 3 — `taskgen.py`, il set core da un riferimento

**Cosa.** Le implementazioni di riferimento `gstin_check()` e `iso_label()` sono la chiave delle risposte. Da esse il generatore costruisce due famiglie (GSTIN, settimana ISO), ciascuna con un contratto identico byte per byte, un esempio svolto, due compiti visibili, tre batch nascosti e un indizio. Il primo compito riusa gli input esatti del tutorial (risposta `KXMS`); il resto è con seme, così il file è riproducibile.

**Perché generato.** Perché l'esempio di input nascosto del tutorial era sbagliato. Un generatore con un'implementazione di riferimento non può contraddire sé stesso, e `--check` confronta il file committato byte per byte con una nuova costruzione.

**Un contrasto utile per dopo.** Il contratto GSTIN, tenuto verbatim dal tutorial, dice "il checksum GSTIN standard" e non enuncia mai il passo finale `(36 - s % 36) % 36` — si appoggia alla conoscenza del modello più l'esempio svolto. I contratti finance (passo 14) sono deliberatamente autosufficienti. Entrambi gli stili sono validi; la differenza vale la pena capirla.

**La lezione di questo passo riguarda il testare il test.** Il generatore ha un `validate()` che asserisce ogni proprietà promessa (esempi svolti, contratti identici, risposte che combaciano con la chiave, nessun caso limite visibile, almeno due limiti per batch nascosto). Per fidarmene, ho rotto il documento di proposito in quattro modi. Il primo tentativo "catturava" tutti e quattro — ma due erano catturati dal controllo *sbagliato* (un input riusato faceva scattare un'asserzione "input appare due volte" prima di quella voluta), e un'asserzione non aveva alcun messaggio. **Un controllo che scatta per il motivo sbagliato non è un test superato.** La correzione: input freschi per ogni mutazione, un messaggio su ogni asserzione, e un assert che sia scattato il messaggio *giusto*.

**Trappole incontrate.** Modificare una stringa Python con un heredoc di shell ha scritto un `\n` letterale nel sorgente e l'ha rotto — le modifiche multi-riga vanno fatte in un vero editor, non con `sed`. Ed eseguire uno script nella cartella temporanea di sistema falliva con `ModuleNotFoundError: src`, perché Python mette la cartella *dello script* nel percorso, non quella di lavoro; passare da stdin (`python - < file`) o `python -m` dalla radice risolve.

**Verifica.** `python -m src.taskgen` asserisce `CW` e `KXMS`, scrive il file, e una seconda esecuzione è byte-identica.

---

## Passo 4 — `tools.py`, i due strumenti iniziali

**Cosa.** `calc` (un valutatore aritmetico a AST ristretto) e `today`. `call()` non solleva mai — un fallimento è testo che il modello può leggere e riparare. Gli schemi usano una forma neutrale `{name, description, parameters}` che ogni adattatore avvolge.

**Il miglioramento sul tutorial** è una riga di pensiero: **"codice fidato" non è "input fidato".** `calc` gira nel processo dell'agente perché l'abbiamo scritto noi — ma il suo *argomento* viene dal modello. `9 ** 9 ** 9` è un intero con circa cento milioni di cifre; valutarlo bloccherebbe l'agente a lungo. Così `calc` limita la lunghezza dell'espressione e rifiuta una torre di esponenti prima di calcolarla. Il sandbox (più avanti) ci protegge dal *codice* del modello; i nostri strumenti devono comunque difendersi dagli *argomenti* del modello.

**Verifica.** `calc('(36 - 221 % 36) % 36') → 31`, la torre è rifiutata in meno di un decimo di secondo, argomenti sbagliati tornano come `ERROR: wrong arguments`.

---

## Passo 5 — `llm.py` e gli adattatori dei provider

**Cosa.** Una sola porta verso il modello. `providers/base.py` tiene forme neutrali: `ToolCall` (argomenti già interpretati), `ToolResult`, `Completion` (il cui campo `raw` porta il turno dell'assistente del provider) e `ProviderError` con un `kind` — `rate`, `busy`, `malformed`, `daily` o `fatal`. Il `generate()` di ogni adattatore solleva `ProviderError`; `llm.complete()` possiede la politica di ritentativo e **non solleva mai** — un limite di frequenza, una chiamata malformata, una quota giornaliera esaurita tornano tutti come un `Completion` con nome.

**La regola che ha guidato questo passo: mai scrivere chiamate SDK a memoria.** Entrambi i pacchetti erano cambiati, quindi ho ispezionato il codice *installato* — firme, campi, classi d'errore — prima di scrivere qualunque cosa.

- `google-genai` 2.24.0: `client.aio.models.generate_content(model, contents, config)`; dichiarazioni di funzione costruite da JSON schema; `thinking_level` per Gemini 3 ma un budget di token per Gemini 2.x; `FunctionCall` porta un `id`; l'SDK ritenta solo se passi le opzioni di ritentativo (quindi passo "un tentativo" esplicito, tenendo visibile ogni fallimento); `HttpOptions.timeout` è in **millisecondi**.
- `anthropic` 1.7.0: `messages.create` **non ha alcun parametro `temperature`** su Opus 5; `with_raw_response` ora richiede `await raw.parse()`; gli errori tipizzati includono `OverloadedError` (529); `beta.messages.create` porta il parametro `fallbacks`.

**Perché ogni adattatore possiede le sue forme di messaggio.** I modelli con pensiero di Gemini attaccano *firme di pensiero* alle parti della risposta, e i *blocchi di pensiero* di Claude vanno rimandati indietro immutati; una copia ricostruita del turno li perderebbe. Così ogni adattatore aggiunge l'oggetto-turno del modello verbatim. Claude vuole anche **tutti** i risultati degli strumenti di un turno in un solo messaggio utente — separarli gli insegna a smettere di fare chiamate in parallelo.

**La scala delle temperature sparisce.** Il tutorial ritenta una generazione malformata a temperature crescenti perché a temperatura 0 un ritentativo ridisegna il campione *identico*. Claude Opus 5 non ha la manopola della temperatura, e Gemini 3 è tarato per 1.0, quindi ogni ritentativo è già un nuovo campione. La politica di ritentativo resta; la scala delle temperature è superflua.

**Una sottigliezza nei limiti di frequenza.** Il 429 di Gemini porta dettagli strutturati. Un `quotaId` che contiene `PerDay` significa un limite *giornaliero* — ritentare è inutile per ore, quindi `complete()` si ferma con un messaggio chiaro ("si azzera a mezzanotte ora del Pacifico; un altro modello ha la sua quota"). Un limite al minuto invece aspetta il suggerimento del server, interpretato da un piccolo `duration()` che legge `"7.66s"`, `"650ms"` (i millisecondi provati prima dei minuti, altrimenti `650ms` sarebbe 650 minuti) e un numero secco di secondi.

**Verifica.** I controlli offline costruiscono oggetti SDK reali e asseriscono le forme: le parti di pensiero di Gemini escluse dal testo della risposta, gli id delle chiamate preservati, il Content restituito per identità; la richiesta di Claude senza temperatura, con strumenti stretti e un livello di sforzo, e un blocco di pensiero che sopravvive al giro. L'unico controllo dal vivo — forzare una piccola chiamata `echo_number(4021)` — gira solo quando c'è una chiave.

---

## Passo 6 — `protocol.py`, da sorgente a script eseguibile

**Cosa.** Uno strumento generato è solo testo. `build_script()` lo avvolge in un preambolo che blinda l'interprete e un footer che legge le chiamate da stdin (un oggetto JSON per riga) e stampa un risultato marcato per riga. `parse_lines()` rilegge quei risultati.

**Tre problemi che il progetto ha dovuto risolvere** — nessuno visibile nell'estratto del tutorial:

1. **Builtin oscurabili.** Il footer chiama `print`, `type`, `str`. Uno strumento che definisce il proprio `print` lo romperebbe. Così il footer importa `builtins` sotto un nome riservato e chiama `_TS_b.print`, `_TS_b.type`, e così via.
2. **Risultati falsificabili.** Uno strumento potrebbe semplicemente *stampare* una riga che sembra un risultato. Così il marcatore porta un nonce casuale per esecuzione; ogni riga senza è "output vagante" — tenuta, mai interpretata.
3. **Import contro l'audit hook.** L'hook nega `os.listdir`. Ma importare un *pacchetto* per la prima volta elenca la sua cartella, che è un `listdir` — quindi il primo `import json` dopo l'installazione dell'hook si schianterebbe. Un esperimento l'ha confermato: senza precaricamento, `import json` dopo l'hook ha buttato giù l'intero processo. La correzione è **precaricare ogni modulo permesso prima di installare l'hook** (un import in cache non genera alcun evento di audit).

**Irrobustire la regola sull'apertura di file.** I percorsi sono normalizzati (`abspath` + `normcase`) prima del controllo del prefisso. Un esperimento ha mostrato perché: `sys.path[-1] + "\..\..\..\..\Windows\win.ini"` comincia con un prefisso permesso *testualmente*, quindi senza normalizzazione sarebbe stato leggibile. Anche una chiamata in stile `os.open` con flag di scrittura ma senza stringa di modo è negata.

**Un bug del mio stesso test da ammettere.** Ho provato per primo l'idea del "marcatore ASCII stampabile" con un byte `\x1c` dentro un valore — ma il JSON vieta i caratteri di controllo grezzi, quindi `json.dumps` lo scappa e la trappola non è mai scattata. La vera trappola è `U+2028`, che `json.dumps(ensure_ascii=False)` lascia grezzo e `str.splitlines()` spezza (ma `split("\n")` no). Il test ora dimostra che `splitlines()` vede sei righe dove `split("\n")` ne vede cinque — che è esattamente perché il parser usa `split("\n")`.

**Verifica.** L'autoverifica compila l'intero script, conferma che l'hook viene prima dello strumento e gli import dopo, ed esercita i casi vagante/falsificato/mancante di `parse_lines()`.

---

## Passo 7 — `sandbox.py`, il livello a runtime

**Cosa.** `run_calls(source, calls)` scrive lo script in una cartella temporanea nuova e lo esegue come `python -I -S -B -X utf8`, con stdin che porta le chiamate e un watchdog che controlla l'orologio e la dimensione dell'output.

**Perché quei flag.** `-I` isola l'interprete (ignora le variabili d'ambiente, tiene la cartella di lavoro fuori dal percorso); `-S` toglie i site-packages così solo la libreria standard è leggibile, rinforzando l'allowlist; `-B` ferma le scritture `.pyc` su cui il divieto di scrittura si schianterebbe; `-X utf8` perché `-I` toglie la variabile di codifica.

**L'ambiente è ripulito.** Il figlio riceve solo `SYSTEMROOT` e un paio di variabili innocue — **nessuna chiave API.** `SYSTEMROOT` resta perché Windows ne ha bisogno per inizializzare i socket e `os.urandom`.

**Verifica.** Uno strumento benigno restituisce i suoi valori; un `while True` è ucciso dal watchdog; un'alluvione di stampe colpisce il tetto dell'output; e — con la guardia saltata di proposito — `os.system`, la lettura di `.env`, la scrittura di un file e l'apertura di un socket sono tutti negati dall'audit hook. Quest'ultima parte è il punto: i due livelli sono indipendenti, quindi il runtime regge anche se la guardia è aggirata.

---

## Passo 8 — `guard.py`, il livello statico

**Cosa.** `check(source, params)` interpreta il sorgente e restituisce la prima violazione come `"line N: reason"`, o `None`. Impone la struttura (esattamente un `run()` di primo livello con i parametri dichiarati, solo istruzioni innocue in cima, niente async), l'allowlist degli import, un insieme di builtin e attributi vietati, un'allowlist di dunder, attributi privati solo su `self`, i pivot di modulo raggiunti tramite alias, l'attraversamento via stringa di formato, e qualunque costrutto che possa ingoiare il `BaseException` del sandbox.

**Perché così severo, e perché default-deny.** La guardia vede nomi, non valori. Non può sapere che un ciclo non finisce mai — quello è compito del sandbox. Quindi rifiuta sul *nome* soltanto, e un costrutto a cui nessuno ha pensato viene respinto, perché un rifiuto costa un turno di riparazione mentre una svista costa una risposta sbagliata.

**Un buco vero, trovato qui, non solo un bug di test.** `"{0.__class__}".format(x)` raggiunge un attributo a runtime senza alcun `getattr` in vista. La mia prima regola segnalava `.format` solo su un ricevente *non letterale*, quindi una stringa letterale sfuggiva. La correzione interpreta il template con `string.Formatter().parse()` e rifiuta ogni campo che attraversa un `.` o `[`.

**Una lezione sui visitor dell'AST.** Per un attributo concatenato come `x.__class__.__bases__`, l'attributo *esterno* è visitato per primo, quindi il messaggio nomina `__bases__`, non `__class__`. Entrambi rifiutati; i test sono stati rilassati per asserire "not allowed" invece del nome interno.

**Verifica.** Sei campioni benigni passano (incluso `Counter.most_common`, una classe che usa `self._n`, `try/except ValueError`) e 23 attacchi sono rifiutati, ciascuno asserendo che il messaggio nomina il motivo. La prova adversariale completa è il passo successivo.

---

## Passo 9 — `attacks.py` e `redteam.py`, provare entrambi i livelli gratis

**Cosa.** Un corpus di 27 attacchi alla guardia, 9 al sandbox e 7 benigni quasi-sospetti. `redteam.py` li esegue tutti ed esce con errore se un attacco passa o un benigno è rifiutato. **Nessuna chiamata API** — questa è tutta la storia della sicurezza, provata gratis, su cui ogni passo successivo può appoggiarsi.

L'idea acuta qui: gli attacchi al sandbox includono i bersagli della guardia — `os.system`, scrivere un file, un socket, `os.listdir` — inviati **dritti al sandbox con la guardia saltata**, per dimostrare che l'audit hook regge da solo.

**Un bug nel mio stesso campione benigno.** Lo strumento "data" usava prima `__import__('datetime')` — che la guardia giustamente vieta. La correzione *era* la lezione voluta: chiama il parametro `date`, importa il *modulo* `datetime` (non `from datetime import date`), così il parametro non nasconde ciò che ti serve.

**Verifica.** 36 attacchi contenuti (27 dalla guardia, 9 dal sandbox), 7 strumenti benigni passano, uscita 0.

---

## Passo 10 — `registry.py`, una cassetta che cresce come file

**Cosa.** Ogni strumento è due file: `generated/<nome>.py` (un'intestazione più il sorgente) e `<nome>.json` (il suo schema, famiglia, set, test e uno sha256). `load_all()` riesegue la guardia e l'hash su ogni file e **salta uno manomesso o ora non sicuro**. `call()` gira sempre nel sandbox — il processo padre non importa mai uno strumento generato.

**Perché ricontrollare i nostri file.** Difesa in profondità. Un file generato su disco potrebbe essere modificato tra un'esecuzione e l'altra; l'hash lo coglie, e la guardia gira di nuovo nel caso le regole si siano irrigidite.

**Quattro bug, tutti colti dall'autoverifica** — che è esattamente a cosa serve un'autoverifica:

1. `RESERVED_PREFIX` vive in `protocol`, non in `config`.
2. L'hash era calcolato sul sorgente *senza* l'intestazione, ma il ricaricamento leggeva il file *con* essa — quindi ogni strumento sembrava manomesso. Correzione: hash sui byte esatti su disco.
3. Questo creava un rischio di doppia intestazione al ri-salvataggio; risolto togliendo l'intestazione al caricamento così il sorgente in memoria è sempre puro.
4. Una dataclass `slots=True` non ha `__dict__`, quindi `record_use` usa `dataclasses.replace`.

**Verifica.** Salva uno strumento, ricaricalo in un registro nuovo, chiamalo nel sandbox; manometti il `.py` e guardalo saltato con un avviso sull'hash. Il test gira in una cartella temporanea così la `generated/` del repo resta pulita.

---

## Passo 11 — `smith.py`, scrivi, controlla, registra

**Cosa.** `forge(spec, family, reg)` esegue i controlli in ordine, il più economico e rivelatore per primo: nome, parametri che combaciano esattamente con l'interfaccia della famiglia, almeno due test, la guardia statica, poi **un'unica esecuzione nel sandbox** su test propri e ogni chiamata nascosta.

**La regola sulla privacy è il fulcro dell'intero progetto.** Un test proprio fallito è riportato per intero — sono dati del modello stesso. Un batch nascosto fallito è riportato **solo come conteggio più l'indizio della famiglia**: niente input, niente valori attesi, e soprattutto nessun messaggio d'eccezione, perché un errore come `invalid literal … 'R'` rimanderebbe indietro un input nascosto. Il test asserisce che l'input limite e la sua risposta siano entrambi assenti dal messaggio di rifiuto.

**È qui che il punto del progetto atterra.** Uno strumento GSTIN sottilmente sbagliato — che mappa un valore di controllo sotto 10 attraverso la tabella delle lettere invece di lasciarlo una cifra — passa i propri test con risposte a lettera ma fallisce il caso nascosto a cifra. Riceve "fallito 1 su 1 controlli nascosti" e l'indizio, e si ripara. Lo strumento corretto si registra.

**Verifica.** Lo strumento corretto si registra; quello sbagliato si ferma alla fase nascosta con l'indizio e senza fuga di dati; i parametri sbagliati sono nominati; `import os` si ferma alla fase della guardia.

---

## Passo 12 — `tasks.py`, `prompts.py`, `agent.py`: il ciclo e la riga

**Cosa.** `tasks.py` trasforma un file di compiti in oggetti tipizzati, tenendo gli input nascosti fuori dai prompt. `prompts.py` tiene il system prompt indipendente dal compito (il contratto degli strumenti, e l'istruzione di ricavare a mano i risultati dei test dall'esempio svolto), la riga d'interfaccia costruita dai `tool_params` di una famiglia, e gli schemi di `write_tool`/`submit_answer`. `agent.py` esegue il ciclo.

**La riga.** A ogni round l'insieme degli strumenti è ricostruito: `tools.SCHEMAS + registry.schemas() + meta_schemas(can_write)`. Uno strumento scritto al round *N* è quindi chiamabile al round *N+1* — quella ricostruzione è l'intera funzionalità. Ogni chiamata è instradata a uno di quattro gestori (strumento fisso, generato, `write_tool`, `submit_answer`); un rifiuto torna come testo che il modello può riparare.

**Il budget.** Il primo `write_tool` più tre riparazioni, poi `write_tool` sparisce dall'insieme e la nota di guida sale da uno stimolo, a un avviso di round in esaurimento, a "risolvilo con ciò che hai".

**Verifica senza spendere token.** Un provider finto *scriptato*, sostituito nella tabella degli adattatori, gioca tre turni (scrivi, quattro chiamate parallele, invia) senza rete. Risolve `gstin_1 → KXMS`, scrive uno strumento e fa quattro chiamate — provando l'instradamento, la ricostruzione e il budget offline.

---

## Passo 13 — `main.py`, la riga di comando

**Cosa.** Sottocomandi `argparse`: `run` (con `--all`, `--set`, `--provider`), `tools`, `show`, `reset`, `redteam`. `run` carica il set e il registro, fallisce subito con l'URL della chiave, risolve ogni compito con una traccia dal vivo, e stampa una tabella dei risultati.

**Verifica.** `tools` mostra la scatola vuota, `reset` riporta zero file, e `run` senza chiave stampa l'URL della chiave Gemini ed esce con 1 — prima di ogni chiamata al modello.

---

## Passo 14 — `taskgen_finance.py`, un secondo set verificato con le librerie

**Cosa.** Due famiglie — cifre di controllo ISIN e date di seduta di borsa (NYSE e Nasdaq Stoccolma, 2025) — scelte con `--set finance`. Il generatore calcola ogni risposta dalla regola nel testo del compito, poi la **verifica con una libreria esterna**: le cifre ISIN con `python-stdnum`, le date di seduta con `exchange-calendars`, con gli elenchi di chiusura del testo asseriti uguali a quelli della libreria e nessun intervallo che tocchi una mezza giornata. Le librerie stanno in un gruppo di dipendenze separato, così solo il generatore ne ha bisogno — il JSON committato è puro dato.

**Perché un secondo set.** Mostra che la macchina è generale: lo stesso ciclo, guardia, sandbox e registro gestiscono una coppia di regole completamente diversa. Il set è un file separato dietro un flag, così il set core non cambia mai e le librerie pesanti non raggiungono mai l'agente.

**Ispezione della libreria per prima, di nuovo.** `stdnum.isin.calc_check_digit` riproduce la regola di Luhn su cifre espanse; `exchange_calendars` limita il suo intervallo alla prima seduta (quindi la query parte a dicembre), espone `early_closes` come proprietà, e ha confermato ogni data del piano — inclusa la chiusura NYSE del 9 gennaio 2025 (un giorno di lutto nazionale) e le mezze giornate che i compiti evitano di proposito.

**Il progetto delle sedute ha un bordo affilato.** Lo strumento prende l'elenco delle chiusure come *parametro*, e un batch nascosto passa l'elenco di Stoccolma *durante il task NYSE*. Così uno strumento che ignora il suo argomento `closures` fallisce alla **registrazione**, non solo al secondo compito. La prova offline mostra proprio questo: uno strumento che imposta `closed = set()` fallisce tutti e tre i batch nascosti.

**Verifica.** Il generatore gira pulito contro entrambe le librerie e riproduce le risposte previste; una nuova costruzione è byte-identica al file committato.

---

## Cosa coprono le autoverifiche, e cosa serve ancora una chiave

Ogni modulo ha un'autoverifica `__main__`, e passano tutte offline insieme alla suite di red-team e ai controlli byte dei due generatori. L'unica cosa che serve una chiave API vera è la demo *dal vivo*: `python -m src.main run ...` con un modello che risolve davvero un compito. Incolla una chiave Gemini in `.env` e gira dall'inizio alla fine.

## Cosa costruire dopo

- Un tetto di memoria su Windows (un Job Object) per pareggiare il limite di spazio di indirizzamento di POSIX.
- Raggruppare le chiamate parallele a uno stesso strumento generato in un solo processo sandbox.
- Altre famiglie di compiti, per continuare a mettere sotto stress la guardia contro codice reale scritto dal modello.
