# NFR misurabili e modello di capacità dell'osservabilità

> La versione impaginata di questa nota, in tre pagine, è `deliverables/NFR_Capacity_Note.pdf`. Questo Markdown aggiunge le formule e il dettaglio della validazione e non è soggetto al limite di stampa delle tre pagine.
>
> Ogni quantità è una **stima modellata**, riproducibile con `python tools/capacity_model.py --full`; nessuna è un dato misurato presso il cliente. Le assunzioni su cui si basano sono elencate in [01](01-scope-and-assumptions.md).

## 1. Target contrattuali espressi come NFR verificabili

| Requisito | Accettazione misurabile proposta | Metodo / owner |
|---|---|---|
| Disponibilità della piattaforma in orario lavorativo | SLI di catalogo, GitOps e osservabilità **≥99,9%** per trimestre solare di orario lavorativo (assunto 08:00–18:00, ~66 giorni lavorativi = 660 h, quindi 39,6 min di budget a trimestre, con report mensile) e ≤1 interruzione non pianificata a trimestre (≥5 minuti consecutivi di orario lavorativo sotto la soglia dello SLI, fuori dalle manutenzioni approvate): due vincoli indipendenti. I disastri con perdita di sito dichiarata sono governati da RPO/RTO, non da questo SLO (proposta da sottoporre all'accettazione del CIO; [ADR 0006](adr/0006-alerting-and-slos.md)) | Canary sintetici e strumentazione dei servizi; SRE. Il cliente conferma calendario, fuso orario e festività |
| Disponibilità della piattaforma di produzione (24×7): proposta, perché la produzione di Central è business critical | API server dei cluster di produzione, ingress e admission ≥99,95% al mese, misurata 24×7 (~21,9 min di budget). Gli alert con impatto sulla produzione chiamano il reperibile 24×7; la finestra dell'orario lavorativo vale solo per i servizi di piattaforma della riga precedente. Gli SLO applicativi sono fissati da ciascun service owner a partire dai template di SLO della piattaforma | Probe sintetici per ogni cluster di produzione; SRE |
| Perdita di Central | **RPO ≤60 min e RTO ≤240 min** dopo dichiarazione e fencing, per tutta la produzione inventariata di Central sui cluster gestiti dalla piattaforma e per il control plane della piattaforma. I workload ancora su cluster legacy sono elencati con la loro capacità reale, sotto eccezioni firmate dal CIO. Percorso progettato di 175 min (modellato); obiettivo interno ≤180 min. Nessun restore sul percorso critico per i dati in ambito ([05](05-reliability-and-dr.md) §7) | Drill sull'intero inventario prima dell'impegno in produzione, poi ogni anno; drill trimestrali per coorte; tempi mensili per singolo passo. RPO misurato per dataset. Owner: SRE, Data Engineering, Platform Engineering |
| Self-service: nuovo team | Onboarding standard di un team non di produzione, compresa la revisione di identità e budget, ≤1 giorno lavorativo; namespace dopo la richiesta approvata p95 ≤15 min | Timestamp di Backstage e GitLab; Platform Engineering |
| Self-service: dismissione | Ambiente marcato come scaduto, utente avvisato e risorse non stateful rimosse p95 ≤30 min dopo il periodo di grazia; controllo della retention dei dati applicato; TTL ≤30 giorni per dev e ≤90 giorni per test, imposto dallo schema di richiesta | Log del controller e di GitOps; Platform Engineering / Data Engineering |
| Affidabilità del ciclo di vita del catalogo | ≥99% delle richieste di creazione e dismissione completate senza intervento manuale, misurato ogni mese. Zero risorse orfane: ogni dismissione emette un report, e un report non vuoto apre un ticket. ≥20 richieste concorrenti rispettano il target p95 ≤15 min. Le richieste oltre la quota del team, o oltre il budget di capacità non di produzione di South, sono rifiutate in validazione invece di fallire durante la riconciliazione. Una creazione fallita torna a un namespace vuoto o a una merge request chiusa | Timestamp di Backstage e GitLab, report di dismissione, test di carico con richieste sintetiche; Platform Engineering |
| Sicurezza | 100% delle creazioni di risorse in produzione verificate da admission control in modalità enforce; 100% dei cluster sottoposti a scansione di drift almeno una volta al giorno; zero esenzioni di policy concesse dai tenant | Test negativi e di conformità; CISO, Platform Engineering |
| Audit | Almeno 365 giorni conservati; policy di archivio di 400 gg; doppio archivio immutabile (copia in North e in South); verifica giornaliera dell'integrità; ritardo dell'archivio ≤5 min; recupero entro 4 h ([ADR 0010](adr/0010-audit-evidence-and-retention.md)) | T-09 esteso, alla presenza del CISO; SRE |
| Retention | Metriche grezze 30 gg; metriche selezionate di capacity planning 13 mesi solari; log operativi 30 gg; trace 7 gg | Probe e query di retention, test di lifecycle; SRE |
| Freschezza della strumentazione | 99,9% dei campioni degli SLO critici consegnati al piano di query entro 2 minuti a regime; ingestione dei log p95 ≤60 s, trace p95 ≤60 s | Canary sintetici e test di backpressure; SRE |
| Qualità degli alert | ≥95% di page azionabili, ≤2 falsi page a settimana per team reperibile, 100% delle route P1 testate | Revisione degli alert e campionamento degli incidenti; SRE |
| Scala | 30 cluster e 1.500 pod a regime; burst breve di 3× sull'ingest e margine di 1,5× sull'inventario | Pilota su 2 cluster più generatore di carico; SRE |
| Sicurezza delle modifiche | Rilascio in produzione tramite MR e controlli di policy, rollout e rollback esercitati, 100% delle modifiche attribuibili | Audit di GitLab e riconciliazione di Flux; Platform Engineering |

## 2. Volumi di telemetria (intera fleet)

Le metriche partono da due componenti: 1.500 pod × 250 serie = 375.000 serie, a cui si sommano 30 cluster × 10.000 serie di infrastruttura = 300.000 serie. La base di 675.000 serie, con il 50% di margine, arriva a **1.012.500 serie attive**. Con uno scrape ogni 15 s si ottengono 67.500 campioni/s, cioè 5,832 miliardi di campioni al giorno. Lo storage è 2,5 B per campione × 1,5 di overhead di blocchi e indici × 30 giorni × 1,5 di margine di provisioning, per un totale di 0,984 TB logici.

Il livello di capacità conta 40.000 serie in allowlist con intervallo di 300 s per 395 giorni, cioè 4,55 miliardi di campioni. A 3 B per campione con overhead 2 si ottengono 27,3 GB, che con un margine di 1,5× diventano 40,95 GB: è il valore usato in tutti i totali. La quota del bucket è fissata a 50 GB come allocazione arrotondata. Mimir non effettua downsampling automatico, quindi questo livello è prodotto con recording rule federate ([ADR 0008](adr/0008-retention-tiering.md)).

Per i log, 1.500 pod × 0,28 GiB più 80 GiB della piattaforma danno **500 GiB/giorno grezzi**. Applicando la compressione (× 0,35), l'overhead (× 1,3), i 30 giorni di retention e il margine (× 1,5) si arriva a 10,0 TiB logici.

L'audit vale 20 GiB/giorno grezzi × 0,35 × 400 giorni × 1,5 = 4,1 TiB logici per copia, con due copie (North e South). Il volume va rimisurato con la policy di audit approvata dal CISO.

Per le trace, 10.000 span/s con campionamento al 10% lasciano 1.000 span/s conservati; moltiplicati per 700 B, 7 giorni e 1,5 di margine danno 0,64 TB logici.

## 3. Storage per sito

La ripartizione tra i siti deriva dalla topologia, non da un'ipotesi. Central gestisce 12 cluster e i 900 pod di produzione; South gestisce 18 cluster (tra cui i suoi 10 cluster DR, inattivi) e i 600 pod non di produzione. In condizioni normali, quindi, a Central va il 51% delle metriche, il 57% dei log e il 60% delle trace (`site_shares()` nel modello).

Dopo un failover l'ingest di South è il 100% della fleet, ma il 100% della telemetria archiviata si raggiunge solo 30 giorni dopo il cutover: quel valore è perciò un limite superiore.

| Sito | Logico (TiB) | Fisico ×1,5 | ×2 | ×3 | Contenuto |
|---|---:|---:|---:|---:|---|
| Central | 6,51 | 9,8 | 13,0 | 19,5 | Quota di Central di metriche, log, trace e livello di capacità |
| South, normale | 9,13 | 13,7 | 18,3 | 27,4 | Quota di South + **seconda copia di audit** (4,1) + copia di capacità di Central |
| South, 30 giorni dopo il failover (limite superiore) | 15,63 | 23,4 | 31,3 | 46,9 | 100% operativo + copia di audit + copia di capacità |
| North | 4,10 | 6,1 | 8,2 | 12,3 | Archivio di audit; i backup di produzione si aggiungono (§5) |

I moltiplicatori fisici rappresentano scenari di erasure coding o di replica, non valori dei fornitori. Sono calcolati a parte, in §5, i dischi del broker e i volumi locali (1,5 TiB in totale), la copia GitLab Geo, il registry di South e i dati di produzione. Non è incluso lo spazio di appoggio per i restore.

## 4. Compute per sito

I coefficienti del percorso di scrittura di Mimir vengono dalla guida di Grafana *Planning Grafana Mimir capacity* (consultata il 2026-11-05). Il distributor richiede 1 core e 1 GB ogni 25.000 campioni/s; l'ingester richiede 1 core, 2,5 GB di RAM e 5 GB di disco ogni 300.000 serie in memoria, dove le serie in memoria sono le serie attive × RF 3. Grafana li definisce rapporti approssimativi e i suoi runbook citano circa 2 M di serie per ingester, quindi li trattiamo come un limite superiore conservativo.

Per Loki usiamo il livello più piccolo della tabella *Size the cluster* di Grafana (p90, modalità microservizi). I nostri ≈0,5 TB/giorno sono sotto il primo livello, quindi anche questa scelta è conservativa.

Gli altri componenti usano le dotazioni fisse per sito definite in `SizingAssumptions` ([`tools/capacity_model.py`](../tools/capacity_model.py)).

| Componente | Central (51% delle metriche) | South normale (49%) | South dopo il failover (100%) |
|---|---:|---:|---:|
| Distributor Mimir (core; burst ×3) | 1,38 (4,14) | 1,32 (3,96) | 2,70 (8,10) |
| Ingester Mimir (core / RAM GB / disco GB) | 5,17 / 12,9 / 25,9 | 4,95 / 12,4 / 24,8 | 10,12 / 25,3 / 50,6 |
| Percorso di lettura e manutenzione di Mimir (querier, frontend, store-gateway, compactor, ruler, Alertmanager) | 12,75 vCPU / 35,5 GiB | Idem | Idem |
| Loki (livello più piccolo) | 30 vCPU / 50 GiB | Idem | Idem |
| Tempo, Grafana, gateway, Memcached, metamonitoraggio, più il relay di audit (contato qui per il dimensionamento del sito, anche se gira nel management cluster) | 19,5 vCPU / 55 GiB | Idem | Idem |
| Totale LGTM | 68,8 vCPU / 154 GiB | 68,5 / 153 | 75,1 / 167 |
| Con il 25% di margine per la perdita di un nodo | 86 vCPU / 192 GiB | 86 / 192 | 94 vCPU / 208 GiB |
| Broker compatibile Kafka (3 nodi, Data Engineering) | 12 vCPU / 48 GiB; scrittura 0,76 MB/s (2,29 a ×3); ~132 GB di disco per broker | 12 / 48; 0,61 MB/s (1,83); ~105 GB | 12 / 48; 1,38 MB/s (4,12); ~238 GB per broker |

**South è dimensionato sulla colonna del failover: ~94 vCPU / 208 GiB di LGTM più il broker.** È l'unico dimensionamento difendibile, perché la produzione ripristinata emette la sua telemetria in South.

Il burst di 3× previsto dagli NFR riguarda i distributor e il percorso di scrittura del broker, che scalano orizzontalmente fino ai valori ×3 della tabella. Gli ingester sono dimensionati sulle serie attive, che un burst breve non cambia. Il burst va verificato nel test T-06 del pilota.

Il throughput del broker assume 10 B per campione (A-15), una retention di 24 h e RF 3. Entrambi i valori vanno misurati nel pilota.

## 5. Fleet e riserva DR (input al costo del programma)

| Voce | vCPU / GiB | Base di calcolo |
|---|---:|---|
| Control plane, 30 cluster | 360 / 1.440 | 3 VM × 4 vCPU / 16 GiB per cluster (A-13) |
| di cui 10 cluster DR | 120 / 480 | Un DR a livelli risparmierebbe 36 / 144; un DR in pool risparmierebbe 84 / 336 ([ADR 0002](adr/0002-multi-site-topology.md)) |
| Collector di cluster | 30 / 60 | 1 vCPU / 2 GiB per cluster |
| Workload di management (entrambi i siti) | 32 / 128 | CAPI/CAPV, Flux, Backstage, runner, OpenTofu |
| Servizi abilitanti di South | 48 / 192 | IdP, CA, secret manager, DNS, registry, appliance vCenter ([ADR 0011](adr/0011-south-recovery-dependencies.md)) |
| Incremento per GitLab HA (Central) + secondario Geo (South) | 48 / 192 | A-18; storage: 10 TiB di copia Geo e 5 TiB di registry in South |
| Riserva DR di South per la produzione | 540 / 1.080 | 900 pod di produzione × richieste di 0,5 vCPU / 1 GiB × 1,2 di margine (A-12). Dopo l'inventario viene sostituita dalle richieste misurate della produzione di Central |
| Non produzione in South | 150 / 300 | 600 pod × 0,25 vCPU / 0,5 GiB |
| Sovrapposizione durante la migrazione (una tantum) | 112,5 vCPU-anno | Durante la migrazione il 25% delle richieste di produzione gira sia sui cluster legacy sia sui nuovi, per circa un anno (A-19) |
| Dati di produzione replicati in South / sottoposti a backup in North | 20 TiB / 40 TiB logici | A-12; Data Engineering conferma in Fase 0 |

La riserva DR è la singola voce di compute più grande, circa il 38% dei ~1.410 vCPU incrementali del programma. È un **vincolo di finanziamento bloccante**: senza di essa l'RTO di 4 h non è credibile.

## 6. Validazione, soglie e controllo delle previsioni

Le settimane 1–4 del pilota (Fase 1, che inizia dopo la discovery della Fase 0) servono a misurare sui due cluster pilota le serie attive e la cardinalità, i byte di log compressi al giorno, gli span dopo il campionamento, il tasso di eventi di audit con la policy approvata, i byte per campione sul broker, il carico di query, la banda e la latenza dei collegamenti.

Nelle settimane 4–8 il pilota passa allo stress. Si sostiene un ingest di metriche e log a 3× per almeno 30 minuti, si fermano un ingester, il broker e l'endpoint dell'object storage, e si misurano il replay del WAL, il p99 delle query e il tempo necessario a far scattare gli alert.

Nei mesi 3–5 si verifica la retention: il costo per tenant si calcola dalle dimensioni reali dei blocchi, si esegue una prova di retention accelerata su 35 giorni e si controlla che la cancellazione su WORM venga rifiutata.

Da lì in poi, ogni mese si confrontano previsione e consuntivo con una **soglia di scostamento del ±30%**. Se la soglia viene superata, storage, compute e collegamenti si riprevedono prima di consentire ulteriore crescita.

Resta un vincolo non ancora dimostrato. Un RTT di 10–20 ms non dice nulla sulla banda, e l'RPO di 1 h dipende dal backlog di replica misurato. Un RTO di 4 h dichiarato senza capacità dei collegamenti, senza servizi di identità in South e senza una riserva South finanziata non è accettato.
