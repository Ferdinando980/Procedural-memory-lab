<h1 align="center">Procedural Memory Lab</h1>

<p align="center">Un modello linguistico piccolo migliora recuperando una procedura, o gli basta rivedere una risposta simile?</p>

<p align="center"><a href="README.md">English</a> · <b>Italiano</b></p>

<p align="center"><img src="docs/images/cognitive-city.gif" width="880" alt="Una quest rigiocata in Cognitive City"></p>

<p align="center"><sub>Una quest rigiocata in Cognitive City, la pagina che trasforma un run concluso in una piccola città. I quattro agenti (NPC-A, B, C ed F) ricevono lo stesso bug a <i>Casa</i>. C ed F passano prima dalla <i>Biblioteca</i> per consultare qualcosa (<i>Sto imparando!</i>). Poi tutti scrivono una soluzione al <i>Negozio</i> e fanno i test all'<i>Ospedale</i>, prima di tornare a casa con <i>Missione riuscita</i>.</sub></p>

## In breve

- **La domanda.** Un modello economico migliora perché ha una procedura generale, o solo perché ha già visto una soluzione simile?
- **Il risultato di riferimento** (una run pulita, 39 compiti). Il modello piccolo da solo ne risolve 36, con una procedura 38, con la soluzione di un caso simile 38, e gli ultimi due hanno risolto gli stessi compiti. Sono tre fallimenti recuperati: una direzione, non un effetto statisticamente significativo.
- **Ragiona o copia?** Cambiando una costante dentro la procedura, la risposta del modello la seguiva 12 volte su 12. Chiedendo di derivare il valore, il modello ha calcolato tolleranze su sette ordini di grandezza.
- **Serve sempre?** In 27 dei 31 compiti in cui il modello piccolo riceveva una procedura, li avrebbe risolti comunque.

## La domanda

Un modello economico può avvicinarsi a uno più potente se gli permettiamo di recuperare conoscenza scritta in precedenza?

E soprattutto: **deve essere una procedura generale, oppure basta mostrargli la soluzione di un problema simile?**

La seconda domanda è quella che mi interessava davvero.

Un sistema che sembra imparare potrebbe semplicemente ricordare una risposta. Magari risolve più problemi, costa meno e sembra anche ragionare meglio. Ma quale parte del miglioramento viene dalla conoscenza che gli abbiamo dato? E quella conoscenza gli ha insegnato un metodo, oppure gli ha fornito qualcosa da copiare?

Contare i successi non basta per distinguere le due possibilità.

Ho costruito Procedural Memory Lab per provare a separarle, con esperimenti controllati, un verificatore automatico e un confronto che spesso manca quando si parla di Skills: quello con una soluzione precedente già pronta.

Nel tempo, però, il laboratorio ha iniziato a rispondere anche ad altre domande.

**Quando una procedura è davvero utile? Quando è soltanto un costo? Può persino peggiorare un modello che senza aiuti avrebbe risolto il problema? E come faccio a sapere se il mio test sta misurando la cosa giusta?**

Sono domande nate dai risultati, compresi quelli che non mi aspettavo.

Il progetto usa un vocabolario preso dai giochi di ruolo: Quest, Book, NPC, Librarian. I nomi sono una scelta narrativa; sotto ci sono normali problemi di memoria procedurale, recupero della conoscenza, valutazione e instradamento tra modelli.

## Un bug, quattro modi di affrontarlo

Ogni Quest è una funzione Python con un bug introdotto nel catalogo sperimentale.

La stessa richiesta viene affidata a quattro configurazioni. Cambia il modello, oppure la conoscenza aggiuntiva che può consultare.

| Configurazione | Chi risolve | Cosa riceve |
|---|---|---|
| **A — Expert** | Modello più potente | Nessun aiuto |
| **B — Small** | Modello economico | Nessun aiuto |
| **F — Skill Library** | Stesso modello economico | Una procedura generale recuperata dalla libreria |
| **C — Solution Bank** | Stesso modello economico | La soluzione corretta di un problema simile |

B è il punto di partenza: cosa sa fare il modello da solo?

F verifica se una procedura scritta in precedenza può aiutarlo.

C pone il dubbio più importante: **e se il vantaggio di F non dipendesse affatto dall'avere una procedura?**

