# ADR 0003: tenancy per livelli di rischio, confine di privilegio GitOps, admission e fiducia nella supply chain

- Stato: proposta
- Data: 2026-11-05
- Decisori: Platform Engineering
- Revisori: CISO, che approva il modello delle eccezioni alle policy e le radici di fiducia; consultati Network Security, SRE e Data Engineering
- Documenti correlati: [baseline di sicurezza](../04-security-and-tenancy.md), [ADR 0010](0010-audit-evidence-and-retention.md), [ADR 0012](0012-telemetry-tenancy-and-read-isolation.md)

## Contesto

I team di business hanno bisogno di un self-service basato sui namespace. Il CISO chiede ambienti conformi per impostazione predefinita ed evidenze che i controlli siano applicati, e chiede anche che i team **non possano indebolire** la postura di sicurezza.

Il golden path esistente in South combina già RBAC sui namespace, quote, network policy default-deny, Pod Security Standards, un motore di policy, secret esterni e GitLab CI con scansioni, SBOM e firma.

La produzione ospita carichi critici per il business e potenzialmente sensibili. Tutti i componenti devono girare on-prem, quindi i servizi pubblici di firma e di trasparenza non sono utilizzabili. In una piattaforma self-service i percorsi realistici di escalation dei privilegi sono il reconciler GitOps, che per default gira come cluster-admin, la pipeline CI, che un tenant potrebbe modificare, le eccezioni alle policy e la fiducia nelle immagini. Per questo l'admission control da solo non basta.

## Opzioni considerate

Le opzioni riguardano tre questioni distinte, ognuna con la propria numerazione.

Sulla tenancy, l'opzione 1 (tenancy a namespace in tutti i livelli) costa meno, ma non offre un confine di raggio d'impatto sufficiente per le applicazioni di produzione più rischiose. L'opzione 2 (un cluster per team) separa bene, con un overhead di flotta molto alto. L'opzione 3 usa namespace per dev/test sui cluster condivisi di South e colloca i carichi di produzione su cluster dedicati o condivisi in base alla classificazione del rischio, sempre con namespace al loro interno.

Sul privilegio GitOps abbiamo scartato l'opzione a, un unico reconciler Flux privilegiato che si affida solo alla protezione dei repository: qualunque scrittura su un percorso riconciliato diventerebbe cluster-admin. L'opzione b combina il lockdown multi-tenancy di Flux con impersonation, la separazione dei repository, policy GitLab Ultimate non aggirabili e l'admission applicata anche al reconciler. L'opzione c, gli AppProject di Argo CD, è un pattern valido e viene valutata insieme alla scelta dello strumento GitOps in [ADR 0001](0001-platform-toolchain.md).

Per la radice di fiducia della firma, che deve restare on-prem, le opzioni sono quattro:

- i. firma keyless con Sigstore pubblico, scartata perché dipende dai servizi pubblici Fulcio e Rekor;
- ii. firma keyless self-hosted (Fulcio, Rekor e OIDC per sito), la più flessibile, che però aggiunge tre servizi per sito e una dipendenza da OIDC durante il DR;
- iii. cosign con chiavi non esportabili in un HSM o KMS per sito e un transparency log Rekor self-hosted per sito;
- iv. Notation con certificati x509 della PKI del cliente e una timestamp authority, senza transparency log, come ripiego.

## Decisione

### 1. Tenancy

Adottiamo l'opzione 3: la collocazione sui cluster segue la classificazione del rischio, non l'anzianità del team.

Per dev/test il template riprende nella sostanza il golden path esistente: RBAC del namespace legato ai gruppi OIDC; default-deny sia in ingresso sia in uscita, con aperture esplicite per DNS, registry, telemetria e database; PSS `restricted` fissato alla minor version Kubernetes del cluster; policy Kyverno in modalità enforce; quote e LimitRange; verifica delle immagini firmate; External Secrets; un TTL con teardown controllato.

