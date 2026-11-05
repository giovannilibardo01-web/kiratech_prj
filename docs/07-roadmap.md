# Roadmap di modernizzazione: prima l'osservabilità (18 mesi)

## Principi operativi

Kiratech si integra con i due workstream attivi e con i quattro team esistenti del cliente, senza sostituire nessuno di essi. Per tutta la durata del programma restano protetti due elementi: la disponibilità della produzione in ciascun sito e il monitor ping/HTTP esistente.

L'osservabilità viene prima di tutto il resto, ma i suoi cluster devono essere creati come codice. Per questo un bootstrap minimo della toolchain di piattaforma (Fase 0b) corre in parallelo alla discovery e precede l'osservabilità stessa. Anche la produzione esistente viene osservata prima che qualsiasi altra cosa cambi su di essa: i collector in sola lettura arrivano in Fase 2, molto prima dell'enforcement delle policy e della migrazione.

Il DR si costruisce prima di spostare la produzione. **Nessuna coorte di produzione passa a un cluster gestito finché non è dimostrata l'autonomia di South (T-18)** e finché, per quella coorte, non sono operativi la controparte DR, la replica e il drill di coorte. L'impegno RPO/RTO verso il business arriva solo dopo il drill sull'intero inventario (T-11), a migrazione conclusa.

Tutte le finestre temporali sono ipotesi di pianificazione. I tempi di approvvigionamento di object storage, host per il broker, HSM/KMS e riserva di capacità di South non sono noti (A-14 li assume tra 8 e 16 settimane) e vengono seguiti come dipendenze sul percorso critico.

## Fasi

