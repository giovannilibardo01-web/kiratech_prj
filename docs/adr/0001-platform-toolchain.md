# ADR 0001: toolchain della piattaforma (IaC, ciclo di vita dei cluster, GitOps, catalogo e uso di GitLab Ultimate)

- Stato: proposta, in attesa di revisione da parte del cliente. La scelta sul ciclo di vita dei cluster dipende dall'inventario VMware della Fase 0.
- Data: 2026-11-05
- Decisori: Platform Engineering
- Revisori: SRE, Data Engineering, Network Security, Kiratech (design authority)
- Documenti correlati: [architettura](../02-architecture.md), [ADR 0003](0003-tenancy-and-policy.md), [ADR 0007](0007-source-control-and-recovery.md)

## Contesto

Il cliente usa VMware per la virtualizzazione e Kubernetes per l'orchestrazione. I cluster esistenti sono stati costruiti a mano e nel tempo si sono allontanati l'uno dall'altro per versione e configurazione. GitLab Ultimate è già in licenza, quindi la piattaforma deve usarne le funzioni invece di duplicarle. Tutti gli ambienti di deployment sono codice e nessun valore segreto viene mai salvato in Git. I componenti open source sono la scelta predefinita e un abbonamento a pagamento va giustificato sul piano dei costi. Non è imposto alcuno strumento di IaC, GitOps o gestione del ciclo di vita dei cluster: per questo ogni scelta è registrata, con la sua motivazione, in questa serie di ADR.

Il requisito non funzionale principale è il self-service. La piattaforma deve funzionare sito per sito, senza dipendere a runtime da Central quando Central viene perso.

Le quattro scelte che seguono sono valutate con gli stessi criteri:

1. aderenza ai vincoli: VMware, on-prem, GitLab, nessun segreto in Git;
2. indipendenza di ciascun sito: nessun percorso di controllo tra siti necessario a runtime;
3. funzionamento dichiarativo e correzione del drift;
4. modello di licenza e lock-in;
5. maturità e comunità, con lo stato CNCF come indicatore (verificato il 2026-11-05);
6. competenze del cliente e sforzo operativo;
7. integrazione con GitLab Ultimate;
8. costo di uscita se la scelta viene ribaltata.

## Opzioni considerate

### 1. Infrastructure as code

| Opzione | Punti di forza | Punti deboli | Esito |
|---|---|---|---|
| OpenTofu | Open source (MPL 2.0, Linux Foundation; CNCF Sandbox da aprile 2025). Linguaggio e provider compatibili con Terraform, incluso vSphere (da verificare sulla versione adottata). State remoto protetto | Ecosistema di supporto commerciale più piccolo di quello di Terraform; la compatibilità di provider e versioni va fissata con pin espliciti | Scelto |
| Terraform | Ecosistema più ampio, supporto commerciale disponibile | Nel 2023 la licenza è passata a BSL, che non è una licenza open source approvata da OSI; è in contrasto con la preferenza per l'open source, salvo giustificazione | Scartato come default; da riconsiderare se il supporto del vendor diventa obbligatorio |
| Crossplane | Nativo Kubernetes, riconciliazione continua dell'infrastruttura | Richiede un control plane già in funzione prima che l'infrastruttura esista, il che crea un ciclo di bootstrap proprio per i management cluster. Copertura VMware più debole | Scartato per il bootstrap; potrà affiancarsi in seguito per le risorse cloud gestite dall'interno dei cluster |
| Automazione nativa VMware (PowerCLI, VCF automation) | Nativa per VMware | Imperativa o proprietaria; revisione e diff in GitLab meno efficaci; non copre DNS, LB e S3 | Scartata come strumento principale |

OpenTofu gestisce le primitive VMware (cartelle, resource pool e relative prenotazioni, reti, template), il bootstrap dei management cluster, gli oggetti DNS, LB e firewall dove esistono API, e i bucket S3 con le loro policy. Non gestisce le risorse dentro i cluster, che sono compito di Flux. **Nessun valore segreto passa da OpenTofu**: lo strumento crea soltanto i percorsi e le policy del secret manager, mentre le credenziali arrivano ai cluster tramite External Secrets ([04](../04-security-and-tenancy.md) §5). Lo state è conservato in un backend versionato, con lock e log degli accessi, replicato in South (classe di dato D7 in [05](../05-reliability-and-dr.md)). Come difesa in profondità abilitiamo anche la cifratura dello state di OpenTofu, da verificare sulla versione adottata.

### 2. Ciclo di vita dei cluster

