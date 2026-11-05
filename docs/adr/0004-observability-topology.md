# ADR 0004: LGTM multi-tenant locale a ogni sito, architettura di ingest e servizi di supporto

- Stato: proposta, in attesa dei test di carico e di guasto del pilota.
- Data: 2026-11-05
- Decisori: SRE
- Revisori: Data Engineering, Network Security, Platform Engineering (consultati)
- Documenti correlati: [approfondimento sull'osservabilità](../03-observability-deep-dive.md), [ADR 0006](0006-alerting-and-slos.md), [ADR 0008](0008-retention-tiering.md), [ADR 0012](0012-telemetry-tenancy-and-read-isolation.md)

## Contesto

L'osservabilità è la prima priorità del cliente. Oggi esiste solo un monitoraggio black-box ping/HTTP e i log non vengono elaborati. Lo stack Grafana è obbligatorio e tutti i componenti e i dati devono restare on-prem.

Gli obiettivi di retention sono 30 giorni a piena risoluzione per le metriche, più 13 mesi per la pianificazione della capacità; 30 giorni per i log; 7 giorni per le trace; almeno un anno per l'audit della piattaforma e di Kubernetes. La produzione deve continuare a rilevare i problemi e a chiamare il reperibile anche durante i guasti tra siti e dopo la perdita di Central.

La piattaforma è pianificata per circa 30 cluster e 1.500 pod. Il volume di ingest che ne deriva è di circa 1,0 M di serie attive e 67.500 campioni al secondo, più circa 500 GiB al giorno di log (valori modellati in [06](../06-nfr-and-capacity.md)).

## Opzioni considerate

### Decisione 1: collocazione

La soluzione più economica è un unico LGTM in Central, verso cui inoltrano tutti i siti (opzione 1). Ha però tre difetti: la telemetria di South dipende da Central e dal collegamento, il traffico ad alto volume attraversa i firewall e la perdita di Central rende cieco proprio il sito di ripristino. All'estremo opposto, un LGTM completo in tutti e tre i siti (opzione 2) dà la massima autonomia, ma North è un sito di backup senza carichi e un terzo stack non si giustifica.

L'opzione 3 prevede data plane LGTM separati in Central e in South, audit immutabile e backup in North e viste di flotta federate in sola lettura. Ha più componenti, in cambio del miglior isolamento dei guasti e del minor carico sulla WAN.

### Decisione 2: architettura di ingest

I fatti di prodotto citati qui sono stati verificati il 2026-11-05 e vanno ricontrollati quando si fissano le versioni.

L'opzione 1 è Mimir in architettura classica (ingester con RF3) con Tempo monolitico. Non richiede un broker, ma Mimir 3.0 indica l'ingest storage come architettura preferita e prevede di deprecare quella classica; Tempo monolitico è un singolo processo e Tempo 3.0 ha eliminato la modalità monolitica scalabile.

L'opzione 2 è Mimir 3.x con ingest storage e Tempo 3.x a microservizi, che condividono un unico servizio di broker compatibile Kafka per sito. Segue la direzione upstream, e il broker fornisce la durabilità delle scritture (Tempo gira con RF1). Il prezzo è un servizio di supporto (backing service) stateful in più per sito, e un'interruzione del broker blocca le scritture di metriche e trace.

## Decisione

Per la collocazione scegliamo l'opzione 3. Ogni sito attivo ha un proprio cluster di osservabilità, su cui girano i collector Alloy, un telemetry gateway autenticato in mTLS, Mimir, Loki e Tempo scalati orizzontalmente su object storage compatibile S3 **locale al sito**, Grafana in HA, ruler e Alertmanager, e un percorso di metamonitoraggio indipendente tra i siti. I siti non condividono alcun bucket, ring o database attivo in scrittura. Le viste di flotta leggono il sito remoto attraverso il suo query gateway e, se il collegamento cade, falliscono in modo sicuro.

Per l'ingest scegliamo l'opzione 2, a condizione che Data Engineering si impegni a gestire il broker. Ciascun sito richiede questi servizi di supporto:

| Servizio di supporto per sito | Fornito da | Note |
|---|---|---|
| Object storage compatibile S3 (un bucket per segnale) | Data Engineering | ≥3 domini di guasto |
| Broker compatibile Kafka (3 broker, RF3) | Data Engineering | Prodotto da definire; la documentazione Grafana cita come esempi Apache Kafka e Redpanda |
| PostgreSQL in HA per Grafana | Data Engineering | Istanza separata per sito |
| Cache (Memcached) | SRE | Stateless, parte del rilascio LGTM |
| Volumi persistenti | Platform Engineering | Storage class CSI del sito |
| IdP e PKI | Network Security | Ripristinabili in ogni sito senza Central |

SRE gestisce i componenti LGTM e Network Security approva ogni flusso tra siti.

Tenancy e isolamento in lettura seguono [ADR 0012](0012-telemetry-tenancy-and-read-isolation.md): il tenant è impostato dai gateway a partire dall'identità derivata, mai dagli header inviati dal client.

Loki usa TSDB con retention per tenant applicata dal compactor. Il tenant locale `security` di Loki è una copia consultabile per 30 giorni e **non** il sistema di riferimento per l'audit, che passa da un relay separato verso l'archivio immutabile di North (vedi [04](../04-security-and-tenancy.md)).

La baseline di versione è Mimir 3.x, Tempo 3.x e Loki 3.x; Grafana, Alloy e Prometheus vengono fissati all'avvio del pilota. Le versioni esatte saranno congelate in una bill of materials firmata prima della Fase 2 e qui non vengono dichiarate.

## Conseguenze

Due cluster di osservabilità, due object store, due broker e due database Grafana comportano una spesa più alta e due domini di SLO da gestire. In cambio la telemetria ad alto volume resta fuori dalla WAN e ogni sito conserva la capacità di rilevamento durante una partizione.

La disponibilità del broker condiziona le scritture di metriche e trace. I collector bufferizzano su disco (WAL di Alloy), per cui il dimensionamento del broker e dei dischi WAL entra nel modello di capacità.

Sull'object storage le regole di lifecycle non devono cancellare oggetti referenziati dagli indici: la retention la applicano i compactor.

Il metamonitoraggio non deve condividere il percorso di guasto che sorveglia. Si appoggia quindi a un dead-man's switch e a probe nell'altro sito e, durante la coesistenza, al monitor black-box legacy.

Dopo la perdita di Central, South deve assorbire a pieno ritmo l'ingest della produzione ripristinata; solo lo *storico* di Central è facoltativo (dimensionamento in [06](../06-nfr-and-capacity.md)).

## Validazione e trigger di revisione

Il pilota, con dati sintetici su due cluster, deve dimostrare:

- un picco di ingest pari a 3×;
- l'iniezione di guasti su broker, ingester e object store senza perdite silenziose;
- l'isolamento tra i siti;
- il rifiuto dei tentativi di spoofing del tenant in scrittura e in lettura;
- il rispetto della retention su dati di prova predisposti;
- il paging da parte del dead-man's switch.

Se Data Engineering non è in grado di gestire un broker entro la fine del pilota della Fase 1 (R-17), si torna all'opzione 1 della Decisione 2 e si registra un nuovo ADR che sostituisce questo. La decisione va rivista anche se i volumi misurati si discostano dal modello di oltre il ±30% o se una versione di prodotto fissata cambia l'architettura.