| Fase | Finestra | Azioni principali (team responsabile) | Criteri di uscita | Rollback / sospensione |
|---|---|---|---|---|
| Fase 0: discovery e decisioni | Settimane 0–4 | Inventari: cluster e versioni (Q-03), workload e criticità (Q-01, Q-09), prodotti database (Q-15), topologia VMware/vCenter (Q-14), capacità e ownership di IdP, PKI, DNS e secret manager (Q-08, Q-18), posizione del monitor legacy (Q-13), throughput dei collegamenti (Q-05), object storage (Q-04).<br>Decisioni: CAPV o VKS (Q-16), ownership del broker (R-17), decisioni del CISO (modalità di lock, isolamento in lettura), perimetro DR ed eccezioni del CIO.<br>Avvio degli approvvigionamenti.<br>(Platform Engineering, SRE, Data Engineering, Network Security; Kiratech facilita) | Inventario di recovery firmato; flussi firewall presentati; distinta dei componenti con versioni fissate; ordini di acquisto emessi; blocchi della Fase 0 risolti o accettati formalmente | Nessuna modifica in produzione |
| Fase 0b: bootstrap minimo della piattaforma | Settimane 3–8 | Repository OpenTofu e runner protetti; un management cluster per sito, a partire da Central, tramite OpenTofu + CAPV; Flux sui management cluster; repository di baseline protetto; issuer PKI di sito per mTLS (Platform Engineering, Network Security) | In ogni sito un cluster di osservabilità può essere creato e ricreato da codice; il drift viene rilevato e annullato | Management cluster usati solo per il non-prod finché non sono stabili |
| Fase 1: pilota di osservabilità | Mesi 1–3 | Due cluster rappresentativi (uno non critico in Central, uno in South), l'applicazione di riferimento a tre livelli, telemetry gateway (scrittura) e query gateway (lettura), broker (o fallback classico, deciso entro la fine del pilota), prototipo del relay di audit, carico sintetico (SRE; Kiratech) | Metriche, log e trace correlati; ingest a 3×; T-06, T-07, T-14, T-15, T-16 superati su dati sintetici; coefficienti di dimensionamento misurati (scostamento ammesso ±30%) | Rimozione dei collector del pilota; l'applicazione di riferimento mantiene il suo stack locale |
| Fase 2: fondamenta di osservabilità in produzione | Mesi 3–6 | LGTM in HA per sito, creato come codice. Collector Alloy in sola lettura sui cluster di produzione esistenti, senza alcuna modifica ad admission, policy o deployment. Doppio archivio di audit e relay. Dead-man's switch. Tier di capacità. Esecuzione in ombra accanto al monitor legacy e parità per singolo check. L'audit delle API Kubernetes sui cluster esistenti si abilita cluster per cluster come modifica del control plane, con approvazione dell'owner, finestra di change e rollback; finché non è abilitato, la lacuna viene registrata per singolo cluster (R-28). (SRE; Data Engineering per storage e broker; Network Security per i flussi) | Produzione esistente visibile in LGTM; T-08, T-09, T-10, T-17 superati; parità firmata per la prima coorte di check; previsione di storage firmata | Gli alert legacy continuano a chiamare il reperibile; si riduce la raccolta a bassa priorità, mai l'audit |
| Fase 3: golden path sicuro di South | Mesi 5–8 | Template Backstage costruiti sul lavoro dell'ingegnere di South; pipeline GitLab iniettate; lockdown di Flux; policy Kyverno; ESO; TTL e teardown controllato; onboarding dei tenant di telemetria (Platform Engineering; Kiratech) | T-01, T-02, T-03, T-04, T-05, T-12 superati; p95 di creazione del namespace ≤15 min; report di teardown con zero risorse orfane; NFR del catalogo rispettati ([06](06-nfr-and-capacity.md)) | Catalogo in modalità solo richiesta (approvazione manuale) |
| Fase 4: fondamenta di recovery di South | Mesi 6–10 | Servizi abilitanti di South in esercizio ([ADR 0011](adr/0011-south-recovery-dependencies.md)); riserva di capacità; GitLab primario in HA + Geo + contratto di rilascio verso il registry di South; schema di replica per ciascun prodotto database; procedura di dichiarazione e fencing; primi cluster di controparte DR (SRE; Data Engineering; Network Security; Platform Engineering) | **T-18 superato** (precondizione per qualsiasi coorte di produzione); T-13/T-13b, T-19 e T-20 superati | Nessuna coorte di produzione si sposta finché T-18 non è superato |
| Fase 5: migration factory per i cluster esistenti | Mesi 9–15 | Per ciascuna coorte di applicazioni:<br>1. Osservare (già fatto in Fase 2).<br>2. Policy in Audit/Warn, con le relative correzioni.<br>3. Classificare: migrare, oppure mantenere con un'eccezione del CIO.<br>4. Creare il cluster di produzione gestito della coorte e la sua controparte DR, avviare la replica dei dati e superare un drill di coorte (sottoinsieme di T-11).<br>5. Spostare il traffico, mantenendo il vecchio percorso per il rollback.<br>6. Dismettere il vecchio percorso dopo un ciclo di rilascio.<br>(Platform Engineering; Data Engineering per gli spostamenti di dati; owner applicativi) | Il 50% della produzione su cluster gestiti con controparte DR dimostrata entro il mese 12; il 100%, o eccezioni firmate, entro il mese 15; zero interruzioni non pianificate causate dalla migrazione | Rollback per singola applicazione verso il cluster legacy fino alla dismissione |
| G: golden path promosso in produzione (milestone) | Mesi 11–13 | Template di produzione firmato: approvazioni, classificazione dei dati, adesione al DR, finestra di change, perimetro dei secret indipendente (Platform Engineering; approvazione del CISO) | Primi 3 servizi di produzione accolti tramite il template di produzione con zero eccezioni alle policy; percorso di approvazione esercitato; quei servizi inclusi in un drill di coorte | La produzione resta su merge request manuali revisionate |
| Fase 6: prova sull'intero inventario, scala e passaggio di consegne | Mesi 15–18 | Drill di perdita di Central sull'intero inventario (T-11) a migrazione completata; 30 cluster / 1.500 pod; automazione dell'upgrade ring; ridimensionamento della capacità; decisioni di dismissione del legacy per singolo check; passaggio di consegne operativo (tutti e quattro i team; Kiratech consegna) | T-11 entro RPO ≤60 min / RTO ≤240 min → impegno RPO/RTO verso il business; SLO mantenuti; scostamento dei costi entro ±30% della previsione; runbook e registri delle decisioni consegnati | Nessun impegno RPO/RTO se T-11 fallisce; onboarding congelato se la riserva o le quote sono esaurite |

Durante la migrazione la flotta supera temporaneamente i 30 cluster, perché i cluster legacy vengono dismessi coorte per coorte. La capacità di control plane necessaria per la sovrapposizione è inclusa come costo una tantum ([10](10-cost-and-tco.md)).

## Dipendenze sul percorso critico

