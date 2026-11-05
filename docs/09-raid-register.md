# Registro RAID: rischi, assunzioni, problemi e decisioni

Ogni voce del registro resta **aperta finché non è supportata da evidenze esplicite e approvata formalmente**. Probabilità e impatto sono valutazioni qualitative e preliminari.

## Rischi

| ID | Rischio / impatto | Livello | Owner | Mitigazione / prova richiesta |
|---|---|---|---|---|
| R-01 | Capacità di South insufficiente per l'intero tier di Central; RTO di 4 h mancato | Critico | SRE | Riserva di cluster DR caldi e anche di compute, storage e ingress; drill di carico ed evacuazione; nessuna migrazione della produzione senza approvazione formale |
| R-02 | L'unica istanza GitLab in Central e il ritardo asincrono di Geo lasciano il control plane senza una sorgente di recovery valida | Critico | Platform Engineering | Primario HA e secondario Geo supportati, monitoraggio del ritardo ≤60 min, backup, promozione e fencing provati |
| R-03 | L'indisponibilità di identità, PKI, vault o DNS di Central paralizza il failover su South | Critico | Network Security | Servizi indipendenti per sito, recovery offline, doppio controllo, test integrato di isolamento del sito |
| R-04 | Banda tra siti o firewall non in grado di sostenere la replica di DB, audit e Geo | Critico | Network Security | Misura del throughput, matrice dei flussi pre-approvata, allarmi sul ritardo, RPO misurato, collegamenti di riserva |
| R-05 | Copie di audit modificabili, impostazioni di lock errate o la perdita dell'unico sito di archivio violano la garanzia di conservazione dell'audit per 1 anno | Critico | CISO | Doppio archivio (North + South) in compliance mode con amministrazione separata, manifest firmati e concatenati tramite hash, verificatore giornaliero, test di negazione della cancellazione, recupero ≤4 h ([ADR 0010](adr/0010-audit-evidence-and-retention.md)) |
| R-06 | Una gestione errata dell'header del tenant espone telemetria tra team diversi | Alto | SRE | Il gateway autenticato sovrascrive gli header del tenant, test negativo di isolamento delle query, limiti per tenant |
| R-07 | Picchi di cardinalità o di log esauriscono lo storage o il budget | Alto | SRE | Allowlist delle label, quote, test di ingest a 3×, alert sulla perdita di dati e previsioni di storage |
| R-08 | Le policy di deny rompono i workload esistenti al momento dell'adozione | Alto | Platform Engineering | Prima warn/audit, correzioni di compatibilità, rollout per coorte, attivazione reversibile |
| R-09 | Un'incompatibilità del provider vSphere di Cluster API blocca l'automazione del ciclo di vita | Alto | Platform Engineering | Pilota sulla matrice di compatibilità; fallback documentato in un ADR alternativo (solo OpenTofu o altra soluzione approvata) |
| R-10 | Tempeste di falsi positivi spingono SRE a disattivare gli alert | Alto | SRE | Burn rate SLO multi-finestra, owner e runbook obbligatori per ogni alert, revisione settimanale dell'azionabilità, coesistenza con il legacy |
| R-11 | Valori di secret finiscono nella cronologia Git, nei log o negli artifact CI | Alto | Platform Engineering | Solo riferimenti a secret esterni, runner protetti, secret scanning e test di prevenzione della fuga di token |
| R-12 | Contesa di risorse tra i tenant di test di South e la capacità dei cluster DR | Alto | SRE | 10 cluster DR caldi dedicati, riserva rigida sul sito, policy di preemption per il non-prod; drill trimestrali |
| R-13 | Il vendor dello storage non supporta la semantica di object store richiesta da Loki/Mimir o l'immutabilità | Alto | Data Engineering | Test anticipato di API a oggetti e consistenza, distinta approvata dei componenti di storage |
| R-14 | Un'interruzione dell'osservabilità stessa nasconde un guasto della piattaforma | Alto | SRE | Watchdog esterno e monitor black-box indipendente mantenuto; canary per sito |
| R-15 | Il carico crescente dei control plane di 30 cluster supera la capacità del team | Medio | Platform Engineering | Automazione del ciclo di vita, ring di versione, margine di capacità, budget di ownership dettagliato |
| R-16 | Una versione o un upgrade non supportato di Grafana/Tempo compromette la durabilità dei dati | Alto | SRE | Versioni fissate, matrice di supporto, test di durabilità dei trace e di failover con carico a 3× |
| R-17 | Data Engineering non riesce a gestire un broker compatibile con Kafka per sito per il pilota di Fase 1 (ingest storage di Mimir / Tempo a microservizi) | Alto | Data Engineering | Decisione sull'impegno in Fase 0; go/no-go sul broker entro la fine del pilota; fallback su Mimir classico + Tempo monolitico in un ADR sostitutivo ([ADR 0004](adr/0004-observability-topology.md)) |
| R-18 | L'object store on-prem scelto non offre la semantica S3 Object Lock in compliance mode | Alto | Data Engineering | Verifica del prodotto prima dell'acquisto; fallback su appliance WORM ([ADR 0010](adr/0010-audit-evidence-and-retention.md)) |
| R-19 | La transizione delle API di Kyverno (`ClusterPolicy` e PolicyException `kyverno.io` deprecate → tipi basati su CEL) rompe le policy durante gli upgrade | Medio | Platform Engineering | Nuove policy scritte nei tipi basati su CEL; migrazione all'interno dell'upgrade ring; test di conformità delle policy per ogni ring |
| R-20 | Il transparency log self-hosted (Rekor) non è approvato o non è gestibile per sito | Medio | Platform Engineering | Fallback su Notation con certificati x509 della PKI di sito ([ADR 0003](adr/0003-tenancy-and-policy.md), opzione iv) |
| R-21 | L'impegno di costruzione o di esercizio del query gateway supera il piano e ritarda l'isolamento del percorso di lettura | Medio | SRE | Pilota del gateway in Fase 1; LBAC Enterprise + gateway Tempo come alternativa già valorizzata nei costi ([ADR 0012](adr/0012-telemetry-tenancy-and-read-isolation.md)) |
| R-22 | Gli host VMware di South sono gestiti da un vCenter in Central, quindi CAPV non può scalare i cluster DR dopo la perdita di Central | Critico | Platform Engineering | Inventario in Fase 0 (Q-14); vCenter indipendente in South, oppure worker pool DR pre-dimensionati con accettazione del CIO ([ADR 0011](adr/0011-south-recovery-dependencies.md)) |
| R-23 | IdP/directory aziendale presente solo in Central, quindi nessun login possibile in South dopo la perdita di Central | Critico | Network Security | Istanza IdP in South sincronizzata (F-15); account break-glass sigillati; T-18 |
| R-24 | Un prodotto database di produzione non può replicare in modo asincrono tra siti e porta un restore sul percorso critico | Alto | Data Engineering | Schema di replica per prodotto in Fase 0; in alternativa, ri-piattaformare l'applicazione o accettare un RTO più lungo con un'eccezione firmata dal CIO ([ADR 0005](adr/0005-backup-disaster-recovery.md)) |
| R-25 | Workload di produzione restano su cluster legacy creati a mano, senza controparti DR, oltre la finestra di migrazione prevista | Alto | Platform Engineering | Coorti di migrazione nella roadmap; eccezioni del CIO per singola applicazione che dichiarano la reale capacità di recovery; nessuna esclusione implicita |
| R-26 | La manutenzione dei plugin e degli upgrade di Backstage supera la capacità di Platform Engineering | Medio | Platform Engineering | Plugin ridotti al minimo; Red Hat Developer Hub come alternativa supportata; fallback GitLab nativo in modalità solo richiesta ([ADR 0001](adr/0001-platform-toolchain.md)) |
| R-27 | I tempi di approvvigionamento (storage, host per il broker, HSM/KMS, riserva di South) ritardano la sequenza che parte dall'osservabilità | Alto | SRE | Ordini emessi in Fase 0; pilota su storage temporaneo; tabella delle dipendenze nella [roadmap](07-roadmap.md) |
| R-28 | Su alcuni cluster esistenti l'audit delle API Kubernetes non si può abilitare senza modifiche invasive al control plane, e resta una lacuna di audit fino alla migrazione | Alto | Platform Engineering | Modifica del control plane per singolo cluster, con finestra e rollback; lacuna registrata per cluster e accettata dal CISO; chiusa dalla migrazione ([07](07-roadmap.md), Fase 2) |
| R-29 | L'ownership di identità, PKI e secret manager non rientra nel mandato di nessuno dei quattro team (A-17) | Alto | Network Security | CISO e CIO confermano l'owner in Fase 0 (Q-18); in alternativa, owner Platform Engineering con Network Security consultato |

