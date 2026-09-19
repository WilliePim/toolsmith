# Progetto

*Italiano · [English](../en/design.md)*

Le decisioni dietro la costruzione, e i dati confermati per il set finance. Per la storia passo-passo vedi [build-journal.md](build-journal.md); per i diagrammi vedi [architecture.md](architecture.md).

## Il problema che risolve

Il tutorial *"Build an Agent That Writes Its Own Tools"* è leggibile per le prime nove sezioni; il resto è dietro un paywall. Invece di recuperare il testo nascosto, i moduli mancanti (sandbox, guardia, registro, smith, prompt, agente, red-team, CLI) sono stati progettati da ciò che la metà visibile fissa — il diagramma dell'architettura, l'indice, i vincoli dichiarati — e poi provati con una suite adversariale. Il risultato voluto è un'implementazione di riferimento funzionante e leggibile, che un estraneo può eseguire e da cui può imparare.

## Decisioni che hanno plasmato tutto

**Neutrale rispetto al provider, Gemini e Claude.** La dipendenza da Groq del tutorial è sostituita da `llm.py` più un adattatore per API. Gemini è il default (chiave gratuita) ed è esercitato dal vivo; l'adattatore Claude è scritto per intero e verificato offline. La separazione ha imposto una cucitura netta: ogni adattatore possiede le sue forme di messaggio, perché le firme di pensiero di Gemini e i blocchi di pensiero di Claude vanno entrambi rimandati indietro immutati.

**Le risposte sono generate, mai battute.** L'esempio di input nascosto del tutorial era sbagliato, quindi ogni file di compiti è costruito da codice di riferimento (`taskgen.py`, `taskgen_finance.py`), con `--check` a garantire che il file committato combaci. Le risposte finance sono verificate con `python-stdnum` ed `exchange-calendars`.

**Due livelli di sicurezza indipendenti.** La guardia statica legge i nomi; il sandbox sorveglia valori e tempo. Nessuno dei due si fida dell'altro, e il red-team prova ciascuno da solo. Diverse correzioni di irrobustimento vanno oltre il codice visibile del tutorial — vedi [security.md](security.md).

**L'interfaccia di famiglia (`tool_params`).** Ogni famiglia dichiara la firma esatta di `run()`. È ciò che permette al controllo nascosto di chiamare uno strumento con input nascosti, e ciò che costringe lo strumento delle sedute a ricevere il suo elenco di chiusure come parametro invece di scriverlo dentro.

**Un commit per passo verificato, su `develop`.** Ogni modulo arriva con un'autoverifica `__main__`, così ogni passo è provato prima che cominci il successivo.

## Ordine di costruzione

Fondamenta (`config`, `taskgen`, `tools`) → livello del modello (`llm`, adattatori) → sicurezza (`protocol`, `sandbox`, `guard`, red-team, provati senza costi API) → agente (`registry`, `smith`, `prompts`, `agent`) → CLI e documentazione → il set finance.

## Verifica dall'inizio alla fine

1. `uv run python -m src.redteam` — entrambi i livelli di sicurezza, senza chiamate API.
2. L'autoverifica `__main__` di ogni modulo.
3. Il confronto byte `--check` dei due generatori di compiti.
4. Con una chiave in `.env`: `uv run python -m src.main run --all` e `--set finance`.

---

## Appendice A — il set finance (confermato)

Ogni valore qui sotto è stato calcolato dalla regola nel testo del compito e verificato con una libreria al momento della generazione. Regole comuni: la regola e un esempio svolto sono nel testo; c'è una sola risposta esatta; il caso limite nascosto discende dalla regola scritta; gli input visibili non portano casi limite; ogni batch nascosto ha almeno due input limite su sei; l'anno è il 2025.

### Famiglia `isin` — interfaccia `prefix` (11 caratteri) → cifra di controllo; joiner `""`

Regola: un ISIN è un codice paese di due lettere, un corpo di nove caratteri e una cifra di controllo. Trasforma i primi 11 caratteri in cifre (A=10 … Z=35, cifre invariate), poi Luhn da destra; la cifra di controllo è `(10 − somma mod 10) mod 10`. Esempio svolto: `US037833100` → `5`. Indizio: *alcuni codici contengono lettere dopo il prefisso paese di due lettere.* Le posizioni nel corpo si contano 1–9 da sinistra.