Se F supera B, sappiamo che qualcosa è migliorato. Ma se C ottiene lo stesso risultato, non possiamo attribuire quel miglioramento alla generalizzazione procedurale.

Il confronto F contro C serve proprio a mettere in difficoltà questa interpretazione.

C'è una limitazione da dichiarare: la soluzione fornita a C è la funzione di riferimento del catalogo, non una risposta realmente prodotta da Expert in un'esecuzione precedente. È un proxy utile, ma non coincide perfettamente con una memoria di esperienze reali.

### Come verifico le risposte?

Non chiedo a un altro modello linguistico di decidere se il codice è corretto.

La soluzione viene eseguita attraverso `pytest`, in un sottoprocesso separato, e riceve un esito verificabile.

Questo evita di affidare il giudizio alla preferenza di un altro LLM. Non rende però infallibile il verificatore: anche i test possono essere incompleti o sbagliati. Durante la ricerca ho trovato esempi concreti proprio di questo problema.

I task sono inoltre divisi in tre gruppi:

- **KNOWN:** il caso canonico di un pattern già coperto.
- **VARIANT:** lo stesso tipo di errore, ma in un problema differente.
- **NOVEL:** un pattern mai coperto dalla libreria, usato come controllo.

Per alcuni pattern NOVEL non viene mai creata una Skill né inserita una soluzione precedente.

Quando il Librarian recupera qualcosa, registro anche la copertura: `NONE`, `FULL` oppure `PARTIAL`, quest'ultima usata per le corrispondenze parziali della Solution Bank.

Non voglio soltanto sapere se F ha vinto. Voglio sapere **che cosa gli è stato effettivamente fornito quando ha vinto**.

## Le procedure funzionano davvero?

La run di riferimento è `experiment4`: 39 compiti, quattro configurazioni e 156 tentativi.

È stata eseguita in un'unica sessione, con un solo provider e un modello per configurazione: `gemini-3.7-flash` per Expert e `gemini-3.1-flash-lite` per Small.

| Configurazione | Risolti | Accuratezza |
|---|---:|---:|
| A — Expert | 38/39 | 97,4% |
| B — Small | 36/39 | 92,3% |
| F — Skill Library | 38/39 | 97,4% |
| C — Solution Bank | 38/39 | 97,4% |

A prima vista il risultato sembra semplice.

Il modello piccolo, con una procedura, raggiunge Expert. Ma anche quello con una soluzione precedente raggiunge Expert.

Ecco il problema: **F e C hanno risolto esattamente gli stessi compiti**.

Questa run non dimostra che una procedura generale sia migliore di un esempio concreto.

F ha guadagnato tre vittorie rispetto a B, perdendo però un compito sul quale è stato individuato un test difettoso. Escludendo quel caso, il confronto è di tre vittorie a zero su 38 task. Il test esatto di McNemar restituisce `p = 0,25`.

È una direzione interessante, non una differenza statisticamente significativa.

Non voglio trasformare tre problemi risolti in una conclusione molto più grande di quello che i dati permettono.

### E le run precedenti?

Prima di `experiment4` ci sono altre run numerate. Non le uso per nessun risultato: in alcune il provider o il modello cambiavano a metà esecuzione, una usava un Expert diverso, un'altra aveva soltanto quattro compiti. Le ho archiviate come log. Servono a ricostruire la storia della ricerca, non a sostenere una conclusione.

Il primissimo run, ancora precedente, non mostrava benefici.

Per un periodo quella conclusione era rimasta scritta anche dopo nuovi risultati. Non l'ho eliminata dalla storia: semplicemente non era più sufficiente a descrivere il progetto.

Per questo oggi tengo separati il risultato di riferimento, le osservazioni esplorative e le verifiche successive.

## Il modello sta ragionando o sta copiando?

Questa è probabilmente la scoperta che mi ha fatto cambiare di più il modo di pensare alle procedure.

Stavo studiando `floating_point_equality`, una Skill che insegna a evitare confronti esatti tra numeri decimali usando una tolleranza, chiamata epsilon.

Su un compito senza indicazioni numeriche, il modello rispondeva sempre con:

`1e-9`

Ma perché proprio quel numero?

Poteva aver dedotto che fosse appropriato. Oppure poteva semplicemente averlo letto nella Skill e ripetuto.

