<h1 align="center">Procedural Memory Lab</h1>

<p align="center">Un modello linguistico piccolo migliora recuperando una procedura, o gli basta rivedere una risposta simile?</p>

<p align="center"><a href="README.md">English</a> · <b>Italiano</b></p>

<p align="center"><img src="docs/images/cognitive-city.gif" width="880" alt="Una quest rigiocata in Cognitive City"></p>

<p align="center"><sub>Una quest rigiocata in Cognitive City, la pagina che trasforma un run concluso in una piccola città. I quattro agenti (NPC-A, B, C ed F) ricevono lo stesso bug a <i>Casa</i>. C ed F passano prima dalla <i>Biblioteca</i> per consultare qualcosa (<i>Sto imparando!</i>). Poi tutti scrivono una soluzione al <i>Negozio</i> e fanno i test all'<i>Ospedale</i>, prima di tornare a casa con <i>Missione riuscita</i>.</sub></p>

## La domanda

Un modello economico può avvicinarsi a uno costoso e potente su un compito reale, se può leggere conoscenza scritta in precedenza? E soprattutto: quella conoscenza deve essere una procedura generale, o basta avergli già mostrato una soluzione simile?

La seconda domanda è quella difficile. Un sistema che sembra imparare potrebbe soltanto recuperare risposte già viste. Copia e non generalizza, e le due cose non si distinguono contando quanti problemi risolve. La differenza va isolata di proposito, con un esperimento pensato per renderla visibile.

Il vocabolario del codice (Quest, Book, NPC, Librarian) è preso in prestito da un gioco di ruolo. È solo un'etichetta comoda per idee standard: recupero, memoria procedurale e instradamento tra modelli.

## Il banco di prova: un bug, quattro modi di affrontarlo

Ogni compito, una quest, è una funzione Python con un bug reale. Il verdetto non è mai un'opinione. Eseguo `pytest` in un sottoprocesso separato, così un modello linguistico non giudica mai un altro modello linguistico e il verificatore non può coincidere con ciò che viene verificato.

Lo stesso bug va a quattro agenti con lo stesso identico prompt di base.

| Config | Chi risolve | Cosa riceve in più | Cosa dovrebbe mostrare |
|---|---|---|---|
| **A, Expert** | modello grande e costoso | niente | quanto costerebbe farlo bene ogni volta |
| **B, Small** | modello economico | niente | quanto vale il modello nudo, la vera base di confronto |
| **F, Small + Skill Library** | modello economico | una procedura scritta dopo un tentativo precedente: generale, non legata a un caso | se una procedura riusabile aiuta |
| **C, Small + Solution Bank** | modello economico | la soluzione corretta di un problema simile già visto: un esempio, non una regola | se basta aver già visto un caso simile |

C è il pezzo che manca in gran parte dei discorsi sulle librerie di skill. Se F batte B è facile dire che la libreria insegna qualcosa di generale. Ma se anche C batte B di una quantità simile, quel guadagno potrebbe non c'entrare con una procedura: basterebbe aver visto un caso simile. Confrontare F con C, e non solo con B, è l'unico modo per distinguere le due storie.

Un dettaglio onesto. La soluzione data a C è la funzione di riferimento del catalogo dei bug, non una vera trascrizione scritta da Expert. È un sostituto ragionevole, perché Expert di solito risolve dal 95 al 100 per cento dei casi, ma non è la stessa cosa e lo dichiaro qui.

## Come si giudica un run

Ogni bug appartiene a uno split:

- **KNOWN** è l'esempio canonico di un pattern di bug già coperto da una skill o da una soluzione.
- **VARIANT** è lo stesso pattern con un problema diverso, e verifica la generalizzazione.
- **NOVEL** è un pattern mai coperto, di proposito. Per tre pattern non scrivo mai né una skill né una soluzione, così esiste sempre un gruppo di controllo permanente.

Ogni recupero, per F e per C, registra anche la sua copertura: `NONE` se non è stato trovato nulla di pertinente, `FULL` per una corrispondenza esatta, `PARTIAL` per C quando la soluzione riguarda un problema diverso della stessa famiglia.

Tengo separate le due cose perché rispondono a domande diverse. Se F senza nulla di trovato si comporta come B, ma F con una corrispondenza esatta fa meglio, allora è il contenuto recuperato a spostare il risultato e non la semplice presenza di un meccanismo di recupero. Ne escono due numeri:

