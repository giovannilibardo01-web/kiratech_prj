# Perimetro, fonte di verità e assunzioni

## Tracciabilità dei requisiti

| ID | Requisito del cliente (parafrasato) | Risposta architetturale | Evidenza |
|---|---|---|---|
| REQ-01 | I team di business richiedono in autonomia ambienti dev/test dal catalogo | Golden path Backstage → workflow GitLab → namespace GitOps | Accettazione E2E del servizio in South |
| REQ-02 | Creazione, uso e distruzione affidabili; limiti alle risorse; alert solo quando serve un intervento | Riconciliazione, quote, instradamento basato sugli SLO, approvazioni per la garbage collection | Soak test, failure injection, audit settimanale della qualità degli alert |
| REQ-03 | Sicuro e conforme per default, con controlli immutabili | Kyverno in enforce, PSS Restricted, rete deny-by-default, ruoli sigillati, evidenze di conformità | Test negativi di admission e revisione delle eccezioni |
| REQ-04 | Audit della piattaforma e di Kubernetes conservato per almeno 1 anno | Relay di audit dedicato più doppio archivio immutabile a 400 giorni (copia in North e copia in South, compliance mode, amministrazione separata; [ADR 0010](adr/0010-audit-evidence-and-retention.md)) | Policy di lock, tentativo di cancellazione e test di recupero |
| REQ-05 | Prima l'osservabilità; il vecchio monitor ping/HTTP deve coesistere | Check black-box in doppia esecuzione; LGTM per sito | Report di copertura in parallelo e approvazione formale |
| REQ-06 | Tre siti e collegamenti tra siti limitati | Piani indipendenti per sito; flussi mTLS approvati sul firewall | Registro dei flussi; catture di pacchetti e ID delle modifiche firewall |
| REQ-07 | Disponibilità in orario lavorativo con al massimo 1 interruzione non pianificata a trimestre | SLO del 99,9% su una finestra trimestrale in orario lavorativo, più un tetto trimestrale separato alle interruzioni ([ADR 0006](adr/0006-alerting-and-slos.md)) | Report su SLO ed error budget, revisioni degli incidenti |
| REQ-08 | Perdita di Central: produzione e control plane con RPO 1 h / RTO 4 h | Controparti calde 1:1 in South con riserva; replica continua per classe di dato; servizi abilitanti in South; contratto di rilascio GitLab Geo + registry di South; backup immutabile in North ([05](05-reliability-and-dr.md)) | Drill T-11 sull'intero inventario, test di autonomia T-18 |
| REQ-09 | Gli ambienti self-service di South non hanno RPO | Namespace e dati di test usa e getta, ricreazione dichiarativa | Ricreazione da codice in ≤60 min |
| REQ-10 | Retention: metriche complete 30 giorni, capacità 13 mesi; log 30 giorni; trace 7 giorni | Mimir di sito con due tenant a retention separata; Loki TSDB; Tempo | Test di recupero di campioni in base all'età |
| REQ-11 | Circa 30 cluster Kubernetes / 1.500 pod in 18 mesi | 12 in Central + 18 in South; benchmark di scala per sito | Test di conformità della flotta e test di carico sull'ingest |
| REQ-12 | Preservare l'applicazione di riferimento single-cluster in corso e il golden path di South | Assorbirli e consolidarli senza sostituire i deliverable dei team | Checklist di integrazione dei workstream |
| REQ-13 | VMware, Kubernetes, GitLab Ultimate, Grafana, solo on-prem | OpenTofu/CAPV, Flux, GitLab, LGTM locale al sito, object storage on-prem | ADR di architettura |
| REQ-14 | Tutto come codice; nessun secret in Git | Progetti GitLab + Flux + secret esterni + PR per le policy | Secret scanning e ispezione della storia Git |
| REQ-15 | Tutto il traffico tra siti passa dal firewall ed è esplicito | Nessuna VPN east-west generalizzata; solo endpoint circoscritti e approvati | Matrice dei flussi e validazione di Network Security |
| REQ-16 | Codice C4 e rendering, ADR, NFR, roadmap, RACI, RAID, one-pager | Questo repository | Revisione del repository |

## Assunzioni esplicite (non sono fatti forniti dal cliente)

Ogni assunzione ha un owner e un punto di validazione. Prima che un acquisto o un progetto di produzione dipenda da essa, un ADR la registra come `Validated` (validata), `Rejected` (respinta) o `Revised` (rivista).

