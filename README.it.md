<h1 align="center">Procedural Memory Lab</h1>

<p align="center">I modelli linguistici piccoli migliorano recuperando procedure, o rivedono soltanto una risposta simile?</p>

<p align="center"><a href="README.md">English</a> · <b>Italiano</b></p>

<p align="center"><img src="docs/images/cognitive-city.gif" width="760" alt="Una quest rigiocata in Cognitive City"></p>

<p align="center"><sub>Una quest rigiocata in Cognitive City. Quattro agenti ricevono lo stesso bug a casa. I due che usano il recupero passano prima dalla biblioteca, poi tutti scrivono una soluzione al negozio e fanno i test all'ospedale.</sub></p>

## Di cosa si tratta

È un progetto di ricerca indipendente. Volevo capire se un modello più economico può avvicinarsi a uno più grande quando può consultare ciò che è stato imparato nei tentativi precedenti, e come distinguere un vero apprendimento da una semplice copia.

Il banco di prova è piccolo di proposito: funzioni Python con bug reali, controllate da `pytest`. Ogni compito viene eseguito in quattro modi.

| Configurazione | Risolutore | Contesto in più |
|---|---|---|
| A, Expert | modello più grande | nessuno |
| B, Small | modello più piccolo | nessuno (la base di confronto) |
| F, Skill Library | modello più piccolo | una procedura generale recuperata dalla libreria |
| C, Solution Bank | modello più piccolo | la soluzione corretta di un caso simile |

Confrontando F con B vedo se il recupero aiuta. Confrontando F con C capisco perché: se la procedura si generalizza, F deve reggere dove una risposta copiata non basterebbe.

## Cosa ho trovato

Nei primi cinque run completi la Skill Library è finita avanti rispetto al modello piccolo ogni volta, con 7,8 punti di accuratezza in più su 116 tentativi. È un risultato incoraggiante e nient'altro. I run non sono repliche pulite, la libreria è cambiata lungo la strada e il vantaggio è disomogeneo tra le skill. Nel run iniziale più grande solo due dei dieci pattern coperti hanno portato un beneficio.

Il risultato più utile è stato un controllo, non un punteggio. Una skill sul confronto tra numeri in virgola mobile sembrava scegliere una tolleranza, ma poteva ripetere un numero scritto nella procedura. Ho cambiato quel numero e la risposta lo ha seguito 12 volte su 12. Cambiare un numero non correlato non ha fatto nulla, 6 volte su 6. Il modello sceglieva la regola giusta e poi recitava un valore preso da essa. Dopo aver riscritto la procedura chiedendo una derivazione, ha calcolato tolleranze su sette ordini di grandezza.

<p align="center"><img src="docs/images/epsilon-lab.png" width="760" alt="Il controllo sulla tolleranza"></p>

## Come è organizzato

- `domain/` contiene i compiti, le famiglie di bug e i controlli.
- `agents/` costruisce il prompt e fa girare il risolutore.
- `librarian/` recupera, dosa e confronta le procedure.
- `cheater/` è la banca delle soluzioni.
- `experiment/` esegue le configurazioni affiancate.
- `verification/` contiene i controlli che distinguono l'apprendimento dalla copia.
- `city/` trasforma un run concluso nella pagina mostrata sopra.
- `library/books/` è la libreria delle procedure.

I nomi da gioco di ruolo (Quest, Book, Librarian) sono solo etichette per idee ordinarie: compiti, procedure memorizzate e recupero.

## Avvio

Serve Python 3.11 o superiore. Le dipendenze si installano dalla cartella di lavoro superiore e i comandi vanno lanciati dalla cartella che contiene `cognitive_rpg`, così il pacchetto si può importare.

```sh
python -m pip install -r requirements.txt
python -m cognitive_rpg.settings_wizard
python -m cognitive_rpg.experiment.experiment_0
```

Per sviluppare ci sono adattatori simulati che non richiedono chiamate a pagamento. Le esecuzioni reali richiedono le chiavi dei provider, che la configurazione chiede e non salva mai nel repository.

## Stato

Il lavoro è in corso e non è un articolo sottoposto a revisione. I log completi dei run non fanno parte di questo repository pubblico, quindi i numeri qui sopra sono una mia lettura di quei log.

## Licenza

Copyright © 2026 Ferdinando Gregorio Fernandez. Tutti i diritti riservati. Il codice è visibile per valutazione di portfolio e di ricerca. Riuso, ridistribuzione e opere derivate non sono consentiti. Vedi [LICENSE](LICENSE).