| Opzione | Punti di forza | Punti deboli | Esito |
|---|---|---|---|
| Cluster API + CAPV | Open source, dichiarativo, aggiornamento per sostituzione progressiva; un management cluster per sito, che lavora sul vCenter dello stesso sito (`VSphereClusterIdentity`); adatto a GitOps | Richiede una matrice di supporto VMware/Kubernetes; il management cluster è un componente in più; non adotta i cluster creati a mano | Scelto come default |
| VMware vSphere Kubernetes Service (VKS, parte di VMware Cloud Foundation) | Supportato dal vendor sull'hypervisor del cliente; un Supervisor per vCenter, coerente con l'indipendenza dei siti; provisioning basato su ClusterClass | Richiede licenze VCF e ne segue la cadenza di versione; perimetro del prodotto e prezzi da verificare con Broadcom | Alternativa preferita se il cliente ha già licenze VCF con VKS (decisione della Fase 0) |
| Rancher (Rancher Manager + RKE2) | UI matura; può importare i cluster esistenti per dare una visibilità centrale | Aggiunge un altro piano di gestione e un altro dominio di identità; un Rancher centrale diventa una dipendenza tra siti, a meno di installarne uno per sito; il supporto è in abbonamento | Scartato come strumento principale; la visibilità sui cluster esistenti è coperta da LGTM |
| Manuale / kubeadm e script | Familiare ai team attuali | È il modo di lavorare che ha prodotto i cluster eterogenei di oggi; non è dichiarativo | Scartato |

### 3. GitOps

| Opzione | Punti di forza | Punti deboli | Esito |
|---|---|---|---|
| Flux (CNCF graduated) | Modello pull per cluster: nessuna credenziale centrale di push attraversa i firewall. Lockdown multi-tenancy con impersonation. Artifact OCI nativi con verifica cosign, che costituiscono il contratto di rilascio per il DR descritto in [ADR 0007](0007-source-control-and-recovery.md) | Nessuna UI nativa di primo livello; se serve, va aggiunta una dashboard | Scelto |
| Argo CD (CNCF graduated) | UI solida; AppProject per la tenancy | Il deployment tipico hub-and-spoke detiene credenziali verso molti cluster, cioè una dipendenza tra siti e un bersaglio di alto valore. Con un'istanza per cluster si perde buona parte del vantaggio della UI | Scartato; da riconsiderare se il feedback sull'esperienza degli sviluppatori lo richiede |
| Push da GitLab CI (`kubectl`/Helm dalle pipeline) | Nessun componente aggiuntivo | Nessuna correzione del drift; i runner hanno bisogno di credenziali di scrittura verso ogni cluster; smette di funzionare se si perde Central | Scartato per la riconciliazione; la CI resta per build, test, firma e approvazione |

### 4. Catalogo self-service

| Opzione | Punti di forza | Punti deboli | Esito |
|---|---|---|---|
| Backstage (CNCF incubating) | Catalogo ricco e software template; integrazione con GitLab; on-prem; coerente con il requisito principale del self-service | La manutenzione di plugin e aggiornamenti richiede competenze TypeScript; ha una propria HA e un proprio database | Scelto, con istanza primaria in South |
| Red Hat Developer Hub (distribuzione supportata di Backstage) | Stesso modello, con supporto del vendor | Costo dell'abbonamento | Alternativa se lo sforzo di manutenzione di Backstage supera quanto pianificato |
| Nativo GitLab (project template, issue form, CI) | Nessun componente aggiuntivo | Esperienza debole su catalogo e ownership | Modalità di ripiego "solo richiesta" quando Backstage non è disponibile |
| Portali SaaS (Port, Cortex) | Avvio rapido | Viola il vincolo on-prem | Scartato |

### 5. Scelte di supporto

Per l'admission control proponiamo Kyverno, dopo aver considerato OPA Gatekeeper e l'uso della sola ValidatingAdmissionPolicy nativa: Kyverno include già la verifica delle immagini, le eccezioni e la generazione di risorse. Se il golden path esistente in South usa già un altro motore, in Fase 0 ci allineiamo a quello invece di gestirne due.

Per i secret adottiamo External Secrets Operator con un secret manager per sito. Abbiamo considerato anche Secrets Store CSI, mentre SOPS e Sealed Secrets sono esclusi dal vincolo sui segreti in Git, salvo un'eccezione di sicurezza. Il disegno completo è in [04](../04-security-and-tenancy.md) §5.

## Decisione

Per l'infrastruttura come codice adottiamo OpenTofu. Il ciclo di vita dei cluster è affidato a Cluster API con CAPV, con un management cluster per sito; passiamo a VKS se la Fase 0 conferma licenze e compatibilità di VCF/VKS. La riconciliazione GitOps è affidata a Flux e il catalogo self-service è Backstage. GitLab Ultimate resta il sistema per sorgenti, CI, policy di sicurezza, registry, audit e DR di Git.

Il confine di fiducia del bootstrap è tracciato così. I repository di gestione privilegiati e i runner protetti sono separati dai repository dei tenant. Backstage non ha alcuna identità sui cluster e si limita ad aprire merge request. OpenTofu gira su runner protetti con credenziali di breve durata e di ambito ristretto, e lo state non viene mai emesso in forma grezza.