| Dipendenza | Necessaria per | Tempo di approvvigionamento (assunzione) | Owner | In caso di ritardo |
|---|---|---|---|---|
| Storage compatibile S3 per sito (LGTM + archivi di audit) | Fasi 1–2 | 8–16 settimane | Data Engineering | Pilota su storage temporaneo; la Fase 2 slitta |
| Piattaforma broker per sito | Fase 1 (decisione entro la fine del pilota) | 4–8 settimane, subordinate all'impegno di Data Engineering | Data Engineering | Fallback su Mimir classico / Tempo monolitico ([ADR 0004](adr/0004-observability-topology.md)) |
| Flussi firewall approvati | Fasi 1–2, 4 | 2–6 settimane per lotto di modifiche | Network Security | Il pilota resta su un solo sito |
| HSM/KMS per sito | Fasi 2–3 | 8–12 settimane | Network Security | Firma e manifest di audit usano un KMS software provvisorio, documentato come rischio |
| Indipendenza del vCenter di South, riserva di capacità, GitLab HA | Fase 4 | Sconosciuto (Q-14) | Platform Engineering / owner VMware | Migrazione della produzione e impegno DR bloccati ([ADR 0011](adr/0011-south-recovery-dependencies.md)) |

## Ciclo di vita dei cluster e upgrade ring

Kubernetes pubblica circa tre minor release l'anno, ciascuna supportata per circa 14 mesi. Con 30 cluster non si può lasciare che le versioni divergano senza controllo, e serve quindi una cadenza fissa. Gli aggiornamenti seguono un ring che parte dal non-prod di South, passa al DR di South e arriva alla produzione di Central.

Proponiamo **tre ondate l'anno**, una per ogni minor upstream: su 30 cluster sono circa 90 upgrade l'anno (stima). L'alternativa è fare due ondate l'anno, ciascuna delle quali sale fino a due minor in sequenza. In entrambi i casi il DR viene aggiornato prima della produzione, così un failover non atterra mai su un cluster più vecchio.

L'upgrade avviene con la sostituzione progressiva delle macchine gestita da CAPV. Il livello di Pod Security (`enforce-version`) è fissato alla minor di ciascun cluster e viene alzato nella stessa modifica dell'upgrade, dopo un passaggio in modalità audit. Prima di ogni ondata una scansione in pipeline confronta i manifest con la versione di destinazione per individuare le API deprecate. L'owner è Platform Engineering, e l'impegno rientra negli FTE di esercizio di Platform Engineering stimati in [10](10-cost-and-tco.md).

## Esercizio in parallelo e cutover delicati

Il monitor black-box legacy viene dismesso check per check, seguendo i sei passi descritti in [03](03-observability-deep-dive.md) §11. La parità è firmata dall'owner di ciascun check e, anche dopo la dismissione, resta una sonda esterna indipendente minima che rileva un'interruzione totale dell'osservabilità.

I cluster esistenti non vengono mai ricreati solo per uniformarli. Il percorso è sempre lo stesso: prima si osservano, poi le policy passano in Audit/Warn, si correggono le non conformità e infine si migra per coorte, con una controparte DR, oppure si mantiene il cluster sotto eccezione. I cluster non gestiti sono rischi tracciati (R-25), non assunzioni invisibili.

L'applicazione di riferimento mantiene il suo stack locale come materiale di apprendimento finché la pipeline di sito non è dimostrata. L'architettura dell'applicazione e la sua pipeline di osservabilità non vengono mai modificate nello stesso momento.

Del golden path di South si conservano RBAC, quote, default-deny, PSS, policy engine, secret esterni e, nelle pipeline GitLab CI, scansione, SBOM e firma: tutto questo viene impacchettato come template Backstage, e non costruiamo un template parallelo in concorrenza ([11](11-existing-workstreams.md)).

Per GitLab, backup, restore e Geo nelle modalità supportate vengono provati in Fase 4, prima che la produzione dipenda da essi. Una promozione Geo fallita compromette il ripristino della CI, mentre il DR di produzione si appoggia al contratto con il registry di South.

## Governance e passaggi di fase

Ogni fase si chiude con una revisione degli ADR registrata e con l'aggiornamento del threat model, con i runbook, la dashboard e i link alle evidenze, con dimensionamento e costi rivisti, con una decisione esplicita sul rollback e con una revisione insieme agli owner dei team del cliente *esistenti*.

Durante l'ingaggio Kiratech è l'autorità di progetto, mentre le approvazioni restano agli owner operativi del cliente. Non è previsto alcun passaggio silenzioso dal pilota alla produzione ottenuto ridistribuendo un chart in un altro namespace.