- **Delta Retrieval** è l'accuratezza con copertura `FULL` meno quella con `NONE`, dentro la stessa config. Dice quanto conta trovare qualcosa.
- **Delta Architecture** è l'accuratezza della config con copertura `FULL` meno quella di B. Dice quanto l'intera architettura supera il modello nudo quando il recupero funziona davvero.

Per ogni tentativo conservo anche costo, latenza, uso di token e verdetto di `pytest`, e i report si costruiscono da questi dati e non a memoria.

## Recitazione o derivazione: il controllo causale

Il risultato più interessante finora non è un numero di accuratezza. È un modo di non farsi ingannare da una correlazione.

Studiando la skill `floating_point_equality`, che insegna a scegliere una tolleranza (un epsilon) invece di confrontare numeri decimali per uguaglianza esatta, mi è venuto un sospetto. Su un compito senza indizi numerici, F rispondeva sempre `1e-9`. O il modello ragionava sulla scala del problema, oppure ripeteva meccanicamente una costante scritta nella skill. Guardare la correlazione non basta a distinguere le due ipotesi, quindi ho fatto un test causale: ho cambiato direttamente la costante nella skill (`1e-9`, poi `2.5e-6`, poi `7e-4`) e ho controllato se la risposta si muoveva con essa.

- È successo 12 volte su 12, su due compiti scollegati.
- Cambiare invece una costante di una sezione diversa della skill, quella sulla valuta, non ha avuto alcun effetto, 6 volte su 6, e nemmeno il cambiamento inverso.

Quindi il modello sceglieva la regola giusta e poi copiava un numero preso da essa. Non derivava l'epsilon dalla scala del problema. È una sostituzione letterale di uno slot preciso, non una vaga abitudine di citare esempi.

Avrebbe potuto chiudersi lì, ma ho riscritto la skill chiedendo una derivazione invece di una costante fissa, e il modello ha iniziato a derivare. Ha seguito la grandezza del problema su sette ordini di grandezza, con un solo piccolo errore aritmetico. Il collo di bottiglia non era una capacità mancante del modello. Era il contenuto dell'istruzione.

Una conferma pulita è arrivata su un dominio davvero diverso, le cifre significative in un confronto decimale. Lì il modello ha prodotto due epsilon diversi nello stesso test, ciascuno corretto per la propria struttura decimale. Una sostituzione meccanica non può produrre due numeri diversi entrambi corretti, solo una vera derivazione può.

Il test sta in `experiment/canary.py`. Usa compiti sintetici che né l'ottimizzatore né il generatore di skill hanno mai visto, perché altrimenti la skill verrebbe scritta per superare il test, cioè l'opposto di misurarlo. Una versione leggibile delle risposte del modello, trascritte a mano e non rigenerate, è stata conservata come piccola pagina.

<p align="center"><img src="docs/images/epsilon-lab.png" width="760" alt="Il controllo sulla tolleranza, vista della pagina"></p>

## Cosa mostra la run di riferimento

Tutti i risultati qui sotto vengono da una sola run pulita, `experiment4`: 39 compiti, quattro config, 156 tentativi, un solo provider e un solo modello per config (Expert `gemini-3.7-flash`, Small `gemini-3.1-flash-lite`), eseguita in un'unica sessione. Le run precedenti non le uso più per nessun risultato. A metà cambiavano provider o modello, usavano un Expert diverso o avevano solo quattro compiti. Sono archiviate come log.

| Config | Risolti | Accuratezza | Intervallo al 95% |
|---|---|---|---|
| A, Expert | 38 / 39 | 97,4% | da 86,8 a 99,5 |
| B, Small | 36 / 39 | 92,3% | da 79,7 a 97,3 |
| F, Small + Skill Library | 38 / 39 | 97,4% | da 86,8 a 99,5 |
| C, Small + Solution Bank | 38 / 39 | 97,4% | da 86,8 a 99,5 |

| Split (compiti) | A | B | F | C |
|---|---|---|---|---|
| KNOWN (10) | 9 | 8 | 10 | 10 |
| VARIANT (21) | 21 | 20 | 20 | 20 |
| NOVEL (8) | 8 | 8 | 8 | 8 |