Ho deciso di modificare direttamente la costante nella procedura.

Prima `1e-9`, poi `2.5e-6`, poi `7e-4`.

**La risposta del modello ha seguito il cambiamento 12 volte su 12**, su due compiti scollegati.

Ho modificato anche una costante in una sezione non pertinente della Skill, dedicata alla valuta. In quel caso non è cambiato nulla, 6 volte su 6.

Il modello non stava copiando un numero qualsiasi. Stava selezionando la sezione pertinente e prendendo il valore che trovava lì.

Poi ho fatto una seconda prova.

Invece di fornire una costante fissa, ho riscritto la procedura chiedendo di derivare la tolleranza dalla scala del problema.

Il comportamento è cambiato. Il modello ha iniziato a produrre valori dipendenti dal problema, attraversando sette ordini di grandezza con un solo errore aritmetico osservato.

In un caso sulle cifre significative ha persino prodotto due epsilon differenti nello stesso test, entrambi corretti per la rispettiva struttura decimale.

Questo non permette di osservare direttamente i processi interni del modello. Permette però di distinguere due comportamenti: ripetere un valore prescritto e calcolare valori diversi in funzione degli input.

**Il modello era capace di produrre la soluzione richiesta. La prima istruzione lo stava guidando verso un comportamento più rigido.**

Il controllo è implementato in `experiment/canary.py`, con compiti sintetici non utilizzati per costruire o ottimizzare le Skills. Una versione leggibile delle risposte del modello, trascritte a mano e non rigenerate, è stata conservata in una piccola pagina.

<p align="center"><img src="docs/images/epsilon-lab.png" width="760" alt="Il controllo sulla tolleranza, vista della pagina"></p>

## E se una Skill peggiorasse il risultato?

Qui la ricerca ha preso una direzione che non avevo previsto.

L'idea di avere una regola generale sempre disponibile sembra ragionevole. Se una procedura è utile, perché non mostrarla al modello anche prima che ne abbia bisogno?

Ho verificato cosa accadeva con una Skill generica sempre attiva. È un'osservazione esplorativa, fatta con un modello locale (Gemma) e fuori dalla run di riferimento.

Sugli stessi 33 task:

| Condizione | Successi |
|---|---:|
| Senza Skill generica | 28/33 — 84,8% |
| Con Skill generica | 21/33 — 63,6% |

In una verifica successiva, dopo aver rimosso quella Skill, i successi sono tornati a 29/33.

È una sola esecuzione per condizione. Ripetendo la stessa condizione ho visto oscillazioni di uno o due task: la differenza di sette è più ampia, ma una prova come questa non basta a dire quanto sia robusta.

Il danno è osservabile. La sua causa precisa, invece, non è stata isolata.

Una possibile spiegazione è che l'istruzione inducesse il modello a cercare problemi nascosti anche dove non esistevano. Ma non ho separato sperimentalmente gli effetti della lunghezza, della formulazione, della struttura e dell'attivazione indiscriminata.

Quindi non posso dire che tutte le regole globali siano dannose.

Posso dire qualcosa di più circoscritto, ma utile: **in una prova esplorativa, una procedura apparentemente ragionevole ha peggiorato compiti che il modello sapeva già risolvere**.

Questo cambia la domanda da porre prima di aggiungere una nuova Skill.

Non soltanto: «Potrebbe essere utile?»

Anche: «Cosa succede ai problemi che il modello risolveva già senza di essa?»

## Serve davvero recuperare una procedura ogni volta?

Un altro risultato mi ha colpito per il motivo opposto.

Nella run di riferimento, in 27 dei 31 compiti in cui F riceveva una Skill, il modello B risolveva comunque il compito senza aiuti (28 se si conta anche il compito difettoso).

In molti casi, quindi, il recupero aggiungeva testo al prompt senza cambiare l'esito.

Non è automaticamente inutile. Potrebbe avere effetti non catturati dalla sola accuratezza. Ma quei token vengono comunque consumati.

Ho provato anche una politica che evitava di recuperare le procedure appartenenti a otto pattern risultati poco utili nelle run precedenti.

Nel secondo riferimento, `experiment_totale_2026_09_18`, le iniezioni passano da 31 a 6, mentre B, C e F risolvono gli stessi task del run di riferimento. Lì cambiano anche l'Expert e il modo di esecuzione, in parallelo, quindi lo uso solo per B, C e F.

