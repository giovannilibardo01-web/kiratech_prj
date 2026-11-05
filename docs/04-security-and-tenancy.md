# Sicurezza, compliance, tenancy e supply chain

Questo documento poggia su tre decisioni architetturali: [ADR 0003](adr/0003-tenancy-and-policy.md) per tenancy, privilegi GitOps, admission control e firma; [ADR 0010](adr/0010-audit-evidence-and-retention.md) per le evidenze di audit; [ADR 0012](adr/0012-telemetry-tenancy-and-read-isolation.md) per l'isolamento della telemetria.

Seguiamo la stessa convenzione dell'[approfondimento sull'osservabilità](03-observability-deep-dive.md): teniamo distinte le scelte di progetto, i punti da verificare e ciò che è stato testato. Nessuno dei controlli descritti qui è stato ancora testato.

## 1. Confine di fiducia

Nessun input fornito dagli utenti può attribuirsi un'autorità privilegiata sulla piattaforma. La regola vale per i form di Backstage, i repository Git dei tenant, i job delle pipeline GitLab, i service account Kubernetes e la telemetria dei workload.

Le autorità fidate e i rispettivi owner sono questi:

| Autorità | Owner |
|---|---|
| Gruppi GitLab protetti, progetto delle security policy e runner protetti | Platform Engineering |
| Policy-as-code nel repository di baseline protetto | Platform Engineering, con CODEOWNERS delegati dal CISO sui percorsi delle policy |
| PKI, IdP e firewall di ciascun sito | Network Security (la titolarità di identità e PKI è l'assunzione A-17) |
| Secret manager e HSM o KMS di ciascun sito | Network Security gestisce il servizio; il CISO approva il recovery |
| Archivi di audit e relativo amministratore della retention | Storage: Data Engineering. Retention: persona designata dal CISO |

Ogni eccezione ha una scadenza, viene revisionata, registrata e rivalidata automaticamente.

## 2. Tenancy: il golden path è un prodotto diverso per ogni tier

Il modello di tenancy cambia con il tier, perché cambiano il rischio e i dati in gioco.

Gli ambienti di sviluppo sono namespace su un cluster non di produzione condiviso in South. La creazione è automatica se quota, namespace e associazione al team superano i controlli; si usano solo dati sintetici o mascherati, `dataClassification` è limitata a `public`/`internal` e l'RBAC per gruppo segue il minimo privilegio. Gli ambienti di test stanno sullo stesso tipo di cluster: la creazione è automatica entro il budget, mentre integrazioni ed eccezioni di rete richiedono un'approvazione. Usano dataset mascherati o sintetici e ingress temporanei, con un TTL di al massimo 90 giorni imposto sia dalla pipeline sia da un controller di pulizia.

La pre-produzione usa namespace o cluster isolati secondo la classificazione di rischio. Serve l'approvazione della piattaforma, più quella di Data Engineering o di Network Security quando l'ambiente tocca i loro ambiti. I controlli sono analoghi a quelli di produzione, le versioni sono firmate e revisionate e si verificano gli SLO.

In produzione i workload critici o sensibili girano su cluster dedicati in Central, segmentati per namespace al loro interno. **Non esiste creazione di ambienti di produzione senza presidio umano**: servono l'approvazione della merge request, environment protetti e una finestra di change. Ogni ambiente di produzione ha un tier DR obbligatorio, tracciabilità delle modifiche, egress ristretto, workload identity e uno scope di secret indipendente. Le controparti DR calde in South sono di livello produttivo: restano in standby in sola lettura fino alla promozione, che avviene solo dopo il fencing, applicano gli stessi controlli, accettano le chiavi di firma di entrambi i siti e hanno secret locali al sito e replica dei dati.

Quanto al golden path esistente in South, basato su namespace, lo manteniamo come concetto per sviluppo e test, ma non lo promuoviamo in produzione così com'è. Il template di produzione aggiunge approvazioni di ownership, classificazione di criticità, collocazione sul cluster in base al rischio, un tier obbligatorio di backup e DR, revisione di rete, finestre di change ed evidenze di SLO e DR. La milestone di promozione è nella [roadmap](07-roadmap.md).

## 3. Cosa un tenant non può fare e che cosa glielo impedisce

Per ogni tentativo di un tenant di uscire dal proprio perimetro la tabella indica il controllo primario, il secondo controllo e il test negativo che lo verifica.

| Tentativo | Controllo primario | Secondo controllo | Test |
|---|---|---|---|
| Ottenere diritti a livello di cluster tramite GitOps (ClusterRoleBinding, CRD, webhook) | Flux impersona un service account del tenant limitato al namespace; il service account di default non ha permessi | Le policy di admission si applicano anche ai reconciler dei tenant | T-02 |
| Referenziare sorgenti o remote base di un altro tenant | `--no-cross-namespace-refs`, `--no-remote-bases` | Separazione dei repository | T-02 |
| Eliminare i controlli obbligatori della pipeline | Pipeline execution policies di GitLab, definite nel progetto protetto delle security policy | L'admission control continua a imporre le regole al momento del deploy | T-02 |
| Approvare da sé una modifica di policy o un'eccezione | Merge request approval policies e CODEOWNERS (delegato del CISO); eccezioni solo in un namespace protetto | Pulizia alla scadenza e report di conformità | T-02 |
| Deployare un'immagine non firmata o alterata | Verifica della firma in admission, per digest, contro le chiavi di entrambi i siti | Allowlist dei registry | T-04 |
| Leggere i secret di un altro team | `SecretStore` namespaced, autenticato dal service account del namespace e limitato al percorso del team | Kyverno vieta gli store creati dai tenant fuori dal percorso del team | T-05 |
| Leggere la telemetria di un altro team | Un'organizzazione Grafana per team più il query gateway ([ADR 0012](adr/0012-telemetry-tenancy-and-read-isolation.md)) | Endpoint dei backend raggiungibili solo dal gateway | T-14 |
| Scrivere telemetria nel tenant di un altro team | Tenant derivato dai metadati Kubernetes; controllo sul registro da parte del gateway | Tenant `quarantine` per i dati non attribuibili | T-14 |
| Indebolire l'isolamento di rete | Default-deny in ingress e in egress, di proprietà della baseline di piattaforma | Verifica che la CNI applichi le regole | T-03 |
| Superare il budget di risorse | ResourceQuota, LimitRange e limiti di telemetria per tenant | Budget di capacità di South nel catalogo | T-01 |
| Disattivare l'audit | Policy di audit nel repository di baseline protetto; le modifiche richiedono l'approvazione del CISO | Alert di interruzione se l'invio si ferma ([ADR 0010](adr/0010-audit-evidence-and-retention.md)) | T-09 |

## 4. Controlli di baseline

Per ogni dominio della baseline indichiamo il controllo imposto e l'evidenza o il test negativo che lo dimostra.

Sull'identità, i gruppi OIDC arrivano dall'IdP del sito, i workload usano workload identity e i token scadono; non esistono credenziali amministrative statiche valide tra siti. Sulle API, le ClusterRole sono di proprietà della piattaforma, i tenant lavorano nei propri namespace e non sono ammessi binding wildcard o admin. Le evidenze sono l'attestazione degli accessi, un tentativo di accesso con il service account di un altro team, il report delle policy e un test di admission su un'escalation vietata.

Sui workload si applica PSS `restricted`, fissato per minor version di Kubernetes, con admission in modalità enforce: niente container privilegiati, hostPath, hostNetwork, esecuzione come root o capability non sicure. Lo dimostrano i log di conformità e di rifiuto in admission. In rete vale il default-deny **sia in ingress sia in egress**, con eccezioni esplicite per DNS, registry, telemetria e database e una verifica che la CNI applichi davvero le regole; il test consiste in tentativi di traffico tra namespace e tra tier che devono essere scartati. Quote e limiti (ResourceQuota, LimitRange, numero e dimensione dei PVC, TTL, budget di capacità per team) si verificano con una richiesta oltre quota, che deve essere negata.

Per la supply chain proponiamo branch, runner ed environment protetti, scansioni iniettate nella pipeline (SAST, rilevamento dei secret, analisi delle dipendenze e dei container), attestazione dell'SBOM, firma basata su chiave e pinning per digest; il test negativo è un'immagine non firmata, che deve essere respinta. I secret passano da External Secrets Operator al secret manager del sito. Git non contiene mai valori di secret, né in chiaro né cifrati, e la secret detection di GitLab interviene al push. Le evidenze sono la scansione dei secret e un test fail-closed con il secret manager non disponibile.

Le eccezioni alle policy vivono in un namespace protetto, richiedono l'approvazione di un delegato del CISO, hanno una scadenza e sono sottoposte ad audit; il test verifica che un'eccezione scaduta venga rimossa e segnalata. Il ciclo di vita di Kubernetes segue una baseline di versioni supportate, un hardening allineato al CIS e un anello di upgrade non-prod → DR → prod, e si controlla con il report di drift e la conformità delle versioni. L'audit (fonti, policy, relay e doppio archivio immutabile) è descritto in [ADR 0010](adr/0010-audit-evidence-and-retention.md) e si verifica con la versione estesa di T-09. Lo storage usa PVC cifrati, una classe CSI specifica per sito e un piano di backup per classe di dato; la prova è il ripristino di un PVC con verifica della titolarità.

## 5. Progettazione dei secret

Proponiamo un secret manager in HA per ciascun sito attivo (Central e South), ognuno con un proprio meccanismo di unseal basato sull'HSM o sul KMS del sito: South non ha mai bisogno di Central per l'unseal. Il prodotto si sceglie in Fase 0, e lì vanno confermate anche le sue caratteristiche; la topologia e il recovery lato South fanno parte del progetto di autonomia di South descritto in [05](05-reliability-and-dr.md).

La regola di replica è che i secret di produzione siano presenti in South **entro 60 minuti** da ogni modifica, in linea con l'RPO della piattaforma. Il meccanismo preferito è la replica cross-site nativa del prodotto. Se il prodotto scelto non la offre, l'automazione di rotazione scrive ogni nuova versione su entrambi i siti (dual-write) e genera un allarme in caso di divergenza. I secret di sviluppo e test sono locali al sito e vengono ricreati insieme all'ambiente.

Ogni tenant riceve un `SecretStore` namespaced che si autentica con il service account del namespace, e la policy del secret manager lo limita a `<site>/<team>/<namespace>/*`. Un `ClusterSecretStore` esiste solo per i namespace di piattaforma, con condizioni sui namespace, e l'admission control rifiuta gli store creati dai tenant che puntano altrove.

Le credenziali di database e di servizio ruotano almeno ogni 90 giorni, oppure vengono emesse dinamicamente dove il prodotto lo consente. L'intervallo di refresh di ESO non supera 1 h e i workload ricaricano i valori quando cambiano; una rotazione che non arriva a South genera un alert.

Il bootstrap, cioè il problema del "secret zero", si risolve così. ESO si autentica con i token dei service account Kubernetes, non con token statici. Le credenziali Git di Flux (deploy token in sola lettura) e le credenziali vCenter di CAPV stanno nel secret manager, ed External Secrets le consegna sul management cluster, per esempio come Secret dietro la `VSphereClusterIdentity` di CAPV. **Nessun valore di secret passa da OpenTofu**, che crea soltanto percorsi e policy nel secret manager: il suo state quindi non contiene credenziali, e la cifratura dello state è attiva come difesa in profondità (da verificare sulla versione adottata). Le quote di unseal e di recovery sono divise tra custodi nominati dal CISO, con un gruppo di custodi raggiungibile in South.

Nessun secret sta in Git. Abbiamo scartato SOPS, Sealed Secrets e gli schemi analoghi che conservano in Git i secret cifrati, salvo un'eccezione accettata esplicitamente dal team di sicurezza; non ne proponiamo alcuna.

## 6. Supply chain: una richiesta di catalogo dall'inizio alla fine

L'utente si autentica in Backstage, dove l'RBAC associa il suo gruppo ai template di cui è owner e al relativo budget. Backstage apre una merge request nel registro del catalogo o nel repository del tenant: non ha accesso ai cluster e non può fare merge sui branch protetti.

GitLab esegue quindi la pipeline in cui le policy iniettano i controlli: schema e quota, TTL di al massimo 90 giorni per gli ambienti di test, classificazione dei dati, test delle policy-as-code, scansioni SAST, IaC, dei secret, delle dipendenze e dei container, generazione dell'SBOM e firma da parte del job di firma protetto. Le approvazioni richieste dipendono dal tier. Solo dopo l'approvazione OpenTofu, con CAPV, crea le primitive a livello di cluster; gli ambienti basati su namespace vengono invece committati nei percorsi GitOps specifici del sito.

Flux, nel cluster di destinazione, riconcilia il commit impersonando il reconciler del tenant, e l'admission control (PSS, policy, verifica delle firme, RBAC) impone la baseline indipendentemente dalla pipeline. External Secrets Operator risolve i **riferimenti** verso il secret manager del sito. Tenant di telemetria, organizzazione Grafana e owner degli SLO vengono creati a partire dal registro del catalogo ([ADR 0012](adr/0012-telemetry-tenancy-and-read-isolation.md)).

Alla scadenza, dopo un periodo di tolleranza, si apre una merge request di cancellazione soggetta ad approvazione. Data Engineering conferma la retention di ogni risorsa con stato, Flux esegue il prune e un report di dismissione elenca le risorse orfane; se ne resta qualcuna, la richiesta fallisce in modo visibile.

Ogni passo lascia la propria evidenza nell'archivio di audit: ID della merge request, pipeline, SBOM, firma, report delle policy e SHA del deployment.

## 7. Approvazioni nella governance di sicurezza

Il CISO è un'autorità di approvazione, non un quinto team di delivery; il RACI completo è in [08](08-raci-and-governance.md).

Al CISO, o a un delegato nominato, spetta l'approvazione del modello delle eccezioni alle policy e delle singole eccezioni, della policy di audit e del modello delle evidenze (modalità di lock, seconda copia), delle radici di fiducia per la firma e della custodia delle chiavi, del recovery del secret manager, delle regole di classificazione dei dati e dell'accettazione dell'isolamento in lettura della telemetria.

Network Security approva i flussi tra siti, i percorsi DNS, la topologia di PKI e IdP e il fencing in caso di disastro. Data Engineering approva l'isolamento dei tenant sui database SQL e NoSQL, l'RPO dei backup dei database e la verifica dei restore, i servizi di storage e di broker. SRE approva SLO, budget degli alert, soak in staging e runbook operativi.
