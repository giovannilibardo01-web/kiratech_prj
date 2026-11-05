# Architettura attuale e target: interpretazione C4

## Il panorama esistente

Modelliamo come **noti** solo i fatti dichiarati esplicitamente nei requisiti del cliente: Central ospita la produzione e un'istanza GitLab self-managed; North è il sito di backup; South è un sito secondario, non di produzione; sono presenti VMware e diversi cluster Kubernetes configurati a mano; ci si affida a un monitor black-box ping/HTTP legacy; non esiste alcuna elaborazione dei log. I requisiti non stabiliscono in quale sito si trovi ciascun cluster Kubernetes esistente, né il prodotto di database, la CNI, il provider IAM o il software di backup. Il diagramma as-is segna questi elementi come sconosciuti, invece di inventarne il disegno.

Il cliente ha già due attività di ingegneria in corso: un'applicazione di riferimento single-cluster con Prometheus/Loki/Grafana/Alloy e un golden path basato su namespace in South. Le loro architetture attuali sono lavori in corso, non componenti di baseline di livello enterprise.

## Sintesi del target

```text
                       IdP / PKI / DNS / ITSM aziendali
                                   |
                          [Gateway di accesso]
                                   |
                [Catalogo Backstage in South + standby in Central]
                                   |
                        [GitLab Ultimate CI/SCM]
                                   |
             [OpenTofu + Cluster API vSphere] --> VMware per sito
                                   |
                    [FluxCD riconcilia ogni cluster]
                                   |
                        [Kyverno / PSS / RBAC]
                                   |
              [Workload firmati + External Secrets + NetworkPolicy]

 Central: produzione, GitLab primario, LGTM HA locale, 10 cluster di produzione
 South: non produzione, 10 cluster DR caldi, secondario GitLab Geo,
        LGTM HA locale; può promuovere management di piattaforma e produzione
 North: backup fuori sede, audit immutabile + manifest di backup, niente K8s
```

La fonte di verità è ripartita per responsabilità. GitLab conserva la **configurazione desiderata e gli artefatti di deployment**, revisionati e immutabili; lo stato di OpenTofu sta in un backend on-prem protetto, con versioning e credenziali isolate; Cluster API riconcilia gli oggetti dei workload e del control plane; Flux riconcilia le risorse Kubernetes; un vault esterno conserva i valori dei secret; il container registry di GitLab conserva gli artefatti immagine firmati. GitHub ospita soltanto questa proposta di progetto.

## Inventario dei siti e dei cluster proposto a 18 mesi

| Sito | Ruoli dei cluster | Numero | Comportamento in caso di guasto |
|---|---|---:|---|
| Central | 1 management, 1 osservabilità, 10 workload di produzione | **12** | La perdita del sito richiede promozione e recupero in South |
| South | 1 management, 1 osservabilità, 10 DR caldi di produzione, 6 dev/test condivisi | **18** | Gli ambienti di test self-service vengono ricreati; la capacità DR resta protetta |
| North | Archivio indipendente di backup con object lock e coordinatore dei restore (VM/appliance), nessun K8s | **0** | Recupero ed evidenze immutabili fuori sede, nessuna dipendenza a runtime |
| **Totale** | | **30** | Capacità e mappa dei workload di produzione da validare |

Il cliente indica circa 30 cluster, non questa ripartizione. Come disegno di partenza per l'RTO di 4 ore in caso di perdita di un sito scegliamo cluster controparte caldi, uno a uno. La riserva di worker per la produzione recuperata serve in qualsiasi variante di DR; ciò che l'1:1 aggiunge rispetto al DR a livelli o condiviso è soprattutto overhead di control plane: con le assunzioni dichiarate, circa 36 vCPU in più rispetto al DR a livelli e 84 vCPU in più rispetto a quello condiviso. Il confronto tra 1:1, DR a livelli, DR condiviso e ricostruzione a freddo, insieme al comportamento alla perdita di ciascun sito, è in [ADR 0002](adr/0002-multi-site-topology.md). Il DR a livelli è la leva di costo documentata da considerare dopo l'inventario dei workload.

### Regole di topologia dei siti

1. Nessun etcd esteso tra siti e nessun quorum unico tra siti. L'etcd e il control plane di ogni cluster sono locali, quindi il guasto di un sito non può distruggere il quorum dell'altro.
2. South è un dominio di management indipendente. Già prima di qualsiasi disastro esegue una propria istanza dell'IdP, una CA emittente, il secret manager, HSM/KMS, DNS secondari, vCenter, un registry OCI che contiene ogni release di produzione e l'istanza primaria di Backstage. La piattaforma non deve dipendere da alcuna API che esista solo in Central; si veda [ADR 0011](adr/0011-south-recovery-dependencies.md).
3. North è un dominio amministrativo e di guasto separato. Lo storage immutabile di audit e backup richiede permessi di retention indipendenti e un percorso di recupero testato; nessuna applicazione di produzione scrive direttamente sullo storage di archiviazione privilegiato.
4. Non esiste comunicazione diretta e senza restrizioni tra pod di siti diversi. La policy firewall espone solo endpoint di servizio autenticati e con un nome, con sorgente, destinazione, protocollo e owner espliciti.
5. Il failover è controllato, non automatico a livello applicativo, per evitare split brain di database e Git. Controlli di prontezza e deployment automatici sono possibili dopo che un incident commander, cioè una persona, ha emesso una decisione di promozione con fencing.
6. I ruoli dei cluster di piattaforma non coincidono con la tenancy dei servizi Kubernetes. I piani di management e di osservabilità hanno credenziali e storage propri e ristretti, mentre le applicazioni di produzione critiche hanno, dove serve, confini distinti a livello di cluster.