Non considero questa una replica indipendente: utilizza gli stessi compiti e un comportamento di decodifica quasi deterministico. Mostra però che, in quel confronto, le 25 iniezioni eliminate non modificavano gli esiti.

A quel punto nasce una nuova domanda.

**Forse il problema non è soltanto trovare la procedura giusta. È capire quando il modello non ha bisogno di nessuna procedura.**

Il Librarian recupera per sovrapposizione di tag. Il fatto che una procedura sia pertinente al problema non dimostra che sia anche necessaria.

Pertinenza e utilità sono due cose diverse.

## Quanto costa insegnare qualcosa che il modello sa già fare?

Una Skill non è gratuita, neppure quando esiste già.

In `experiment4`, F consuma mediamente 145 token di input in più di B per utilizzare la libreria.

Il consumo medio complessivo registrato per tentativo è:

| Configurazione | Token medi |
|---|---:|
| A — Expert | 593 |
| B — Small | 221 |
| C — Solution Bank | 308 |
| F — Skill Library | 370 |

Per A la maggior parte dei token è ragionamento nascosto del modello, che il registro conta a parte ma che qui è incluso.

Anche costruire una Skill ha un costo.

Nel registro della run, 18 compressioni e 66 riverifiche hanno consumato complessivamente 35.269 token, circa 1.959 per Skill nel conteggio utilizzato.

E questo senza contare tutto il costo storico accumulato durante la ricerca.

Nel rapporto economico del run più completo, su dieci pattern coperti, uno è classificato economicamente positivo, uno positivo sull'accuratezza e otto negativi secondo i criteri adottati.

Non significa che otto procedure siano prive di valore. I campioni per pattern sono piccoli, e una procedura potrebbe diventare conveniente dopo più utilizzi.

Significa che **avere una libreria di conoscenze non è automaticamente più economico che risolvere direttamente il problema**.

Per questo il progetto considera il punto di pareggio, il costo di costruzione, il costo per utilizzo e il risultato ottenuto.

Nella run di riferimento non riporto costi monetari affidabili: le variabili di prezzo non erano configurate e i valori registrati risultano zero. Token e latenza, invece, sono disponibili.

## E se il verificatore fosse quello che sbaglia?

C'è una cosa che non mi piace dei benchmark: quanto sia facile fidarsi di un numero soltanto perché è prodotto da un programma.

All'inizio avevo scelto `pytest` proprio per evitare giudizi soggettivi tra modelli.

È stata una scelta utile, ma non sufficiente.

Durante la ricerca sono stati individuati sei bug nell'infrastruttura di verifica e due task difettosi.

In un caso il test non controllava realmente il comportamento per cui era stato scritto: `temperature_reached`, quello che compare anche nella run di riferimento. In un altro, il difetto vero non era quello dichiarato: una chiamata `.upper()` incidentale nel corpo del ciclo faceva fallire il compito, e correggere soltanto il problema indicato non bastava a farlo passare.

Un modello poteva quindi ricevere un successo senza aver risolto il problema che intendevo misurare, o un fallimento per un motivo diverso da quello che intendevo misurare.

La conseguenza è semplice: **un verificatore deterministico può restituire un risultato ripetibile e comunque sbagliato**.

C'è anche il problema dell'adattamento ai test.

In una prova esplorativa della serie di settembre, un risultato storico di 195 successi su 195, ottenuto con suite di test che avevano fatto da oracolo durante la ricerca, non si è mantenuto su un piccolo insieme di sei casi freschi: ne sono stati superati quattro.

Sei casi non bastano per stimare una nuova accuratezza generale, e non sono direttamente comparabili con tutto il campione storico. Bastano però per mostrare che un risultato perfetto sui casi utilizzati durante lo sviluppo può essere fragile.

Oggi, quando una prova sembra troppo convincente, cerco prima di capire **che cosa potrebbe renderla ingannevole**.

## Sapere che problema è significa sapere come risolverlo?

Non sempre.

Ho eseguito anche piccole prove esplorative per separare il riconoscimento del problema dalla procedura proposta per risolverlo.

In alcuni casi la diagnosi bastava a sbloccare il modello.