La produzione **non** usa il golden path così com'è. Vi aggiunge le approvazioni sugli environment protetti di GitLab, la classificazione dei dati, l'iscrizione a un tier di DR, un ambito di secret indipendente, la revisione di rete, le finestre di change e le evidenze di rollback. La differenza completa è descritta in [04](../04-security-and-tenancy.md).

### 2. Confine di privilegio GitOps (opzione b)

I controller Flux girano con `--no-cross-namespace-refs=true`, `--no-remote-bases=true` e `--default-service-account` puntato su un service account **senza alcun permesso**. Le Kustomization e le HelmRelease dei tenant vengono create dal reconciler di piattaforma nel namespace del tenant e impersonano un service account di reconciler del tenant, legato a una Role di namespace senza verbi a livello di cluster. Solo la Kustomization di piattaforma `flux-system` ha diritti sull'intero cluster.

I repository sono separati per responsabilità. Il repository della baseline di piattaforma contiene policy, RBAC, baseline di rete, configurazione dell'admission e collector; lo mantiene Platform Engineering e il file CODEOWNERS include un delegato del CISO per le directory delle policy. Ogni team ha un proprio repository di configurazione del tenant, che contiene soltanto manifest con ambito di namespace. Il registro del catalogo, con la mappatura tra namespace e tenant e le quote, è scritto dal bot di Backstage tramite merge request e approvato da Platform Engineering.

I controlli di GitLab Ultimate sono imposti da un progetto di security policy protetto:

- le pipeline execution policy iniettano in ogni progetto in perimetro i job di validazione obbligatori (schema, policy, quote, scansioni di sicurezza), che i tenant non possono togliere modificando `.gitlab-ci.yml`;
- le merge request approval policy richiedono l'approvazione della sicurezza quando cambiano i percorsi delle policy o le scansioni trovano violazioni;
- le scan execution policy impongono SAST, secret detection, scansione delle dipendenze e dei container;
- le etichette dei compliance framework limitano l'ambito di queste policy ai progetti di infrastruttura e dei tenant.

Una merge request di dev/test può andare in auto-merge solo se tocca percorsi del tenant, supera la pipeline iniettata e resta entro le quote; la produzione usa environment protetti con approvazione umana. Il bot di Backstage ha un token con ambito di progetto che può soltanto creare branch e merge request: non può fare merge sui branch protetti né amministrare, è conservato nel secret manager e viene ruotato.

Le policy di admission si applicano anche ai service account dei reconciler dei tenant, quindi un manifest non conforme viene rifiutato anche dopo il merge.

### 3. Admission ed eccezioni

L'admission controller gira con almeno 3 repliche, un PodDisruptionBudget e anti-affinity. In produzione i webhook sono fail closed. Le esclusioni si limitano al namespace del motore di policy e a `kube-system`, così i pod di sistema possono sempre ripartire, mentre i carichi dei tenant restano bloccati finché il webhook è giù.

Le eccezioni alle policy sono ammesse solo in un unico namespace protetto (Kyverno consente di limitarle a un solo namespace). Quel namespace è scritto soltanto dal reconciler di piattaforma, a partire da una directory le cui merge request richiedono l'approvazione del delegato del CISO. Ogni eccezione porta ambito, owner, giustificazione e scadenza; una cleanup policy rimuove quelle scadute e il report di conformità le segnala.

Il break-glass usa credenziali di emergenza sigillate sotto doppio controllo (Platform Engineering e delegato del CISO), valide al massimo 4 h. Il loro uso fa scattare un paging di sicurezza ed è seguito da una revisione obbligatoria entro due giorni lavorativi. Il break-glass crea un'eccezione di emergenza con ambito ristretto e **non** disattiva il webhook su tutta la flotta.

Kyverno sta passando da `ClusterPolicy` e dalla PolicyException `kyverno.io` (deprecate nella v1.19, rimozione prevista nella v1.20) ai tipi `policies.kyverno.io` basati su CEL (`ValidatingPolicy`, `ImageValidatingPolicy`). Le nuove policy usano i tipi CEL; l'API esatta dipende dalla versione fissata e va verificata nel pilota.