## Ownership e tecnologie del control plane

| Livello | Scelta | Motivazione e limiti |
|---|---|---|
| Hypervisor | VMware vSphere esistente | Vincolo contrattuale; vanno verificati CSI/CPI e la matrice di supporto di CAPV |
| Infrastructure as code | OpenTofu | Provisioning dichiarativo open source; stato remoto protetto e approvazioni in GitLab |
| Ciclo di vita dei cluster | Cluster API Provider vSphere (CAPV), un management cluster per sito | Ciclo di vita della flotta, template ripetibili e riconciliazione day-2; maturità di CAPI da validare rispetto alle versioni VMware. VMware vSphere Kubernetes Service (VKS) è l'alternativa preferita se il cliente ha la licenza VCF ([ADR 0001](adr/0001-platform-toolchain.md)) |
| GitOps | FluxCD | Pull e riconciliazione per cluster, senza accessi amministrativi push estesi tra siti; bootstrap controllato e runbook per sospendere la riconciliazione |
| Self-service | Backstage | Esperienza d'uso del catalogo e del workflow del golden path, con il confine di approvazione in GitLab; ogni plugin deve avere un owner |
| SCM / CI / artefatti | GitLab Ultimate (esistente) | Valorizza l'investimento enterprise già fatto; scansioni di sicurezza, SBOM e verifica delle immagini firmate, runner e ambienti protetti |
| Policy / tenancy | Kyverno + PSS Restricted + RBAC + NetworkPolicy + quote | Enforcement in fase di admission, eccezioni verificabili, controllo del blast radius e della spesa |
| Secret | External Secrets Operator + vault on-prem | Nessun valore di secret in Git, nemmeno come blob cifrato; accesso indipendente per sito |
| Osservabilità | Grafana/Alloy + Mimir/Loki/Tempo | Stack scelto, self-hosted, con scalabilità orizzontale per sito |
| Gestione degli alert | Burn rate SLO multi-finestra + instradamento a ticket o pager | Gli incidenti non azionabili restano su dashboard o come eventi e non generano paging |

## Viste C4 e modello

`architecture/model.json` è l'unica fonte di tutte e **sette le viste**: contiene l'inventario completo di nodi e relazioni, e `architecture/render_diagrams.py` ne produce DOT, SVG e PNG. Ogni nodo riporta nome, tipo C4, tecnologia, sito, team owner e una descrizione, che nell'SVG compare come tooltip.

Le viste 01 e 02 sono i panorami di sistema, as-is e target. La 03 mostra i container dell'IDP, compresa l'API Kubernetes come sorgente degli eventi di audit e chiamante dei webhook di admission. Le viste da 04 a 06 descrivono il deployment di ciascun sito, e la 07 i componenti di osservabilità, con il team che fornisce ciascun servizio di supporto.

La notazione è in stile C4, resa con Graphviz e non con un workspace Structurizr, e questo comporta alcuni limiti. I nodi di deployment elencano i container che ospitano nella riga della tecnologia, invece di disegnare istanze di container annidate. Gli archi tra siti sono tratteggiati in rosso ed etichettati con l'F-ID della [matrice dei flussi](12-firewall-flows.md). Le linee rappresentano relazioni logiche di comunicazione o di dipendenza: una linea non dimostra che esista una regola firewall né che il traffico sia sincrono. Indirizzi fisici e porte definitive non sono noti.

## Compromessi di progetto espliciti

- Abbiamo preferito ingerire la telemetria in ogni sito anziché centralmente. Ingestione e storage locali costano di più, ma contengono i guasti di collegamento e di firewall e migliorano la disponibilità; Grafana offre query controllate tra siti, e North non è un sito di telemetria a caldo.
- Il DR caldo costa più della ricostruzione su richiesta: 10 cluster di recupero in South e la replica dei dati consumano risorse, ma tolgono il provisioning dei cluster dal percorso critico delle 4 ore. La sola prenotazione di capacità non dimostra che il servizio sia pronto.
- Come SCM operativo resta GitLab, non GitHub. GitLab Ultimate è già a contratto con il cliente, e un repository di consegna su GitHub **non** deve diventare una seconda fonte dello stato desiderato di produzione.
- Gli ambienti di test condividono i cluster, con tenancy a namespace, quote e controlli di admission; l'isolamento della produzione sensibile o critica e il recupero dai guasti richiedono, dove giustificato, confini a livello di cluster interi.
- Per l'operabilità, e contro la proliferazione degli strumenti, si riusano lo stack di riferimento e i workstream esistenti, e si vietano strumenti ed eccezioni di admission privi di owner e policy di object store incompatibili.
