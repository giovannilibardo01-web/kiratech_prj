# Materiale di riferimento e link di validazione del progetto

Il documento dei requisiti del cliente **non è incluso** in questo repository. I requisiti sono parafrasati e tracciati in [perimetro e assunzioni](01-scope-and-assumptions.md), e ogni fatto di progetto che il documento non dichiara è indicato come assunzione.

I link puntano alla documentazione *corrente* ("latest"), consultata il 2026-11-05. Un link sostiene un'affermazione di progetto sulla famiglia di prodotti, ma non dimostra la compatibilità con l'ambiente di questo cliente. Le versioni esatte vengono congelate in una distinta dei componenti (bill of materials) firmata all'avvio del pilota, e ogni affermazione che segue va ricontrollata sulla versione adottata.

## Osservabilità (verificato il 2026-11-05)

| Affermazione usata nel progetto | Fonte |
|---|---|
| Mimir 3.0 rende l'ingest storage (basato su Kafka) l'architettura preferita. L'architettura classica resta supportata, con una deprecazione pianificata | [Architettura ingest storage](https://grafana.com/docs/mimir/latest/get-started/about-grafana-mimir-architecture/about-ingest-storage-architecture/); [Architettura classica](https://grafana.com/docs/mimir/latest/get-started/about-grafana-mimir-architecture/about-classic-architecture/); [Release Mimir 3.0.0](https://github.com/grafana/mimir/releases/tag/mimir-3.0.0) |
| Il chart Helm di Mimir 6.x abilita l'ingest storage per default, e il Kafka incluso nel chart serve solo per i test | [Migrazione del chart Helm da 5.x a 6.0](https://grafana.com/docs/helm-charts/mimir-distributed/latest/migration-guides/migrate-helm-chart-5.x-to-6.0/); [Configurazione del backend Kafka](https://grafana.com/docs/mimir/latest/configure/configure-kafka-backend/) |
| Mimir non ha autenticazione integrata. Un reverse proxy autentica la richiesta e imposta `X-Scope-OrgID`; con la federazione abilitata, più tenant si separano con `\|` | [Autenticazione e autorizzazione in Mimir](https://grafana.com/docs/mimir/latest/manage/secure/authentication-and-authorization/) |
| I rule group federati di Mimir (`source_tenants`) richiedono la federazione dei tenant sia nel ruler sia nelle query, e i loro risultati sono memorizzati nel tenant proprietario | [Ruler di Mimir](https://grafana.com/docs/mimir/latest/references/architecture/components/ruler/) |
| La compattazione di Mimir applica la retention per tenant e non esegue downsampling | [Retention dello storage delle metriche](https://grafana.com/docs/mimir/latest/configure/configure-metrics-storage-retention/); [Compactor](https://grafana.com/docs/mimir/latest/references/architecture/components/compactor/) |
| Modalità di deployment di Tempo 3.0: la modalità a microservizi usa un sistema compatibile con Kafka, block-builder, live-store e scheduler/worker di backend, con RF1. La modalità monolitica non richiede Kafka. La modalità monolitica scalabile è stata rimossa | [Note di rilascio di Tempo 3.0](https://grafana.com/docs/tempo/latest/release-notes/v3-0/); [Modalità di deployment](https://grafana.com/docs/tempo/latest/reference-tempo-architecture/deployment-modes/); [Migrazione alla 3.0](https://grafana.com/docs/tempo/latest/set-up-for-tracing/setup-tempo/migrate-to-3/) |
| Storage, TSDB e retention di Loki si basano sul compactor e non sulle regole di lifecycle dei bucket | [Storage di Loki](https://grafana.com/docs/loki/latest/configure/storage/); [Retention di Loki](https://grafana.com/docs/loki/latest/operations/storage/retention/); [Autenticazione di Loki](https://grafana.com/docs/loki/latest/operations/authentication/) |
| In Grafana OSS qualsiasi utente di un'organizzazione può interrogare qualsiasi data source di quella organizzazione. I permessi sui data source esistono solo in Enterprise, mentre le organizzazioni isolano i data source | [Ruoli e permessi](https://grafana.com/docs/grafana/latest/administration/roles-and-permissions/); [Gestione delle organizzazioni](https://grafana.com/docs/grafana/latest/administration/organization-management/); [Buone pratiche di sicurezza dei data source](https://grafana.com/blog/data-source-security-in-grafana-best-practices-and-what-to-avoid/) |
| LBAC per i data source copre Loki (GEL) e Mimir/Prometheus (GEM) in Enterprise. Per le trace è disponibile solo con Grafana Cloud Traces, non con Tempo self-hosted | [LBAC per i data source](https://grafana.com/docs/grafana/latest/administration/data-source-management/teamlbac/) |
| I data source Prometheus, Loki e Tempo supportano *Forward OAuth Identity* | [Data source Prometheus](https://grafana.com/docs/grafana-cloud/observe-and-act/connect-externally-hosted/data-sources/prometheus/configure/); [Data source Loki](https://grafana.com/docs/grafana/latest/datasources/loki/configure/); [Data source Tempo](https://grafana.com/docs/grafana/latest/datasources/tempo/configure-tempo-data-source/) |
| In Alloy, `otelcol.processor.k8sattributes` associa per connessione o per attributo di risorsa ed estrae il namespace; `discovery.kubernetes` espone `__meta_kubernetes_namespace` | [k8sattributes](https://grafana.com/docs/alloy/latest/reference/components/otelcol/otelcol.processor.k8sattributes/); [discovery.kubernetes](https://grafana.com/docs/alloy/latest/reference/components/discovery/discovery.kubernetes/) |
| Il lookback di PromQL per i vettori istantanei è di 5 minuti per default | [Nozioni di base sulle query Prometheus](https://prometheus.io/docs/prometheus/latest/querying/basics/) |

## Sicurezza e conformità (verificato il 2026-11-05)

| Affermazione usata nel progetto | Fonte |
|---|---|
| Lockdown multi-tenancy di Flux: `--no-cross-namespace-refs`, `--no-remote-bases`, `--default-service-account` (un account senza permessi), impersonation tramite `spec.serviceAccountName`. Per default i controller girano con cluster-admin | [Multi-tenancy in Flux](https://fluxcd.io/flux/installation/configuration/multitenancy/); [Buone pratiche di sicurezza di Flux](https://fluxcd.io/flux/security/best-practices/) |
| Le PolicyException di Kyverno sono disabilitate per default e possono essere limitate a un solo namespace (`exceptionNamespace`). La PolicyException `kyverno.io` è deprecata nella v1.19 e ne è prevista la rimozione nella v1.20 insieme a ClusterPolicy; la sostituiscono i tipi `policies.kyverno.io` basati su CEL | [Policy exception di Kyverno](https://kyverno.io/docs/guides/exceptions/) |
| La verifica delle immagini in Kyverno supporta attestor cosign a chiave pubblica e un'impostazione per Rekor. Saltare il transparency log è documentato solo per i test | [Verifica Sigstore in Kyverno](https://main.kyverno.io/docs/policy-types/cluster-policy/verify-images/sigstore/); [ImageValidatingPolicy](https://kyverno.io/docs/policy-types/image-validating-policy/) |
| GitLab Ultimate (self-managed) offre pipeline execution policy, merge request approval policy e scan execution policy, conservate in un security policy project, con ambito definito dal compliance framework e un limite predefinito di 5 policy per tipo | [Policy di GitLab](https://docs.gitlab.com/user/application_security/policies/); [Merge request approval policy](https://docs.gitlab.com/user/application_security/policies/merge_request_approval_policies/); [Tutorial sulle pipeline execution policy](https://docs.gitlab.com/tutorials/pipeline_execution_policy/); [Security policy project](https://docs.gitlab.com/user/application_security/policies/enforcement/security_policy_projects/) |
| Streaming degli eventi di audit a livello di istanza GitLab verso una destinazione HTTP (Ultimate, self-managed), con un header che porta il token di verifica. Gli eventi possono essere duplicati, quindi vanno deduplicati su `id` | [Streaming degli eventi di audit per le istanze](https://docs.gitlab.com/administration/compliance/audit_event_streaming/) |
| Semantica di riferimento di S3 Object Lock (AWS). In compliance mode nessun utente, root compreso, può cancellare oggetti o accorciarne la retention. La governance mode può essere aggirata con un permesso specifico. Il legal hold è indipendente. Un DELETE su un bucket con versioning aggiunge solo un delete marker. **Il prodotto on-prem del cliente va verificato rispetto a questa semantica** | [S3 Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock.html); [Considerazioni su Object Lock](https://docs.aws.amazon.com/AmazonS3/latest/userguide/object-lock-managing.html) |
| Livelli della policy di audit di Kubernetes (`None`, `Metadata`, `Request`, `RequestResponse`) e backend di log | [Auditing in Kubernetes](https://kubernetes.io/docs/tasks/debug/debug-cluster/audit/). API stabile; da ricontrollare sulla versione adottata |

## Disaster recovery (verificato il 2026-11-05)

| Affermazione usata nel progetto | Fonte |
|---|---|
| Porte richieste da GitLab Geo: dal secondario al primario TCP 5432 (PostgreSQL) e 5000 (registry); 80/443 su entrambi i siti; aperte in entrambe le direzioni per semplificare il failover. I repository si sincronizzano dal primario via Git su HTTPS con JWT | [Geo](https://docs.gitlab.com/administration/geo/); [Replica del database in Geo](https://docs.gitlab.com/administration/geo/setup/database/) |
| La replica Geo è asincrona, quindi un failover non pianificato può perdere i dati più recenti. Il failover richiede un intervento umano e il fencing del vecchio primario (`gitlab-ctl geo promote`, controlli preliminari). Il container registry non è replicato per default | [Disaster recovery (Geo)](https://docs.gitlab.com/administration/geo/disaster_recovery/); [Failover pianificato](https://docs.gitlab.com/administration/geo/disaster_recovery/planned_failover/); [Riportare in servizio il vecchio primario](https://docs.gitlab.com/administration/geo/disaster_recovery/bring_primary_back/) |
| `OCIRepository` di Flux verifica le firme cosign con chiavi pubbliche conservate in un Secret; se la verifica fallisce, l'artefatto non viene scaricato | [OCI Repositories](https://fluxcd.io/flux/components/source/ocirepositories/); [Cheatsheet sugli artefatti OCI](https://fluxcd.io/flux/cheatsheets/oci-artifacts/) |
| Il data movement degli snapshot CSI di Velero copia i dati degli snapshot su object storage compatibile S3 e può ripristinarli in un altro cluster (serve lo stesso nome di storage class) | [Data movement degli snapshot CSI in Velero](https://velero.io/docs/main/csi-snapshot-data-movement/) |
| CAPV gestisce credenziali vCenter per singolo cluster tramite `VSphereClusterIdentity` / `identityRef` | [Gestione delle identità in CAPV](https://github.com/kubernetes-sigs/cluster-api-provider-vsphere/blob/main/docs/identity_management.md) |

## Alternative di toolchain (verificato il 2026-11-05)

| Affermazione usata nel progetto | Fonte |
|---|---|
| OpenTofu è rilasciato con licenza MPL 2.0 sotto la Linux Foundation ed è un progetto CNCF Sandbox da aprile 2025. Terraform è passato alla licenza BSL nell'agosto 2023 | [The New Stack: OpenTofu entra nella CNCF](https://thenewstack.io/opentofu-joins-cncf-new-home-for-open-source-iac-project/); [heise](https://heise.de/-10367910). Fonti secondarie; da confermare sulla pagina del progetto CNCF |
| Flux e Argo sono progetti CNCF graduated (novembre e dicembre 2022); Backstage è CNCF incubating | [Progetti CNCF](https://www.cncf.io/projects/); [Graduation di Flux](https://www.cncf.io/announcements/2022/11/30/flux-graduates-from-cncf-incubator/); [Graduation di Argo](https://www.cncf.io/announcements/2022/12/06/the-cloud-native-computing-foundation-announces-argo-has-graduated/); [Ingresso di Backstage nell'incubator](https://www.cncf.io/blog/2022/03/15/backstage-project-joins-the-cncf-incubator/) |
| VMware vSphere Kubernetes Service (VKS) fa parte di VMware Cloud Foundation 9 e crea i cluster tramite il Supervisor e ClusterClass | Solo il programma di un corso di formazione: [VKS Design, Deploy, Operate V9](https://www.globalknowledge.com/en-sa/courses/vmware/virtualisation/vmvksddo). **Perimetro del prodotto, licenze e compatibilità vanno verificati nella documentazione Broadcom** |
| Kubernetes pubblica circa tre minor release l'anno, ciascuna supportata per circa 14 mesi | [Release di Kubernetes](https://kubernetes.io/releases/). Da ricontrollare quando si fissano le versioni |

## Coefficienti di dimensionamento (verificato il 2026-11-05)

| Coefficiente usato in [06](06-nfr-and-capacity.md) | Fonte |
|---|---|
| Distributor di Mimir: 1 core + 1 GB ogni 25k campioni/s. Ingester: 1 core + 2,5 GB + 5 GB di disco ogni 300k serie in memoria (RF 3). Grafana le presenta come indicazioni di massima | [Pianificare la capacità di Grafana Mimir](https://grafana.com/docs/mimir/latest/manage/run-production-environment/planning-capacity/) |
| Le indicazioni operative citano numeri di serie per ingester più alti (~2 M), quindi i coefficienti precedenti sono considerati conservativi | [Runbook di Grafana Mimir](https://grafana.com/docs/mimir/latest/manage/mimir-runbooks/) |
| Dimensionamento dei componenti di Loki per fascia di ingest (p90, modalità a microservizi); si usa la fascia più piccola | [Loki: dimensionare il cluster](https://grafana.com/docs/loki/latest/setup/size/) |

## Qualità delle fonti

La maggior parte dei link porta a documentazione ufficiale del vendor o del progetto. Fanno eccezione tre casi, segnalati dove sono usati: lo stato CNCF di OpenTofu viene da articoli di stampa; il perimetro di VMware VKS viene dal programma di un corso di formazione; il link al data source Prometheus è documentazione di Grafana Cloud, relativa alla stessa opzione del data source che usa Grafana self-hosted.

## Piattaforma e delivery (riferimenti generali, da ricontrollare quando si fissano le versioni)

- GitLab Geo: [panoramica](https://docs.gitlab.com/administration/geo/), [configurazione](https://docs.gitlab.com/administration/geo/setup/) e [failover pianificato](https://docs.gitlab.com/administration/geo/disaster_recovery/planned_failover/). Geo è uno standby caldo asincrono, non un'HA istantanea, e la promozione è un processo da provare in anticipo.
- Flux: [documentazione](https://fluxcd.io/flux/) e [bootstrap con GitLab](https://fluxcd.io/flux/installation/bootstrap/gitlab/).
- Kubernetes: [Pod Security Standards](https://kubernetes.io/docs/concepts/security/pod-security-standards/) e [network policy](https://kubernetes.io/docs/concepts/services-networking/network-policies/). Le network policy sono efficaci solo con una CNI compatibile.
- Kyverno: [introduzione](https://kyverno.io/docs/introduction/).
- Cluster API Provider vSphere: [progetto](https://github.com/kubernetes-sigs/cluster-api-provider-vsphere). La matrice di supporto per VMware e Kubernetes va validata.

Non si usa alcun prezzo esterno. Tutti i costi sono assunzioni con limiti dichiarati e vanno sostituiti da proposte aggiornate dei vendor.
