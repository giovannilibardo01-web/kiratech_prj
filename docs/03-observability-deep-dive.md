# Osservabilità: architettura di dettaglio dell'area prioritaria

L'osservabilità è la prima priorità del cliente, e per questo è la parte del progetto descritta con più dettaglio nel repository. Poggia su cinque decisioni: la topologia e l'architettura di ingest ([ADR 0004](adr/0004-observability-topology.md)), gli SLO e l'alerting ([ADR 0006](adr/0006-alerting-and-slos.md)), i livelli di retention ([ADR 0008](adr/0008-retention-tiering.md)), la scelta tra OSS e supporto commerciale ([ADR 0009](adr/0009-commercial-support.md)), la tenancy e l'isolamento del percorso di lettura ([ADR 0012](adr/0012-telemetry-tenancy-and-read-isolation.md)). La vista C4 dei componenti è [07-observability-components](../architecture/rendered/07-observability-components.svg).

Il testo distingue lo stato di ciascuna affermazione. Le decisioni di progetto documentate sono la norma e vengono segnalate solo dove il contesto non basta a riconoscerle. I numeri modellati sono indicati come stime e rimandano a [06](06-nfr-and-capacity.md). Ciò che dipende da una versione di prodotto, da un fornitore o da un fatto del cliente è indicato come da verificare, e va confermato nel pilota. Le evidenze misurate sarebbero dichiarate come tali, ma **nulla in questo repository è ancora stato testato**.

## 0. Intento progettuale e punti non negoziabili

1. Il piano dei segnali è locale a ogni sito. Central e South raccolgono, ingeriscono, archiviano, interrogano e valutano gli alert sulla propria telemetria: un incidente circoscritto a un sito o un guasto del collegamento Central↔South non devono fermare né la rilevazione né il paging locali. North non ospita LGTM; contiene l'archivio di audit immutabile e i backup.
2. L'identità del tenant viene derivata, mai dichiarata. La piattaforma la ricava dai metadati Kubernetes e dall'identità autenticata del collector: **nessun workload può scegliere il proprio tenant**, né sul percorso di scrittura né su quello di lettura.
3. L'alerting non dipende dal percorso di query usato dalle persone. Ruler e Alertmanager valutano le regole all'interno del backend; la perdita di Grafana, del query gateway o dell'IdP degrada le dashboard, non il paging.
4. Il sistema di monitoraggio è osservato dall'esterno. Ogni stack LGTM è sorvegliato da un dead-man's switch collocato nell'*altro* sito, da probe di salute tra i siti e, durante la coesistenza, dal tool black-box legacy.
5. Il monitoraggio black-box legacy resta in servizio. Si spegne un check alla volta, solo dopo che la parità è dimostrata e l'owner l'ha firmata (§11).
6. L'evidenza di audit non è logging operativo. Gli eventi di audit della piattaforma e di Kubernetes viaggiano su un percorso separato, con conferma di ricezione, verso un archivio immutabile; Loki ne conserva soltanto una copia ricercabile di 30 giorni.

## 1. Topologia: cosa gira dove

Central ospita un cluster di osservabilità dedicato con Mimir, Loki, Tempo, Grafana, il telemetry gateway, il query gateway, ruler e Alertmanager, più lo scraper di metamonitoraggio che sorveglia South. I collector Alloy girano in ogni cluster di Central (il management cluster e i 10 cluster di produzione) e inviano la telemetria soltanto al gateway di Central.

South ha un cluster di osservabilità dedicato con gli stessi componenti e con lo scraper di metamonitoraggio che sorveglia Central. Riceve tutta la telemetria di South e, dopo un failover per perdita di Central, anche quella della produzione ripristinata (il dimensionamento è in [06](06-nfr-and-capacity.md) §2).

North non ha LGTM: ospita soltanto l'archivio di audit immutabile, alimentato da un percorso di relay separato, e le destinazioni dei backup.

Tra i siti non c'è alcun bucket, ring o database condiviso e attivo in scrittura. Il traffico tra siti si limita a:

- letture federate autorizzate (F-06 e F-07);
- probe di metamonitoraggio (F-10);
- relay di audit verso North (F-04);
- seconda copia di audit da Central a South (F-11);
- copie selezionate di blocchi per il DR (F-05);
- heartbeat del Watchdog verso il dead-man's switch dell'altro sito (F-12).