**Lettura delle differenze appaiate.** F ha battuto B su tre compiti e ha perso su uno. Le vittorie sono due compiti `wrong_string_case_comparison` e uno `floating_point_equality`, tutti con la skill trovata in modo esatto. La sconfitta è `floating_point_equality__temperature_reached__variant`, un compito la cui suite di test so essere difettosa: non verifica mai il caso che dovrebbe testare, quindi B "passa" senza scrivere alcun epsilon. Escludendo quel compito, F ne risolve 38 su 38 contro 35 su 38 di B, tre vittorie a zero, e un test di McNemar esatto dà p = 0,25. È una direzione, non un effetto significativo. F e C hanno risolto esattamente gli stessi compiti, quindi questa run non permette di distinguere una procedura riusabile da una soluzione simile già pronta, ed Expert è già vicino al massimo, il che lascia poco spazio per mostrare qualcosa.

**Dove sta il beneficio.** Una skill è stata iniettata in 31 dei 39 tentativi di F. In 27 di questi (87,1% secondo il conteggio del progetto, 28 se si conta il compito difettoso) B risolveva comunque il compito, quindi quelle iniezioni sono costate token senza cambiare nulla. Tre sono stati vantaggi reali. Il Delta Retrieval di F è meno 3,2 punti, ed è esattamente zero escludendo il compito difettoso. Quello di C è zero. Solo due dei dieci pattern coperti, `floating_point_equality` e `wrong_string_case_comparison`, mostrano un beneficio misurato in questa run.

**Costo.** La run è sequenziale, quindi token e latenza sono confrontabili. F paga in media 145 token di input in più di B (da 0 a 480) per usare una skill già pronta. Per compito: A 593 token, in gran parte ragionamento nascosto, B 221, C 308, F 370. Latenza media: A 13,8 s, B 0,93 s, C 0,88 s, F 0,96 s. Non riporto denaro, perché in questa run le variabili di prezzo non erano impostate e ogni costo risulta zero. Costruire le skill è un costo a parte. Il registro eventi della run segna 18 compressioni e 66 riverifiche, 35.269 token, circa 1.959 per skill. I costi di costruzione per pattern nel report economico, fino a circa 37.000 token, accumulano quanto la libreria condivisa è costata in tutte le run precedenti. Con da due a quattro compiti per pattern, un pattern su dieci è economicamente positivo (pareggio intorno a 13 usi), uno è positivo solo sull'accuratezza e otto sono negativi. Negativo non significa buttare la skill, perché con numeri così piccoli può avere un valore che le due metriche non catturano.

**Un secondo riferimento.** `experiment_totale_2026_09_18` fa girare gli stessi 39 compiti con lo stesso modello Small, ma con un Expert diverso (`gemini-3.6-flash`), in parallelo e con una politica di recupero che salta gli otto pattern in cui una skill non aveva mostrato benefici nelle run precedenti. Solo 6 tentativi di F ricevono una skill invece di 31, con una mediana di 149 token di input contro 257, eppure B, C e F risolvono esattamente gli stessi compiti di `experiment4`, comprese le tre vittorie di F, che stanno tutte nei sei compiti che ricevono ancora una skill. Non è una replica indipendente, perché la decodifica è quasi deterministica: la lunghezza dell'output di B è identica su 38 compiti su 39. Mostra invece che le 25 iniezioni eliminate non hanno avuto effetto sugli esiti. Lo uso per B, C e F, non per Expert e non per la latenza.

**Cosa non si può dire.** I compiti sono 39 bug Python di una sola funzione scritti per questo progetto, una sola esecuzione per cella, su una sola famiglia di modelli. Non separa una procedura da una soluzione simile già pronta, non mostra che il beneficio regga con un altro modello Small o in un altro dominio, e la differenza tra F e B è di tre compiti. I log completi delle run non fanno parte di questo repository pubblico, quindi questi numeri sono una mia lettura di `experiment4`, ricalcolata dal suo `log.jsonl`.

## Dall'esperimento controllato all'uso reale

Le stesse idee sono state poi portate a mano in Aria, un'app di studio che ho costruito per un utente reale con ADHD. Non è un prodotto in vendita. È il secondo terreno di prova della stessa domanda, con dati di comportamento reali invece di compiti sintetici. I due progetti restano separati di proposito, e tra loro non si condivide nulla a livello di codice.