| | Prefissi (emittente) | Lettere nel corpo | Risposta |
|---|---|---|---|
| isin_1 | DE000716460 SAP · IT000312836 Enel · FR000012027 TotalEnergies · US594918104 Microsoft · IT000006207 Generali · GB000989529 AstraZeneca | nessuna | `071522` |
| isin_2 | CH003886335 Nestlé · NL001027321 ASML · JP363340000 Toyota · IT000007261 Intesa · DE000723610 Siemens · US023135106 Amazon | nessuna | `051817` |
| H1 | US88160R101 Tesla · GB000237400 Diageo · US02079K305 Alphabet · DE000519000 BMW · NL00150001Q Stellantis · IT000385640 Leonardo | R6, K6 pari · Q9 dispari | `469395` |
| H2 | US30303M102 Meta · IE00B4L5Y98 iShares World · FR000012101 LVMH · US67066G104 Nvidia · DE000840400 Allianz · IT000523936 UniCredit | M6, G6 pari · B3, L5, Y7 dispari | `734050` |
| H3 | GB00BH4HKS3 Vodafone · US92826C839 Visa · IT000313247 Eni · US46625H100 JPMorgan · FR000013110 BNP Paribas · CH001203204 Roche | C6, H6 pari · Vodafone B3, K7 dispari | `946548` |

### Famiglia `sessions` — interfaccia `start`, `n`, `closures` → una data; joiner `","`

Regola: una seduta è un giorno feriale che non è una festività di mercato (le mezze giornate contano come sedute intere). L'elenco delle festività nel testo è l'unica fonte valida. Restituisci l'n-esima seduta strettamente dopo la data di partenza; la partenza non conta mai. Esempio svolto: `2025-03-07` (ven), n=3 → `2025-03-12`. Indizio: *alcuni intervalli contengono un giorno di chiusura.*

- **Festività NYSE 2025 (nel testo di sessions_1):** 01-01, 01-09 (elencata, non toccata da alcun intervallo), 01-20, 02-17, 04-18, 05-26, 06-19, 07-04, 09-01, 11-27, 12-25.
- **Festività Stoccolma 2025 (nel testo di sessions_2):** 01-01, 01-06, 04-18, 04-21, 05-01, 05-29, 06-06, 06-20, 12-24, 12-25, 12-26, 12-31.
- **Mezze giornate che nessun intervallo attraversa:** NYSE 07-03, 11-28, 12-24; Stoccolma 04-17, 04-30, 05-28, 10-31 (confermate dalla libreria).

| | Coppie (partenza, n), 2025 | Festività attraversate | Risposta |
|---|---|---|---|
| sessions_1 (NYSE) | (02-03,7) (05-02,10) (08-13,4) (10-10,12) (03-18,6) (09-15,8) | nessuna | `2025-02-12,2025-05-16,2025-08-19,2025-10-28,2025-03-26,2025-09-25` |
| sessions_2 (Stoccolma) | (02-10,8) (07-01,5) (08-29,3) (11-24,5) (01-13,5) (05-22,3) | nessuna (tutte e sei diverse con l'elenco NYSE) | `2025-02-20,2025-07-08,2025-09-03,2025-12-01,2025-01-20,2025-05-27` |
| H1 (elenco NYSE) | (04-15,4) (06-02,3) (01-16,3) (08-25,5) (10-01,4) (12-10,6) | 04-18, 01-20, 09-01 | `2025-04-22,2025-06-05,2025-01-22,2025-09-02,2025-10-07,2025-12-18` |
| H2 (elenco NYSE) | (05-22,2) (06-17,3) (07-07,5) (02-13,2) (11-18,5) (09-26,4) | 05-26, 06-19, 02-17 | `2025-05-27,2025-06-23,2025-07-14,2025-02-18,2025-11-25,2025-10-02` |
| H3 (elenco Stoccolma) | (06-04,2) (06-18,2) (02-03,5) (03-10,7) (09-08,4) (10-13,6) | 06-06, 06-20 | `2025-06-09,2025-06-23,2025-02-10,2025-03-19,2025-09-12,2025-10-21` |

H3 porta l'elenco delle festività di Stoccolma, quindi compare nell'insieme nascosto della famiglia `sessions` e coglie uno strumento che ignora il suo argomento `closures` già durante il primissimo task (NYSE).