I flussi sono elencati in [12](12-firewall-flows.md).

## 2. Percorso di scrittura per segnale

La tabella riporta, per ciascun segnale, da dove nasce la telemetria, come si ricava il tenant, che cosa controlla il gateway e come si comporta il sistema quando un componente a valle non è disponibile.

| | Metriche | Log | Trace | Audit (compliance) |
|---|---|---|---|---|
| Sorgente | kubelet/cAdvisor, node-exporter, kube-state-metrics, control plane, `/metrics` delle applicazioni | stdout/stderr dei container, log dei servizi di piattaforma | SDK OpenTelemetry nelle applicazioni (campionamento esplicito) | Backend di audit del kube-apiserver, eventi di audit di GitLab, log di accesso del secret manager, decisioni di Flux e Kyverno |
| Collector | Collector Alloy di cluster (repliche HA), in un namespace della piattaforma | DaemonSet Alloy (lettura dei file locale al nodo) | Receiver OTLP Alloy locale al nodo | Shipper sui nodi del control plane → relay di audit del sito nel management cluster, **non** il gateway LGTM ([ADR 0010](adr/0010-audit-evidence-and-retention.md)) |
| Come si ricava il tenant | Namespace dal service discovery di Kubernetes (`__meta_kubernetes_namespace`); le label `namespace`/`tenant` esposte dall'applicazione non sovrascrivono mai le label del target (`honor_labels=false`) | Namespace dall'API Kubernetes o dai metadati del percorso del file, mai dal contenuto del log | `otelcol.processor.k8sattributes` associa gli span in base all'IP sorgente della connessione e *sovrascrive* `k8s.namespace.name`; gli span non associati finiscono nel tenant `quarantine` | Nessun instradamento per tenant; sequenza di integrità per sorgente |
| Namespace → tenant | Mappatura approvata `{site, cluster, namespace} → tenant` dal registro del catalogo, resa da Flux nella configurazione dei collector; i tenant non possono scriverla | Idem | Idem | Non applicabile |
| Trasporto | Prometheus remote-write su mTLS (certificato client per cluster) | Push Loki su mTLS | OTLP su mTLS | mTLS con conferma di ricezione, spool su disco locale |
| Controllo del gateway | Il telemetry gateway accetta la coppia `(cluster identity, tenant)` solo se il registro elenca quel tenant su quel cluster; rimuove ogni altro header di tenant; applica limiti di frequenza e di dimensione per tenant | Idem | Idem | Non applicabile |
| Backend | Distributor Mimir → broker compatibile Kafka (ingest storage) → ingester → object storage | Distributor Loki → ingester → object storage | Distributor Tempo → broker compatibile Kafka → block-builder / live-store → object storage | Archivio immutabile in North + copia immutabile in South (entrambi in compliance mode) |
| Comportamento in caso di perdita | Il WAL di Alloy bufferizza durante un fermo del gateway o del broker, fino al limite del disco; i contatori di drop generano alert | File delle posizioni + buffer limitato; i contatori di drop generano alert | Retry limitati, poi scarto (le trace hanno la priorità più bassa); i contatori generano alert | Spool dimensionato per ≥72 h; alert sui buchi; nessuno scarto silenzioso |

Il progetto lascia un rischio residuo: un collector di piattaforma compromesso potrebbe instradare in modo errato i dati tra i tenant **del proprio cluster**. Non può raggiungere i tenant di altri cluster, perché il gateway verifica il registro. Il rischio è mitigato dal fatto che i collector girano in namespace della piattaforma, usano immagini firmate, sono protetti dalle policy di admission control e che Flux ne annulla ogni drift.

I pod dei tenant non possono usare `hostNetwork`, che i Pod Security Standards vietano nei namespace dei tenant: si elimina così il modo più diretto di falsificare l'IP sorgente usato per associare le trace. L'associazione per IP di connessione può comunque fallire, o attribuire male gli span, dietro SNAT, sidecar o proxy. In questi casi i dati devono finire in `quarantine` e non nel tenant sbagliato; il comportamento è da verificare nel pilota con una variante di T-14.

Il routing per tenant di `remote_write` e OTLP in Alloy è generato dal registro. Il pattern esatto dei componenti Alloy è da verificare sulla versione di Alloy adottata.