### Funzioni di GitLab Ultimate e requisiti che coprono

| Funzione (GitLab Ultimate, self-managed) | Uso | Requisito servito |
|---|---|---|
| Branch protetti, CODEOWNERS, approvazioni delle merge request | Sì | I team non possono indebolire la baseline |
| Security policy: pipeline execution, scan execution, merge request approval policy | Sì | Controlli non aggirabili ([ADR 0003](0003-tenancy-and-policy.md)) |
| Compliance framework e report di conformità | Sì | Evidenza che i controlli sono applicati |
| SAST, secret detection (inclusa la push protection), scansione di dipendenze, container e IaC | Sì | Scansioni del golden path |
| Elenco delle dipendenze / export SBOM | Sì | Evidenza SBOM per ogni rilascio |
| Vulnerability report e security dashboard | Sì | Evidenze per il CISO |
| License compliance (license approval policy) | Sì | Governance dell'open source |
| Audit event e streaming degli audit event a livello di istanza | Sì | Evidenze di audit per un anno ([ADR 0010](0010-audit-evidence-and-retention.md)) |
| Protected environment e approvazioni dei deployment | Sì | Approvazione delle modifiche in produzione |
| Container registry e package registry | Sì | Artifact firmati; copia in South tramite il contratto di rilascio |
| Geo | Sì | DR del control plane ([ADR 0007](0007-source-control-and-recovery.md)) |
| Componenti del CI/CD catalog | Sì | Mattoni riutilizzabili per le pipeline del golden path |
| Value stream analytics / metriche DORA | Sì | KPI della piattaforma (lead time, tempo di onboarding) |
| DAST | Più avanti (Fase 6) | Solo per i servizi esposti all'esterno |
| State OpenTofu gestito da GitLab | Preferito se Geo lo replica entro l'RPO (da verificare sulla versione adottata); altrimenti il backend S3 | Tiene state, lock e controllo degli accessi in GitLab |
| Container registry di GitLab o registry OCI separato in South | Entrambi | Il registry GitLab è il sistema di riferimento. Il registry separato in South è un'eccezione voluta alla regola di usare GitLab il più possibile: rende il DR di produzione indipendente dalla promozione e dal ritardo di Geo ([ADR 0007](0007-source-control-and-recovery.md)). Da riconsiderare se durante T-13b si dimostra il pull dal secondario sul registry replicato da Geo |
| GitLab agent for Kubernetes | Opzionale (da verificare sulla versione adottata) | Possibile visibilità di Flux in GitLab; non è su alcun percorso critico |

## Conseguenze

Otteniamo una riconciliazione pull, verificabile e locale a ciascun sito. Il nucleo è interamente open source e per ogni livello è già individuata un'alternativa supportata (VKS, Red Hat Developer Hub, Terraform, Grafana Enterprise); il contratto GitLab esistente viene usato il più possibile.

Il prezzo ricade su Platform Engineering, che deve mantenere Backstage, CAPI/CAPV, Flux e una matrice delle versioni supportate, oltre a un management cluster in ogni sito.

Cluster API non adotta i cluster creati a mano. I cluster legacy vengono quindi prima messi sotto osservazione e poi migrati per coorti ([07](../07-roadmap.md)).

Se una scelta va ribaltata, i costi di uscita sono questi:

- OpenTofu ↔ Terraform: bassi;
- CAPV ↔ VKS: medi, perché entrambi usano i concetti di Cluster API (da verificare);
- Flux ↔ Argo CD: medi, perché i manifest si riusano ma il cablaggio della tenancy no;
- Backstage ↔ Red Hat Developer Hub: bassi.

## Validazione

Nel pilota vanno dimostrati quattro risultati:

- creare, aggiornare e distruggere un ambiente non di produzione a partire da una richiesta di catalogo in ≤15 min al p95 dopo l'approvazione, senza alcuna identità elevata del catalogo;
- modificare a mano un namespace e mostrare che viene riconciliato, con il drift registrato;
- eseguire un upgrade rolling con CAPV di un cluster non di produzione sul vCenter di South;
- riconciliare un cluster DR dal registry di South con Central isolato.

In Fase 0 servono l'inventario delle licenze e delle versioni VMware/VCF, che decide tra CAPV e VKS, e l'indicazione del motore di policy usato oggi dal golden path.

## Trigger di revisione

- Se VCF con VKS risulta in licenza e compatibile, il ciclo di vita passa a VKS.
- Se per l'IaC diventa obbligatorio il supporto del vendor, si passa a Terraform.
- Se il feedback sull'esperienza degli sviluppatori dopo la Fase 3 lo richiede, si valutano la UI di Argo CD o Red Hat Developer Hub.
- Se la matrice di supporto di CAPV resta indietro rispetto alle versioni Kubernetes richieste, si rivaluta lo strumento per il ciclo di vita.