## Decisioni in attesa di input del cliente

| ID | Domanda aperta | Owner | Entro quando / evidenza di chiusura |
|---|---|---|---|
| Q-01 | Qual è l'inventario, con la relativa criticità, di tutte le applicazioni e di tutti i servizi dati di produzione? | Data Engineering + Platform | Fase 0, mappa di recovery dei workload firmata |
| Q-02 | Quanta CPU/RAM VMware libera c'è in totale in South, con quali fault domain, IOPS e margine di rete? | SRE | Fase 0, allocazione delle risorse riservate |
| Q-03 | Quali sono le versioni attuali di K8s, CNI, CSI, VMware, GitLab e degli strumenti di monitoraggio? | Platform | Fase 0, valutazione di compatibilità |
| Q-04 | Piattaforma di object storage: API S3, versioning, retention lock ed erasure coding supportato? | Data Engineering | Fase 1, prova di durabilità e di retention |
| Q-05 | Qual è la banda effettiva tra i siti e qual è il tempo di attivazione dei flussi firewall? | Network Security | Fase 0, test di traffico e throughput |
| Q-06 | Che cosa conta esattamente come un'interruzione della piattaforma, e qual è l'orario lavorativo? | SRE | Fase 0, definizione SLI/SLO firmata |
| Q-07 | Chi è formalmente autorizzato dal CISO ad approvare le eccezioni alle policy e l'accesso all'audit? | Network Security | Prima della modalità enforce |
| Q-08 | Quali capacità DR hanno oggi vault, IdP, PKI, DNS e load balancer? | Network Security | Prima della verifica di autonomia di South |
| Q-09 | Quali workload richiedono un cluster di produzione dedicato anziché l'isolamento a livello di namespace? | Platform / Data | Prima dell'acquisto del mix di cluster |
| Q-10 | Quanto dura una promozione Geo per il ripristino della CI? È fuori dal percorso critico della produzione ([ADR 0007](adr/0007-source-control-and-recovery.md)) | Platform | Fase 4, prova controllata |
| Q-11 | Esistono vincoli di legal hold, PII o retention regolamentare oltre l'anno dichiarato? | Network Security/CISO | Prima dell'accettazione da parte del CISO |
| Q-12 | Quali sono il costo pieno effettivo di un FTE, l'offerta per Grafana Enterprise e l'ammortamento dell'hardware on-prem? | SRE / CFO | Prima dell'approvazione dell'investimento |
| Q-13 | Dove gira il monitor ping/HTTP legacy? Se è in Central, non è indipendente dalla perdita di Central | SRE | Inventario di Fase 0 |
| Q-14 | Come è gestito oggi VMware: un vCenter per sito o uno condiviso? Con quale dominio SSO? | Platform Engineering | Fase 0; blocca la verifica di autonomia di South |
| Q-15 | Quali prodotti database di produzione sono in uso, e quali supportano la replica asincrona tra siti? | Data Engineering | Fase 0, mappa di recovery dei workload firmata |
| Q-16 | Il cliente ha licenze VMware Cloud Foundation con vSphere Kubernetes Service, e in quale versione? (Decide tra CAPV e VKS) | Platform Engineering | Fase 0 |
| Q-17 | Quale policy engine usa il golden path esistente di South? | Platform Engineering + ingegnere di South | Fase 0, revisione del workstream |
| Q-18 | Quale dei quattro team è owner di IdP, PKI, secret manager, HSM/KMS e chiavi di firma? (A-17) | CISO + Network Security | Fase 0, prima di congelare il progetto dell'autonomia di South |

## Governance delle assunzioni

Le assunzioni `A-01..A-19` descritte in [perimetro e assunzioni](01-scope-and-assumptions.md) **non** sono vincoli verificati: per ciascuna quel documento indica un owner e il momento della validazione. Prima di impegnare acquisti o di fissare il progetto di produzione, ognuna diventa `Validated`, `Rejected` o `Revised` in un ADR. Nessun elemento chiuso può essere riaperto in silenzio modificando soltanto il diagramma.