Passare da un contesto sintetico a una persona vera ha cambiato alcune scelte.

- Le skill non vengono più generate in automatico dalle conversazioni. Una skill esiste solo quando qualcuno la crea di proposito.
- Il testo scritto dall'utente non viene mai riscritto in silenzio. L'unico accorciamento ammesso si può annullare, e viene tenuto solo se un secondo controllo indipendente conferma che obiettivo e criterio di riuscita restano intatti.
- Non ogni istruzione è una procedura. Solo un metodo, con un risultato atteso e un criterio di riuscita, può essere giudicato giusto o sbagliato da un esito. Una preferenza o una regola vincolante non è giusta o sbagliata in quel senso.

L'uso reale cambia anche il modo di misurare. Nell'esperimento posso forzare metà dei casi su F e metà su B. Nell'app è il sistema a decidere da solo quando una skill è pertinente, e questo introduce un bias nel campione, quindi le prove sono di due livelli di forza. Confrontare gruppi sull'uso ordinario è debole per costruzione, perché le richieste che attivano una skill tendono a essere più facili delle altre. La versione forte è un confronto appaiato alla cieca: la stessa richiesta reale risposta due volte, una con le skill e una senza, e giudicata senza sapere quale sia quale.

Cosa è emerso finora, con i suoi limiti.

- Il controllo causale descritto sopra è stato riusato su otto meccanismi di autoverifica che controllano l'output del modello indipendentemente da ciò che il modello ne dice. Ognuno è stato validato su un caso noto più una manipolazione diretta prima di entrare in uso. Restano tutti candidati: verificati una volta, ma non ancora osservati abbastanza a lungo nell'uso reale.
- Preliminare e fuori dalle run di riferimento: su un modello Gemma locale ho confrontato un meccanismo di recupero del comportamento con il solo prompt nudo su 22 coppie confrontabili, giudicate dagli stessi validator usati in produzione. Il risultato è stato 17 su 22 (77%) contro 13 su 22 (59%). Quasi tutto il vantaggio sta in un dominio, l'onestà sui materiali (6 su 9 contro 2 su 9). Sulla scomposizione dei compiti e sulle spiegazioni per principianti i due approcci sono più o meno pari. È un solo run per cella, senza ripetizioni, quindi la direzione è coerente con questo progetto ma il numero esatto non è conclusivo.
- Un risultato di qui è diventato una regola di prodotto. Quando si scrive una skill, vanno nominati esplicitamente i casi scomodi invece di fidarsi che il modello generalizzi da un principio. È la lezione del controllo sulla tolleranza.

Ho fermato di proposito anche una cosa. La condivisione automatica delle skill tra utenti non si porta com'è. Una skill nata dall'uso di una persona è tarata su quella persona, e non si può confrontare tra persone diverse come si confrontano i bug Python nel dominio sintetico. Quello che l'uso reale può aggiungere a questa ricerca è l'adattamento duraturo di un singolo agente nel tempo. Il trasferimento di conoscenza tra agenti diversi resta testato solo qui.

## Il percorso di una skill nel codice

1. **Nasce.** `librarian/skill_generator.py` crea un `Book` con stato `DRAFT`, oppure ne scrivo uno a mano.
2. **Viene verificata.** `librarian/optimizer.py` comprime e riverifica un Book sopra una soglia di costo, senza mai sovrascrivere l'originale. Se il controllo passa, salva una nuova versione con stato `VERIFIED`.
3. **Viene deduplicata.** `librarian/similarity.py` confronta coppie di Book per capire se la libreria accumula duplicati con nomi diversi, e `librarian/archive_duplicates.py` archivia, senza mai cancellare, quelli superati.
4. **Viene recuperata.** `librarian/librarian.py` instrada per sovrapposizione di tag, a costo zero e senza chiamate a embedding, e produce un `SkillPackage`.
5. **Entra nel budget.** `librarian/context_budget.py` impone un tetto reale al contesto iniettato, basato sulla finestra del modello e su un conteggio vero dei token, mai una stima.
6. **Entra nel prompt.** `SkillPackage.as_prompt_context()` concatena i testi delle procedure selezionate.
7. **Viene usata.** `agents/worker.py` costruisce il prompt completo, chiama il modello ed estrae la risposta.
8. **Viene misurata.** `experiment/events.py` registra ogni fase in JSONL, e i moduli di economia, riepilogo, tabella dell'osservatore e mappa della conoscenza trasformano quei log in report leggibili, senza costi perché leggono solo file locali.