In altri, aggiungere una procedura completa non migliorava il risultato o lo peggiorava. Una procedura-placebo, priva di contenuto utile, ha persino portato un caso `flatten_list` da tre successi su tre a zero su tre.

Sono campioni minuscoli: tre ripetizioni su uno o due task per pattern. Non permettono conclusioni generali.

Ma indicano una distinzione che vale la pena conservare.

Un modello può fallire perché non riconosce il problema. Oppure può riconoscerlo correttamente e non sapere come intervenire. Oppure può sapere già come intervenire, ma essere deviato da istruzioni aggiuntive.

Questi tre errori non richiedono necessariamente lo stesso tipo di conoscenza.

## Dall'esperimento controllato all'uso reale

Ho portato alcune idee del laboratorio anche in Aria, un'app di studio costruita per un utente reale con ADHD.

Non è un prodotto in vendita, e i due progetti rimangono separati a livello di codice.

L'uso reale ha imposto criteri diversi.

Le Skills non vengono generate automaticamente dalle conversazioni. Una procedura nasce da una scelta esplicita. Il testo scritto dall'utente non viene riscritto in silenzio. Gli accorciamenti devono essere reversibili e controllati.

Soprattutto, ho dovuto distinguere tra una procedura verificabile, una preferenza personale e una regola vincolante.

Non tutto quello che una persona chiede di ricordare può essere trattato come un metodo da premiare o penalizzare in base a un test.

Cambia anche la valutazione.

Nel laboratorio posso assegnare lo stesso task a due configurazioni. Nell'uso reale è il sistema a scegliere quando recuperare una Skill. Le richieste che la attivano potrebbero quindi essere diverse, e più facili, di quelle che non la attivano.

Per ridurre questo problema serve un confronto appaiato e, quando possibile, alla cieca.

In un controllo preliminare con un modello Gemma locale, su 22 coppie confrontabili, il meccanismo di recupero del comportamento ha ottenuto 17 successi contro 13 del prompt senza supporto.

Quasi tutto il vantaggio era concentrato in un solo dominio, l'onestà sui materiali. Negli altri domini i risultati erano molto più simili.

Un solo run per condizione non permette conclusioni definitive, e questo controllo sta fuori dai dati di riferimento del laboratorio.

Il passaggio all'uso reale mi ha insegnato soprattutto che **una procedura nata per una persona non diventa automaticamente una buona procedura per tutte le altre**.

## Come funziona la memoria procedurale nel codice?

L'unità della libreria si chiama `Book`.

Un Book contiene una procedura, la sua identità, i tag di recupero, lo stato di verifica e le informazioni sulle versioni precedenti.

Il suo percorso è questo:

1. **Nasce.** `librarian/skill_generator.py` crea una procedura in stato `DRAFT`, oppure viene scritta manualmente.
2. **Viene verificata.** `librarian/optimizer.py` può comprimerla e riverificarla senza sovrascrivere l'originale. Una versione che supera i controlli diventa `VERIFIED`.
3. **Viene confrontata.** `librarian/similarity.py` cerca possibili duplicati; `archive_duplicates.py` archivia le versioni superate senza cancellarle.
4. **Viene recuperata.** `librarian/librarian.py` usa la sovrapposizione dei tag e restituisce uno `SkillPackage`, senza chiamate a embedding.
5. **Entra nel budget.** `librarian/context_budget.py` controlla quanti token possono essere inseriti nel contesto.
6. **Entra nel prompt.** `SkillPackage.as_prompt_context()` assembla le procedure selezionate.
7. **Viene usata.** `agents/worker.py` costruisce il prompt e interroga il modello.
8. **Viene misurata.** `experiment/events.py` registra i passaggi in JSONL, da cui vengono generati i report.

L'intero processo è tracciabile, anche quando il risultato è negativo.

### Dove si trova cosa?

| Directory | Ruolo |
|---|---|
| `domain/` | Bug, famiglie di task e verificatori |
| `agents/` | Prompt e chiamate ai modelli |
| `librarian/` | Recupero, gestione, confronto e ottimizzazione delle procedure |
| `library/books/` | Libreria delle Skills |
| `cheater/` | Solution Bank della configurazione C |
| `experiment/` | Esecuzione dei confronti e registrazione dei risultati |
| `verification/` | Controlli causali, holdout e verifiche, con gli script in `benchmarks/`, `runners/` e `validation/` |
| `tests/` | Test automatici del laboratorio |
| `city/` | Visualizzazione delle Quest in Cognitive City |
| `adapters/` | Collegamento ai provider e simulatori |