| ID | Assunzione | Owner | Validazione |
|---|---|---|---|
| A-01 | I 30 cluster comprendono tutti i cluster Kubernetes a regime, compresi management, osservabilità e 10 controparti DR calde dedicate | Platform Engineering | Inventario di Fase 0 (Q-01, Q-09) |
| A-02 | L'impronta di produzione è di 10 cluster in Central e 10 cluster standby speculari in South; numero e carichi sono provvisori e vanno ridimensionati dopo l'inventario | Platform Engineering | Fase 0 |
| A-03 | Data Engineering può fornire per ogni sito bucket compatibili S3, archivi immutabili con semantica compliance mode, un broker compatibile con Kafka e meccanismi DR per i database SQL/NoSQL | Data Engineering | Verifica di prodotto in Fase 0 (Q-04, R-17, R-18) |
| A-04 | Ogni sito attivo ha almeno 3 fault domain VMware indipendenti per host e storage e percorsi di rete ridondanti | Platform Engineering | Fase 0 |
| A-05 | L'RTT è di 10–20 ms, ma throughput e perdita di pacchetti non sono noti; replica e query tra siti dipendono dalle misure | Network Security | Test di throughput in Fase 0 (Q-05) |
| A-06 | Tutta la produzione sui cluster gestiti rientra in un inventario di recupero firmato. I carichi sui cluster legacy sono elencati tra le eccezioni del CIO; nulla è escluso implicitamente | SRE | Inventario firmato in Fase 0 |
| A-07 | I parametri di carico sono valori di scenario; la ripartizione tra Central e South è *derivata* da dove girano i 12 + 18 cluster e i 900 + 600 pod, quindi non è un'assunzione a parte. I valori sono: 250 serie per pod e 10.000 per cluster, scrape ogni 15 s; 2,5 B per campione con overhead di 1,5×; 0,28 GiB di log per pod al giorno più 80 GiB/giorno di log di piattaforma, compressione 0,35, overhead di 1,3×; 10.000 span/s con campionamento al 10%, 700 B per span; 20 GiB/giorno di audit | SRE | Pilota di Fase 1, con ogni parametro misurato (soglia ±30%) |
| A-08 | L'istanza GitLab attuale può passare a un primario supportato con un secondario Geo in South e replica del registry | Platform Engineering | Fase 0 / prova in Fase 2 |
| A-09 | Un secret manager per sito, HSM/KMS e una CA emittente possono funzionare in South in modo indipendente ([ADR 0011](adr/0011-south-recovery-dependencies.md)) | Network Security | Fase 0 (Q-08) |
| A-10 | Valgono i controlli aziendali standard; qualsiasi obbligo di settore o di residenza dei dati richiede una valutazione di Legal e del CISO | CISO | Prima dell'accettazione del CISO (Q-11) |
| A-11 | Il calendario dell'orario lavorativo è 08:00–18:00 ora locale, con ~22 giorni lavorativi al mese: 660 h a trimestre per la finestra dello SLO | SRE | Definizione SLI/SLO firmata (Q-06) |
| A-12 | La riserva DR si basa su 900 pod di produzione con richieste di 0,5 vCPU / 1 GiB; i dati di produzione da replicare e sottoporre a backup sono 20 TiB | SRE + Data Engineering | Richieste e volumi di dati misurati in Central in Fase 0 |
| A-13 | L'overhead per cluster è di 3 VM di control plane × 4 vCPU / 16 GiB | Platform Engineering | Dimensionamento del cluster pilota |
| A-14 | I tempi di approvvigionamento sono di 8–16 settimane per storage, host del broker, HSM/KMS e riserva di South | SRE | Piano degli acquisti in Fase 0 |
| A-15 | Il payload sul broker è di ~10 B per campione, con retention di 24 h | Data Engineering | Misura nel pilota |
| A-17 | I charter dei quattro team non indicano un owner per identità, PKI, secret manager, HSM/KMS e chiavi di firma; si *assume* che ne sia owner Network Security, trattandoli come infrastruttura di sicurezza. L'alternativa è Platform Engineering come owner, con Network Security consultato. La stessa assunzione copre SRE come owner dell'operatività di LGTM e Data Engineering come owner di object storage e broker (A-03) | CISO + Network Security | Fase 0 (Q-18) |
| A-18 | L'incremento HA di GitLab in Central più il secondario Geo in South richiede ≈ 48 vCPU; la copia Geo è di 10 TiB e il registry di South di 5 TiB | Platform Engineering | Dimensionamento secondo la reference architecture di GitLab in Fase 0 |
| A-19 | Circa il 25% delle richieste di produzione gira sia sui cluster legacy sia sui nuovi per circa un anno | Platform Engineering | Piano delle coorti in Fase 5 |
| A-16 | I costi unitari nei casi basso, base e alto (€ per vCPU-anno, € per TiB-anno, abbonamenti, tariffa FTE; [10](10-cost-and-tco.md)) sono illustrativi, non quotazioni | CFO | Tariffe del cliente e proposte dei vendor prima dell'investimento |

## Che cosa è in perimetro e che cosa è rinviato

Sono in perimetro l'architettura e la migrazione dell'osservabilità, del control plane dell'IDP, della gestione della flotta Kubernetes e della baseline di sicurezza; il DR, il dimensionamento, il TCO e i runbook; l'allineamento non distruttivo con i workstream esistenti.

Sono rinviati alla discovery la distinta esatta di CPU e storage, gli override Helm di produzione, i prezzi dei vendor, i backup specifici per database, la configurazione hardware, l'acquisto dei prodotti di sicurezza e l'approvazione delle procedure di failover dei siti. Le proposte non vanno considerate controlli già implementati.