## 3. Modello di tenancy

| Tenant | Ambito | Segnali | Retention | Limiti | Lettori |
|---|---|---|---|---|---|
| `t-<team>` | Uno per team di business (tutti i namespace del team in un sito) | Metriche, log, trace | 30 gg / 30 gg / 7 gg | Per tenant: serie, frequenza di ingestione, stream, frequenza di span (fissati all'onboarding, rivisti ogni mese) | Organizzazione del team in Grafana; SRE |
| `platform` | Infrastruttura dei cluster, servizi di piattaforma, metriche proprie di LGTM, regole SLO | Metriche, log, trace | 30 gg / 30 gg / 7 gg | Limiti **riservati**, mai condivisi con i tenant dei team | SRE, Platform Engineering |
| `capacity` | ~40.000 serie a bassa cardinalità in allowlist (§8) | Metriche | 395 gg | Allowlist fissa | Solo SRE e capacity planner |
| `security` | Copia ricercabile di 30 giorni dei log rilevanti per la sicurezza (audit, rifiuti dell'admission, autenticazione) | Log | 30 gg | Riservati | Solo gli auditor di sicurezza |
| `quarantine` | Telemetria che non si riesce ad attribuire a un namespace | Metriche, log, trace | 30 gg / 30 gg / 7 gg (come i target di retention) | Bassi | Solo SRE |

Lo stesso ID di tenant esiste in Central e in South, così dopo un failover la produzione ripristinata mantiene la propria identità.

Il problema del vicino rumoroso (noisy neighbour) è affrontato su due livelli, con parametri ancora da verificare. Quando un tenant di team raggiunge i propri limiti, il backend rifiuta l'eccedenza di quel tenant con HTTP 429, mentre gli altri tenant e `platform` continuano a ingerire. La somma dei limiti di serie dei tenant di team è fissata sotto la capacità degli ingester, al netto della riserva di `platform`. Il secondo livello di difesa è lo shuffle-sharding di Mimir, che assegna a ogni tenant un sottoinsieme di ingester; le dimensioni degli shard vanno verificate nel test di carico a 3× (T-06). Ne segue che un picco di cardinalità in un team non può accecare le regole SLO della piattaforma.

## 4. Percorso di lettura e isolamento delle query (tutti e tre i segnali)

I backend non autenticano gli utenti. Grafana Mimir si aspetta che un reverse proxy autentichi le richieste e imposti `X-Scope-OrgID` ([autenticazione e autorizzazione in Mimir](https://grafana.com/docs/mimir/latest/manage/secure/authentication-and-authorization/)), e lo stesso schema vale per Loki e Tempo. Il percorso di lettura ha quindi un proprio punto di enforcement, che descriviamo qui in sette elementi; la decisione completa è nell'[ADR 0012](adr/0012-telemetry-tenancy-and-read-isolation.md).

1. Organizzazioni Grafana. Ogni team di business ha una propria organizzazione Grafana; un'organizzazione `platform` serve SRE e Platform Engineering, un'organizzazione `security` gli auditor di sicurezza. La ragione è che in Grafana OSS qualunque utente può interrogare qualunque data source della propria organizzazione, mentre i permessi per singolo data source sono una funzione Enterprise ([ruoli e permessi in Grafana](https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/)): in OSS l'unità di isolamento è dunque l'organizzazione. Data source e dashboard sono predisposti da Git, e il ruolo *Org Admin* è assegnato solo al service account di provisioning, così gli utenti dei team non possono modificare le impostazioni dei data source.
2. Identità inoltrata. Ogni data source Mimir, Loki e Tempo punta al **query gateway** del sito con l'opzione *Forward OAuth Identity* attiva: viene inoltrato il token OIDC dell'utente, non una credenziale statica. Tutti e tre i data source supportano questa opzione ([Prometheus](https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/data-sources/prometheus/configure/), [Loki](https://grafana.com/docs/grafana/latest/datasources/loki/configure/), [Tempo](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/)).
3. Query gateway. Il gateway valida il token sull'IdP locale del sito e mappa i gruppi dell'IdP sull'insieme dei tenant consentiti, usando lo stesso registro del percorso di scrittura. Imposta esso stesso `X-Scope-OrgID`, rifiuta ogni richiesta che chieda un tenant fuori da quell'insieme e applica limiti di query per tenant. Registra ogni query (utente, tenant, hash della query) nel tenant `security` e nel relay di audit, così gli accessi in lettura restano conservati per l'intera retention di audit ([ADR 0010](adr/0010-audit-evidence-and-retention.md)). I ruoli SRE e di piattaforma ricevono un header multi-tenant (`a|b|…`), che richiede la tenant federation attiva in Mimir e in Loki: va verificata sulla versione adottata di ciascuno. Il gateway è in HA (≥2 repliche) e locale al sito. I candidati per l'implementazione sono reverse proxy con supporto OIDC e un hook di autorizzazione esterno; la scelta si fa nel pilota di Fase 1.
4. Enforcement di rete. Gli endpoint di query e di amministrazione dei backend accettano traffico solo dal query gateway e dai ruler interni al cluster (NetworkPolicy e mTLS). Un utente che aggira Grafana incontra comunque il gateway.
5. Le trace non sono un caso a parte. Il controllo di accesso basato su label (LBAC) di Grafana per i data source supporta, nell'edizione Enterprise, le metriche (Mimir tramite GEM) e i log (Loki tramite GEL). Per le trace è offerto solo con Grafana Cloud Traces, non con Tempo self-hosted ([LBAC per i data source](https://grafana.com/docs/grafana/latest/administration/data-source-management/teamlbac/)). L'isolamento di Tempo si basa quindi sul controllo combinato di organizzazione e gateway, in ogni edizione.
6. L'alerting non usa l'identità inoltrata. Le regole di alert e di recording sono valutate dai ruler di Mimir e di Loki all'interno di ciascun tenant, non come regole gestite da Grafana ed eseguite con il token di un utente. È una scelta di progetto il cui funzionamento va verificato sulla versione adottata.
7. Vista di fleet tra i siti. L'organizzazione `platform` di ciascun sito ha data source in sola lettura che puntano al query gateway del sito *remoto* (F-06/F-07). Il gateway remoto applica la stessa validazione del token: si fida delle chiavi di firma degli IdP di entrambi i siti, sincronizzate insieme ai dati di identità (F-15, [ADR 0011](adr/0011-south-recovery-dependencies.md)). La perdita del collegamento degrada soltanto le viste di fleet.

Le alternative considerate sono Grafana Enterprise con LBAC, un'istanza Grafana per team e il solo RBAC di Grafana; i compromessi sono registrati nell'[ADR 0012](adr/0012-telemetry-tenancy-and-read-isolation.md).

## 5. Servizi di supporto e team che li fornisce

I servizi di supporto (backing service) possono essere forniti dal cliente, a condizione che per ciascuno sia indicato il team che lo eroga. I prodotti sono da confermare nel pilota.

| Servizio di supporto (per sito attivo) | Usato da | Fornito e gestito da | Aspettativa di HA e domini di guasto | In caso di guasto |
|---|---|---|---|---|
| Object storage compatibile S3, un bucket per segnale (versioning non richiesto per i bucket LGTM) | Blocchi e chunk di Mimir, Loki e Tempo; stato di ruler e Alertmanager | Data Engineering | ≥3 domini di guasto dello storage, erasure coding o replica | Le scritture proseguono su disco locale/WAL per un tempo limitato; query storiche e compaction si fermano |
| Broker compatibile Kafka (3 broker, fattore di replica 3) | Ingest storage di Mimir; percorso di scrittura di Tempo in modalità microservizi | Data Engineering | Broker distribuiti sui domini di guasto; prodotto da definire (Grafana documenta come esempi Apache Kafka o Redpanda) | **Le scritture di metriche e trace si fermano al distributor**; i collector bufferizzano; le query sui dati recenti possono risultare non aggiornate |
| PostgreSQL in HA | Metadati di Grafana (utenti, organizzazioni, preferenze) | Data Engineering | Primario + replica per sito; istanza separata in South | UI di Grafana non disponibile; dashboard ripristinabili da Git; **alerting non toccato** |
| Cache Memcached | Cache di query, chunk, indici e metadati | SRE (parte del rilascio LGTM) | ≥2 repliche | Solo query più lente |
| Volumi persistenti (dischi di ingester e live-store, WAL di Alloy, spool) | Ingester, store-gateway, collector, relay di audit | Platform Engineering (storage class CSI specifica del sito) | Datastore per sito; anti-affinity | Riavvio del singolo pod; dati protetti da broker o replica |
| IdP locale al sito (OIDC) e PKI (mTLS) | Login a Grafana, query gateway, certificati dei collector | Network Security (owner presunto di identità e PKI, A-17) | Un'istanza per sito, ripristinabile senza Central ([ADR 0011](adr/0011-south-recovery-dependencies.md)); owner secondo l'assunzione A-17 | Nessun nuovo login; ingest e alerting non toccati finché i certificati sono validi |
| Endpoint di paging / ITSM | Alertmanager, dead-man's switch | SRE | Raggiungibile da entrambi i siti in modo indipendente | Vedi §10 |

SRE gestisce i componenti LGTM; Network Security approva ogni flusso tra siti.

## 6. Architettura di ingest e baseline di prodotto

| Componente | Baseline di progetto | Stato |
|---|---|---|
| Grafana Mimir | 3.x con architettura ingest storage. Con Mimir 3.0 diventa l'architettura preferita; quella classica è ancora supportata, con deprecazione pianificata. Nel chart Helm 6.x l'ingest storage è attivo per default, ma il Kafka incluso serve solo per i test ([architettura ingest storage](https://grafana.com/docs/mimir/latest/get-started/about-grafana-mimir-architecture/about-ingest-storage-architecture/), [rilascio di Mimir 3.0](https://github.com/grafana/mimir/releases/tag/mimir-3.0.0)) | Minor esatta da verificare; in produzione il broker è esterno (§5) |
| Grafana Tempo | 3.x in modalità microservizi: i distributor scrivono su un sistema compatibile Kafka, i block-builder scrivono blocchi Parquet, i live-store servono i dati recenti, scheduler e worker di backend sostituiscono il compactor, RF1 perché la durabilità è data dal broker. La modalità monolitica non richiede broker ma gira come un unico processo ([note di rilascio di Tempo 3.0](https://grafana.com/docs/tempo/latest/release-notes/v3-0/), [modalità di deployment](https://grafana.com/docs/tempo/latest/reference-tempo-architecture/deployment-modes/)) | Da verificare; scelta perché il broker esiste già per Mimir e le trace richiedono HA |
| Grafana Loki | 3.x a microservizi (nessun broker previsto), indice TSDB, retention per tenant tramite compactor | Da verificare |
| Grafana (UI) | OSS, un'organizzazione per team, provisioning come codice | Funzioni delle organizzazioni da verificare sulla major adottata |
| Grafana Alloy | Versione fissata; WAL per le metriche; `otelcol.processor.k8sattributes` per le trace ([riferimento](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.processor.k8sattributes/)) | Da verificare |
| Prometheus | Piccola istanza indipendente in ogni sito per il metamonitoraggio tra siti (§10) | Scelta di progetto |

Abbiamo scelto l'ingest storage al posto dell'architettura classica per tre motivi. Segue la direzione upstream ed evita una riprogettazione forzata quando la classica sarà deprecata; il broker separa la disponibilità in scrittura dai riavvii degli ingester; un solo servizio broker per sito è condiviso da Mimir e da Tempo. Il prezzo è un nuovo servizio di supporto stateful in ogni sito, con owner, monitoraggio e postura DR propri, e il fatto che un fermo del broker blocca le scritture di metriche e trace (i collector bufferizzano).

Il trigger di revisione è esplicito: se entro la fine del pilota di Fase 1 Data Engineering non è in grado di gestire una piattaforma di broker, si torna all'architettura classica di Mimir (ingester con RF3) e a Tempo monolitico in ogni sito, registrando la scelta in un ADR che sostituisce quello attuale. Throughput e dischi del broker sono stimati in [06](06-nfr-and-capacity.md) §4.

## 7. Alta affidabilità e comportamento in caso di guasto

| Guasto | Effetto | Comportamento previsto | Rilevato da |
|---|---|---|---|
| Un nodo / ingester / live-store | Nessuno per gli utenti | Il broker conserva i dati; le repliche subentrano; anti-affinity tra i domini di guasto VMware | Salute dei componenti, tenant `platform` |
| Broker non disponibile | Scritture di metriche e trace rifiutate | WAL di Alloy e retry OTLP bufferizzano fino al limite del disco; log non toccati; page se il problema persiste | 5xx del gateway + crescita del WAL |
| Object storage non disponibile | Dati recenti ancora interrogabili; storico e compaction in pausa | I dischi locali assorbono gli upload per un periodo limitato; la durata di fermo tollerata è un input del dimensionamento in [06](06-nfr-and-capacity.md) | Tasso di upload falliti |
| Telemetry gateway giù (una replica) | Nessuno | ≥2 repliche dietro il load balancer del sito | Probe + freschezza dei canary |
| Query gateway o Grafana giù | Le persone non possono interrogare | **Ruler e Alertmanager continuano a chiamare il reperibile** | Probe legacy / probe dall'altro sito |
| PostgreSQL di Grafana giù | UI non disponibile | Nuovo provisioning; alerting non toccato | Probe dall'altro sito |
| IdP del sito giù | Nessun nuovo login | Alerting e ingest non toccati; admin break-glass locale e sigillato per Grafana | Probe dall'altro sito |
| Collegamento Central↔South giù | Viste di fleet parziali | Ingest, query e alert locali non toccati; "sito remoto irraggiungibile" è un ticket se non è confermato (§10) | Entrambi gli scraper di metamonitoraggio |
| Alertmanager giù | Nessun page da quel sito | L'heartbeat del Watchdog si ferma → il dead-man's switch dell'altro sito chiama SRE | §10 |
| **Perdita di Central** | LGTM di Central perso | LGTM di South continua; la produzione ripristinata scrive in South con gli stessi ID di tenant; lo storico di Central non è servito, tranne il tenant capacity ripristinato (§8) | Metamonitoraggio di South + probe legacy (se non si trova in Central) |

## 8. Meccanismi di retention, incluso il livello di capacità a 13 mesi

| Dati | Retention | Meccanismo |
|---|---|---|
| Metriche (`t-*`, `platform`) | 30 gg a piena risoluzione | Override della retention per tenant nel compactor di Mimir |
| Metriche di capacità | 395 gg (13 mesi) | Tenant `capacity` separato (vedi sotto) |
| Log | 30 gg | Retention per tenant nel compactor di Loki; le regole di lifecycle dell'object storage **non devono** cancellare oggetti referenziati dall'indice |
| Trace | 7 gg | Retention nel worker di backend di Tempo |
| Audit | Archivio di 400 gg (≥365 gg richiesti) | Doppio archivio immutabile ([ADR 0010](adr/0010-audit-evidence-and-retention.md)); il tenant `security` di Loki conserva una copia ricercabile di 30 gg; gli eventi più vecchi si ripristinano su richiesta, entro 4 h, in un tenant temporaneo `audit-restore` |

Il livello di capacità è una scelta di progetto con alcuni comportamenti ancora da verificare. **Mimir non effettua downsampling automatico**: la compaction non cambia la risoluzione, quindi il livello a 13 mesi va prodotto in modo esplicito. Lo producono recording rule federate di proprietà del tenant `capacity`, che leggono da `platform` e da `t-*` (`source_tenants`). Le regole sono valutate ogni 300 s e scrivono ~40.000 serie in allowlist: CPU, memoria, storage, numero di pod e di richieste per sito, cluster, namespace e team. Richiedono `-ruler.tenant-federation.enabled` e `-tenant-federation.enabled` ([ruler di Mimir](https://grafana.com/docs/mimir/latest/references/architecture/components/ruler/)).

La conseguenza per l'isolamento è che i risultati aggregati vivono nel tenant `capacity`, ed è per questo che quel tenant è leggibile soltanto da SRE e capacity planner.

Il lookback predefinito di PromQL è di 5 minuti ([basi delle query in Prometheus](https://prometheus.io/docs/prometheus/latest/querying/basics/)): con campioni ogni 300 s e il jitter della valutazione, le query istantanee possono mostrare buchi. Le dashboard di capacità usano quindi funzioni su intervallo come `last_over_time(x[10m])`, con uno step di almeno 5 min. Lo storage resta alla dimensione modellata (stima), mentre il comportamento delle query è da verificare nel pilota.

Lo storico di capacità sopravvive alla perdita di Central. I blocchi `capacity` di Central sono copiati ogni giorno in un prefisso DR separato in South (F-05) e possono essere caricati in South come `capacity-central`. Lo storico di capacità ha così un RPO ≤24 h, accettabile per dati di pianificazione; i dati di produzione seguono la matrice DR in [05](05-reliability-and-dr.md).

## 9. Alerting, SLO e instradamento (sintesi; le regole sono nell'ADR 0006)

Un alert è ammesso solo se ha un owner nominato, un impatto sugli utenti o sui dati, un'azione definita e un runbook.

L'SLO di piattaforma è del 99,9% per **trimestre solare di orario lavorativo**, con report mensile. Con l'orario assunto 08:00–18:00 e circa 66 giorni lavorativi, il trimestre vale ~660 h e l'error budget stimato è di 39,6 min. Con questa finestra i moltiplicatori convenzionali mantengono il loro significato abituale: un burn rate di 14,4× per 1 h consuma ~2,2% del budget, uno di 6× per 6 h ~5,5%. La tabella completa è nell'[ADR 0006](adr/0006-alerting-and-slos.md).

L'SLO del 99,9% e il tetto di "≤1 interruzione non pianificata a trimestre" sono due vincoli indipendenti. Un disastro con perdita di sito, una volta dichiarato, è governato da RPO e RTO e non dallo SLO di disponibilità; è una proposta che richiede l'accettazione del CIO.

Gli alert sono instradati ai quattro team per competenza: a SRE disponibilità, LGTM e ingest; a Platform Engineering GitLab, Flux, catalogo e admission; a Data Engineering object storage, broker, database e replica; a Network Security firewall, PKI, IdP e flussi falliti. Gli alert rilevanti per la sicurezza (buchi nell'audit, tentativi di falsificare il tenant, scadenza di chiavi) hanno una severità propria e non sono mai soppressi dallo stato dello SLO.

Le severità sono tre. Il page chiama il reperibile del team owner e si usa per il burn rapido o lento dello SLO di un servizio di piattaforma, per una perdita prolungata di ingest, per uno spool di audit oltre soglia e quando scatta il dead-man's switch. Il ticket finisce nel backlog del team e copre, per esempio, una previsione di capacità che supera la soglia a 30 giorni, il flapping di una singola replica o un guasto in non produzione. Il livello "solo dashboard" riguarda i rischeduling innocui che restano entro il budget.

Gli obiettivi di qualità, per ora stimati, sono tre: almeno il 95% di page azionabili, non più di 2 falsi page per team a settimana dopo il tuning, il 100% delle route critiche testate ogni trimestre. I primi 90 giorni sono dedicati a misurare e a calibrare.

## 10. Il monitoraggio del sistema di monitoraggio (percorso indipendente)

1. Dead-man's switch. L'Alertmanager di ciascun sito invia un heartbeat *Watchdog* sempre attivo a un receiver ospitato nell'**altro** sito. Se gli heartbeat si fermano, il receiver chiama SRE attraverso un canale di notifica che non passa dall'Alertmanager guasto. Si elimina così la dipendenza circolare per cui il sistema monitorato dovrebbe segnalare da sé il proprio guasto.
2. Metamonitoraggio tra siti. Un piccolo Prometheus in ciascun sito esegue lo scrape degli endpoint di salute LGTM dell'altro sito (gateway, distributor, ingester, broker, probe dell'object storage) sul flusso F-10 e controlla la freschezza dei canary.
3. Canary. Il tenant `platform` scrive ogni minuto una metrica, una riga di log e una trace attraverso il telemetry gateway. "Età del canary più recente ≤2 min" è lo SLI di freschezza usato in [06](06-nfr-and-capacity.md).
4. Tool black-box legacy. Durante la coesistenza sonda anche Grafana ed entrambi i gateway. Oggi non si sa dove sia installato, e la sua collocazione è da verificare: se gira in Central **non** è indipendente dalla perdita di Central, e la rilevazione di quella perdita deve affidarsi al metamonitoraggio di South.
5. Gestione delle partizioni. "Sito remoto irraggiungibile" segnalato da un solo probe è un ticket. Diventa un page quando è confermato da un secondo punto di osservazione: il tool legacy, oppure un controllo di raggiungibilità da North usato solo come indicazione ausiliaria.

## 11. Coesistenza con il monitoraggio legacy e con i cluster esistenti

| Passo | Cosa succede | Criterio di uscita | Owner |
|---|---|---|---|
| 1. Inventario | Ogni check ping/HTTP legacy è censito con owner, target e azione attuale | 100% dei check mappati | SRE |
| 2. Osservazione dei cluster esistenti (sola lettura) | Collector Alloy installati come codice sui cluster creati a mano, con RBAC in sola lettura: metriche e log, nessuna modifica di admission o di policy | Produzione esistente visibile negli LGTM di Central e South | SRE + Platform Engineering |
| 3. Shadow | I nuovi alert SLO aprono solo ticket; il tool legacy continua a chiamare il reperibile | Due cicli di rilascio completi di dati affiancati | SRE |
| 4. Parità per singolo check | Ogni check legacy ha un probe sintetico o un alert SLO equivalente, che è scattato durante un game day | L'owner firma la parità per singolo check | Owner del check |
| 5. Cutover per singolo check | Il nuovo alert chiama il reperibile; il check legacy resta come probe esterno indipendente | Nessun incidente mancato per un ulteriore ciclo di rilascio | SRE |
| 6. Dismissione | Il tool legacy resta solo come probe indipendente di LGTM e Grafana, oppure viene dismesso con l'approvazione del CIO | Verbale di dismissione firmato | SRE (A), CIO (approvazione) |

L'applicazione di riferimento three-tier è il primo workload preso in carico: le sue dashboard restano e la sua telemetria passa sul percorso del gateway (vedi [11](11-existing-workstreams.md)).

## 12. Controlli di sicurezza e compliance

Il trasporto dai collector ai gateway usa mTLS, gli utenti si autenticano con OIDC e ogni sito ha la propria PKI. Non esistono credenziali amministrative statiche tra siti, e i dati sono cifrati in transito e a riposo.

Le label sono in allowlist: site, cluster, env, namespace, service, owner. Pod UID, request ID, e-mail dell'utente e percorso URL grezzo non diventano mai label di uso generale. Credenziali e dati personali (PII) sono oscurati nel collector e nel gateway.

Gli eventi di audit passano per un relay dedicato nel management cluster di ciascun sito. Oggetti e manifest firmati finiscono in un doppio archivio immutabile (North + South, compliance mode), descritto nell'[ADR 0010](adr/0010-audit-evidence-and-retention.md). Il relay si trova fuori dal cluster di osservabilità, quindi un fermo di LGTM non interrompe la consegna dell'audit.

Ogni query è attribuibile a un utente, grazie al log del query gateway nel tenant `security`.

## 13. Piano di validazione (prima del rollout sulla fleet)

| # | Test | Accettazione |
|---|---|---|
| 1 | Strumentare l'applicazione di riferimento three-tier e due cluster rappresentativi (Central + South) | Dashboard conservate; trace e log oscurati correlati tra loro |
| 2 | Carico di serie metriche a 1× e 3×; picco di cardinalità in un tenant di team (T-06) | Gli altri tenant e `platform` non perdono campioni; le regole SLO continuano a essere valutate |
| 3 | `k8s.namespace.name` OTLP falsificato, campi di log falsificati, header di tenant falsificati (T-14) | I dati finiscono nel tenant del namespace di origine o in `quarantine` |
| 4 | Query cross-tenant attraverso l'API di Grafana **e** direttamente contro il query gateway e gli endpoint dei backend (T-14) | Zero risultati cross-tenant; accesso diretto ai backend rifiutato |
| 5 | Fermare il broker (T-16), un ingester e l'endpoint dell'object storage (T-07); revocare il certificato di un collector (T-07) | Buffering limitato, gli alert scattano, nessuna perdita silenziosa; il collector revocato viene rifiutato e segnalato |
| 6 | Isolare il collegamento Central↔South (T-08) | Entrambi i siti continuano a ingerire e a chiamare il reperibile; si degradano solo le viste di fleet |
| 7 | Fermare l'Alertmanager e Mimir di un sito (T-15) | Il dead-man's switch chiama SRE entro il tempo concordato |
| 8 | Tenant capacity: query di trend su 13 mesi, query a cavallo di fine mese, ripristino in South della copia di Central | Serie continue; storico ripristinato interrogabile |
| 9 | Tenere attivi i monitor legacy per tutto il periodo | Nessun check dismesso prima della firma del passo 4 di §11 |