## Come provarlo

Serve Python 3.11 o superiore.

Clona il repository in una directory chiamata `cognitive_rpg`, poi esegui i comandi dalla cartella che la contiene.

```bash
python -m pip install -r cognitive_rpg/requirements.txt
python -m cognitive_rpg.settings_wizard
python -m cognitive_rpg.experiment.experiment_0
```

Gli adapter simulati permettono di sviluppare senza chiamate a pagamento. Le esecuzioni con modelli reali richiedono le chiavi dei rispettivi provider.

I test del pacchetto possono essere lanciati dalla directory superiore con:

```bash
python -m pytest cognitive_rpg
```

## Cosa posso concludere?

Non che le Skills siano sempre utili.

Non che un modello piccolo, con una buona libreria, possa sostituire in generale un modello più potente.

E nemmeno che una procedura sia necessariamente migliore di un esempio precedente.

I risultati permettono una conclusione più circoscritta.

**La conoscenza esterna può modificare concretamente il comportamento di un modello. Ma il suo beneficio dipende dal compito, da ciò che il modello sa già fare, da cosa contiene la procedura e da quando viene recuperata.**

In alcuni casi la procedura aiuta. In altri l'esempio ottiene lo stesso risultato. In molti non serve nulla. E in una prova esplorativa una regola aggiuntiva ha fatto peggiorare sensibilmente le prestazioni.

Il controllo causale sulla tolleranza mostra anche che una procedura può indirizzare il modello verso la copia di un valore oppure verso una derivazione dipendente dal problema.

Questi sono risultati osservati nel contesto del laboratorio. Non dimostrano automaticamente come debbano essere organizzati i file di istruzioni di un agente, le sue Skills o i sistemi di Context Engineering più complessi.

Forniscono però un metodo per studiarli: confronti appaiati, controlli negativi, modifiche causali, casi non visti e verificatori sottoposti a loro volta a verifica.

## Le domande che rimangono

C'è una domanda che trovo persino più interessante di quella da cui sono partito:

**Come possiamo sapere che un modello ha bisogno di una procedura prima di fornirgliela?**

Se il recupero avviene soltanto per somiglianza, troviamo conoscenza pertinente. Ma non necessariamente conoscenza utile.

E se una procedura risolve un problema, come distinguiamo un metodo trasferibile da una scorciatoia che funziona soltanto sui casi già osservati?

Quanto del vantaggio dipende dal contenuto? Quanto dalla diagnosi? Quanto dalla selezione? Quanto dalla capacità del modello?

Infine: una memoria procedurale deve cercare di ricordare tutto quello che ha funzionato, oppure imparare anche quando è meglio non intervenire?

Non ho ancora risposte generali a queste domande.

Il laboratorio, però, ha già mostrato perché vale la pena porsele.

## Stato della ricerca e limiti

Procedural Memory Lab è un progetto di ricerca indipendente ancora in corso, non un articolo sottoposto a peer review.

La run principale comprende 39 task sintetici di correzione Python, con un tentativo per configurazione e una sola famiglia di modelli. Le verifiche complementari utilizzano talvolta campioni ancora più piccoli.

Le run numerate precedenti sono archiviate come log e non entrano in nessun risultato. Alcune valutazioni sono state utilizzate durante lo sviluppo delle procedure. Le prove in Aria appartengono a un contesto differente e non vanno aggregate con quelle del laboratorio.

Nessun log grezzo è presente nel repository pubblico. I numeri qui riportati derivano dagli artefatti locali della ricerca, ricalcolati da `log.jsonl`; non sono quindi riproducibili indipendentemente dalla sola versione pubblica.

Preferisco dichiarare questi limiti accanto ai risultati piuttosto che lasciare numeri apparentemente precisi senza spiegare da dove vengono.

## Licenza

Copyright © 2026 Ferdinando Gregorio Fernandez.

Tutti i diritti riservati. Il codice è visibile per valutazione di portfolio e di ricerca. Riuso, ridistribuzione e opere derivate non sono consentiti. Vedi [LICENSE](LICENSE).