### 4. Fiducia nella supply chain (opzione iii, con l'opzione iv come ripiego)

Le immagini si costruiscono una sola volta. La firma avviene in un job protetto, su runner protetti, con una chiave che non lascia mai l'HSM o il KMS del sito; Central e South hanno ciascuno la propria chiave. SBOM e risultati delle scansioni sono allegati come attestazioni e conservati nel registry accanto all'immagine. Ogni evento di firma è registrato nel Rekor self-hosted del sito e nell'archivio di audit ([ADR 0010](0010-audit-evidence-and-retention.md)).

In admission la firma viene verificata contro **entrambe le chiavi pubbliche dei siti**. L'inclusione nel transparency log si controlla sul bundle che accompagna la firma, con le chiavi pubbliche dei Rekor di sito, quindi la verifica non ha bisogno di raggiungere Central. Le immagini devono provenire da registry approvati ed essere referenziate per digest. I nomi esatti dei campi e il comportamento del bundle offline vanno verificati nel pilota con le versioni fissate di cosign e Kyverno. Kyverno documenta il salto del transparency log come impostazione da usare solo nei test, e il progetto non vi fa affidamento.

Durante il DR la CI di South, collegata al nodo Geo promosso, firma con la chiave di South, e una firma di hotfix d'emergenza richiede due approvatori. Le chiavi ruotano ogni anno; per revocarne una si toglie la chiave pubblica dalla policy attraverso il repository protetto della baseline.

## Conseguenze

Con questo disegno un tenant non può ottenere diritti a livello di cluster tramite GitOps, non può togliere i controlli CI obbligatori, non può approvarsi da solo un'eccezione e non può fare deploy di immagini non firmate. Ciascuna di queste proprietà poggia su un controllo *e* su un test negativo.

Il costo è fatto di più oggetti per tenant (service account, Role, Kustomization, organizzazione Grafana), di un Rekor self-hosted e di capacità HSM o KMS in ogni sito, e dei progetti di policy GitLab: sulle istanze self-managed hanno un limite predefinito di 5 policy per tipo, quindi le policy vanno consolidate.

Restano due rischi operativi. Un'interruzione del webhook fail closed blocca i deploy dei tenant; la mitigano l'HA e le esclusioni ristrette. La transizione delle API di Kyverno deve avvenire dentro l'anello di aggiornamento della piattaforma.

## Validazione (test negativi, a estensione di T-02, T-04 e T-05)

| # | Tentativo | Risultato atteso |
|---|---|---|
| 1 | Una merge request del tenant aggiunge una ClusterRoleBinding, una PolicyException, un `sourceRef` verso un altro namespace, oppure modifica `.gitlab-ci.yml` per togliere la validazione | Bloccata dalla pipeline iniettata; se forzata in merge, rifiutata dall'RBAC di impersonation e dall'admission |
| 2 | Deploy di pod privilegiati, con hostPath o hostNetwork, con un token di service account non sicuro, con egress verso un indirizzo non consentito o senza le etichette richieste | Negato; ogni diniego arriva all'archivio di audit |
| 3 | Deploy di un'immagine non firmata, o sostituzione di un tag dopo la firma | Rifiutato |
| 4 | Con South isolato, deploy di un'immagine firmata da South e di una non firmata | Immagine firmata accettata; immagine non firmata rifiutata |
| 5 | Webhook giù | I pod di sistema partono; i pod dei tenant sono rifiutati |
| 6 | Eccezione di emergenza | Scade automaticamente |

## Trigger di revisione

La decisione va riaperta se il cliente impone un motore di admission diverso, se il Rekor self-hosted non viene approvato (nel qual caso si passa all'opzione iv), se i limiti delle policy GitLab bloccano il disegno o se i tipi CEL di Kyverno cambiano il modello delle eccezioni.