Un `Book` è una procedura. Questi sono i suoi campi principali.

| Campo | Significato |
|---|---|
| `id`, `version`, `title`, `domain` | identità, versione e area |
| `problem_tags`, `capability_tags`, `resource_tags` | etichette che il Librarian usa per il confronto per sovrapposizione |
| `procedure_text` | il testo che entra davvero nel prompt |
| `pattern_id` | il pattern di bug a cui la procedura risponde |
| `status` | `DRAFT` se appena generata, `VERIFIED` dopo la riverifica dell'ottimizzatore |
| `confidence`, `verification_count` | fiducia numerica, e quante volte e come è stata riverificata |
| `derived_from`, `supersedes`, `superseded_by` | genealogia: da cosa è stata compressa e la catena delle versioni |
| `duplicate_of` | un altro Book giudicato duplicato dal controllo di similarità |
| `generation_method` | `manual`, `compression` o `skill_generator` |

## Come è organizzato il repository

- `domain/` contiene i compiti, le famiglie di bug e i controlli deterministici.
- `agents/` costruisce il prompt e fa girare il risolutore.
- `librarian/` recupera, dosa, confronta e ottimizza con cautela le procedure.
- `cheater/` è la banca delle soluzioni usata dalla config C.
- `experiment/` esegue le configurazioni affiancate, salva i punti di ripresa e scrive le prove.
- `verification/` contiene le sonde causali, gli holdout, la logica di recupero e i controlli di coerenza, con gli script eseguibili in `benchmarks/`, `runners/` e `validation/`.
- `tests/` contiene i test automatici, organizzati come il pacchetto (`experiment`, `librarian`, `verification`). Si lanciano dalla cartella superiore con `python -m pytest cognitive_rpg`.
- `city/` trasforma un run concluso nella pagina di Cognitive City mostrata sopra.
- `adapters/` collega i provider dei modelli, con adattatori simulati per lo sviluppo.
- `library/books/` è la libreria delle procedure.

## Avvio

Serve Python 3.11 o superiore. Clona il repository in una cartella chiamata `cognitive_rpg` e lancia i comandi dalla cartella che la contiene, così il pacchetto si può importare. La configurazione scrive il tuo `.env` in quella cartella superiore, fuori dal repository.

```sh
python -m pip install -r cognitive_rpg/requirements.txt
python -m cognitive_rpg.settings_wizard
python -m cognitive_rpg.experiment.experiment_0
```

Per sviluppare ci sono adattatori simulati che non richiedono chiamate a pagamento. Le esecuzioni reali richiedono le chiavi dei provider, che la configurazione chiede e non salva mai nel repository.

## I termini in un posto solo

| Termine | Significato |
|---|---|
| Quest | un bug da risolvere, controllato automaticamente con `pytest` |
| Book | una procedura scritta, l'unità base della libreria di skill |
| Librarian | il componente che instrada le skill pertinenti, per sovrapposizione di tag, a costo zero |
| Optimizer | comprime e riverifica una skill senza mai sovrascrivere l'originale |
| KNOWN, VARIANT, NOVEL | esempio canonico, stesso pattern con un altro problema, pattern mai coperto (il controllo) |
| Coverage | quanto ha trovato il recupero: `NONE`, `PARTIAL` o `FULL` |
| DRAFT, VERIFIED | ciclo di vita di una skill: appena generata, poi riverificata prima di fidarsene |

## Stato

Il lavoro è in corso e non è un articolo sottoposto a revisione. I risultati sono prove da caso di studio, con i loro limiti scritti accanto. I risultati di riferimento vengono da una sola run pulita, `experiment4`, con `experiment_totale_2026_09_18` come secondo riferimento. Tutto il resto è tenuto come log.

## Licenza

Copyright © 2026 Ferdinando Gregorio Fernandez. Tutti i diritti riservati. Il codice è visibile per valutazione di portfolio e di ricerca. Riuso, ridistribuzione e opere derivate non sono consentiti. Vedi [LICENSE](LICENSE).
