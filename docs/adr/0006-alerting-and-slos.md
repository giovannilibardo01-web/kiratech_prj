# ADR 0006: alerting azionabile basato sugli SLO, con un error budget esplicito sull'orario lavorativo

- Stato: proposta; il calendario dell'orario lavorativo deve essere confermato dal cliente.
- Data: 2026-11-05
- Decisori: SRE
- Revisori: Platform Engineering, Data Engineering, Network Security (consultati)

## Contesto

Due requisiti del cliente guidano questa decisione. Chi gestisce l'esercizio vuole essere allertato solo quando serve un intervento umano. I servizi di piattaforma (catalogo, GitOps, osservabilità) devono essere disponibili in orario lavorativo con **al massimo un'interruzione non pianificata per trimestre**.

Il monitor ping/HTTP esistente deve restare in servizio, in coesistenza, finché non si dimostra la parità. Con 30 cluster e molti ambienti self-service, chiamare il reperibile su sintomi grezzi di pod o nodi produrrebbe solo rumore.

Uno SLO del 99,9% in orario lavorativo è la lettura naturale del requisito di disponibilità. I moltiplicatori di burn rate convenzionali, 14,4× e 6×, sono stati ricavati per una finestra di 30 giorni 24×7, quindi il loro significato va ricalcolato su una finestra limitata all'orario lavorativo.

Questa finestra vale soltanto per i servizi di piattaforma. La produzione di Central è critica per il business: gli alert che hanno impatto sulla produzione chiamano il reperibile 24×7 e fanno riferimento a un NFR distinto di disponibilità della produzione (≥99,95% al mese, 24×7) definito in [06](../06-nfr-and-capacity.md).

## Opzioni considerate

Chiamare il reperibile su ogni soglia o evento di pod (opzione 1) è scartato: genera molto rumore e non ha legame con l'impatto sugli utenti. I soli check black-box di uptime (opzione 2) non bastano, perché non rilevano perdite di ingest, perdite di dati o guasti di sicurezza. L'opzione 3 è un paging a livelli basato su SLO ed error budget, con alert di burn rate multi-finestra, alert predittivi che aprono solo ticket e ownership esplicita.

Per la finestra dello SLO dell'opzione 3 abbiamo valutato tre varianti: (a) una finestra mensile in orario lavorativo, scartata per i motivi esposti nella decisione; (b) una finestra trimestrale in orario lavorativo, che è quella scelta; (c) una finestra 24×7, scartata perché il requisito riguarda solo l'orario lavorativo.

## Decisione

Scegliamo l'opzione 3 con una **finestra SLO trimestrale in orario lavorativo**.

### 1. SLI

Gli SLI sono il successo e la latenza delle richieste al catalogo, il successo e il ritardo della riconciliazione GitOps, la freschezza dell'ingest di osservabilità (età del canary ≤2 min) e il successo delle query di osservabilità. Ognuno è misurato solo in orario lavorativo.

### 2. Calendario ed error budget (assunzione da confermare)

Assumiamo come orario lavorativo la fascia 08:00–18:00, ora locale, nei giorni lavorativi: circa 22 giorni al mese, cioè 66 a trimestre. Si ottengono così **660 ore lavorative per trimestre**. Al 99,9% il budget è di 39,6 minuti per trimestre, riportato ogni mese rispetto a una quota proporzionale di 13,2 minuti.

### 3. Alert di burn rate

Gli alert di paging multi-finestra sono due: 14,4× su 1 h, con conferma su 5 m, e 6× su 6 h, con conferma su 30 m.

La quota di budget che ciascuno consuma dipende dalla finestra. Sulla finestra di riferimento di 30 giorni 24×7, pari a 720 ore, un burn a 14,4× che dura un'ora consuma il 2,0% del budget e uno a 6× che dura sei ore il 5,0%. Sul trimestre in orario lavorativo che abbiamo scelto, pari a 660 ore, gli stessi eventi consumano il 2,2% e il 5,5%. Sul mese in orario lavorativo, 220 ore, salirebbero al 6,5% e al 16,4%, ed è per questo che la variante mensile è scartata.

La finestra trimestrale conserva quindi il significato delle soglie convenzionali e coincide con il tetto trimestrale di interruzioni fissato dal cliente. Per i primi 90 giorni i moltiplicatori restano ipotesi da tarare.

### 4. Due vincoli separati

Lo SLO di disponibilità e il tetto di "≤1 interruzione non pianificata per trimestre" sono tracciati in modo indipendente.

Proponiamo di definire interruzione non pianificata un intervallo di almeno 5 minuti consecutivi di orario lavorativo in cui uno SLI di un servizio di piattaforma resta sotto la propria soglia, fuori da una finestra di manutenzione approvata. Ne segue che una sola interruzione più lunga di circa 40 minuti esaurisce da sola il budget trimestrale, e che per i servizi di piattaforma il progetto richiede un MTTR effettivo ben inferiore ai 40 minuti.

### 5. Eventi di disastro (proposta, richiede l'accettazione del CIO)

Un disastro dichiarato per la perdita di un sito è regolato dagli obiettivi RPO 1 h / RTO 4 h e dal runbook DR. Proponiamo di rendicontarlo a parte, senza conteggiarlo nello SLO di disponibilità: altrimenti un singolo evento di DR consumerebbe più di sei trimestri di budget.

### 6. Instradamento verso i quattro team

- SRE riceve gli alert su disponibilità, LGTM, ingest e dead-man's switch.
- Platform Engineering riceve quelli su GitLab, Flux, catalogo e admission.
- Data Engineering riceve quelli su object storage, broker, database, replica e ripristino.
- Network Security riceve quelli su firewall, PKI, IdP e flussi falliti.

Gli alert di sicurezza (buchi nell'audit, tentativi di spoofing del tenant, scadenza delle chiavi, drift delle policy di retention) hanno una severità indipendente e non vengono mai soppressi dallo stato degli SLO.

Sono obbligatori raggruppamento, inibizione e deduplicazione, le finestre di manutenzione e un URL di runbook su ogni alert.

### 7. Indipendenza

Le regole sono valutate dai ruler del backend, non da Grafana con token utente. L'Alertmanager di ciascun sito invia un heartbeat Watchdog a un dead-man's switch nell'altro sito.

## Conseguenze

Il modello funziona solo se esistono alcuni prerequisiti: un catalogo dei servizi con gli owner, SLI accurati, un calendario firmato (festività, fuso orario, gestione dell'ora legale), l'etichettatura degli incidenti e una revisione settimanale degli alert.

Gli SLI limitati all'orario lavorativo richiedono una serie di calendario nelle regole; l'implementazione PromQL esatta va verificata nel pilota.

La qualità del paging è accettata se almeno il 95% delle chiamate richiede davvero un intervento e se ci sono al massimo 2 chiamate false a settimana per team di reperibilità, misurate su un campione rappresentativo di 30 giorni dopo la taratura.

Il monitor legacy resta attivo in parallelo per due cicli di rilascio. I suoi check vengono dismessi uno alla volta dopo l'approvazione della parità, e in seguito si mantiene comunque una probe black-box indipendente.

## Validazione e trigger di revisione

I game day devono mostrare tre comportamenti: un guasto sintetico della piattaforma chiama il reperibile indicando owner e runbook (T-10); i flap di pod senza impatto non chiamano nessuno; il dead-man's switch chiama il reperibile quando si ferma l'Alertmanager di un sito (T-15).

Rivediamo la decisione se il calendario del cliente differisce da quello assunto, se l'MTTR misurato rende irrealistico il budget trimestrale o se il CIO rifiuta di trattare a parte gli eventi di disastro.
