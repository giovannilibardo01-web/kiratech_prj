# ADR 0012: tenancy della telemetria e isolamento del percorso di lettura

- Stato: proposta, in attesa della revisione di CISO e SRE
- Data: 2026-11-05
- Decisori: SRE, responsabile della decisione
- Revisori: CISO, che approva; Platform Engineering e Network Security, consultati
- Documenti correlati: [ADR 0004](0004-observability-topology.md), [ADR 0009](0009-commercial-support.md), [approfondimento sull'osservabilità, §2–§4](../03-observability-deep-dive.md)

## Contesto

Il CISO chiede che i team non possano indebolire la postura di sicurezza e che i controlli lascino evidenza. Per la telemetria ne discendono due vincoli. Sul percorso di scrittura, un workload non deve poter depositare dati nel tenant di un altro team. Sul percorso di lettura, un utente non deve poter leggere metriche, log o trace di un altro team.

Grafana Mimir, Loki e Tempo ricavano il tenant dall'header `X-Scope-OrgID` e si aspettano un proxy di autenticazione davanti a sé: da soli non autenticano gli utenti.

Abbiamo controllato il comportamento dei prodotti sulla documentazione corrente il 2026-11-05; va ricontrollato sulla versione adottata. In Grafana OSS qualsiasi utente di un'organizzazione può interrogare qualsiasi data source di quella organizzazione, perché i permessi sulle data source sono una funzione Enterprise/Cloud. La funzione *LBAC for data sources* di Grafana Enterprise copre le metriche (Mimir tramite GEM) e i log (Loki tramite GEL); per le trace è disponibile solo con Grafana Cloud Traces, **non con Tempo self-hosted**. Le data source Prometheus, Loki e Tempo di Grafana supportano *Forward OAuth Identity*.

Imporre la tenancy in scrittura quindi non basta. Se Grafana interroga direttamente i backend, qualunque utente di un'organizzazione legge tutti i tenant che stanno dietro alle sue data source. Il percorso di lettura ha bisogno di un disegno proprio.

## Opzioni considerate

| # | Opzione | Punti di forza | Punti deboli |
|---|---|---|---|
| A | Grafana OSS con un'organizzazione per team e un query gateway di sito che valida il token OIDC inoltrato e imposta l'header del tenant | Stesso controllo per metriche, log e trace; nessun abbonamento; registro dei tenant condiviso con il percorso di scrittura; endpoint dei backend raggiungibili solo tramite il gateway | Il gateway va costruito o assemblato ed esercitato (costo di persone nel TCO); un'organizzazione per team aumenta gli oggetti di provisioning; i dashboard trasversali ai team vivono solo nell'organizzazione `platform` |
| B | Grafana Enterprise con GEM/GEL, permessi sulle data source e LBAC | Supporto del vendor, isolamento a livello di label dentro una sola organizzazione per metriche e log | Costo dell'abbonamento; non copre Tempo self-hosted, quindi per le trace servono comunque un gateway o la separazione per organizzazione; le data source LBAC non si possono gestire come codice (le regole sì) |
| C | Un'unica organizzazione, affidandosi a ruoli e cartelle di Grafana | La più semplice | Scartata: qualsiasi Viewer può eseguire qualsiasi query su qualsiasi data source dell'organizzazione |
| D | Un'istanza Grafana per team | Separazione forte | Scartata: N deployment e N database Grafana per sito, con un costo operativo sproporzionato |

Le abbiamo confrontate su sette criteri: l'isolamento di tutti e tre i segnali, le evidenze per il CISO, l'esercizio solo on-prem, il costo operativo per SRE, il costo di licenza, il provisioning as code e il comportamento in caso di guasto, con l'alerting che deve restare indipendente dal percorso di query.

## Decisione

Scegliamo l'opzione A. L'opzione B resta un'alternativa già valutata, con trigger di revisione espliciti.

1. I tenant sono quelli definiti nell'approfondimento sull'osservabilità, §3: `t-<team>`, `platform`, `capacity`, `security` e `quarantine`, identici in Central e in South.
2. Sul percorso di scrittura, l'identità del tenant si ricava dai metadati Kubernetes risolti da collector di proprietà della piattaforma: service discovery per le metriche, API Kubernetes per i log, associazione per IP di connessione di `k8sattributes` per le trace. Si mappa poi attraverso il registro `{site, cluster, namespace} → tenant`, protetto in integrità. Il telemetry gateway accetta una coppia `(cluster certificate, tenant)` solo se il registro la elenca, e tutto ciò che non è attribuibile finisce in `quarantine`.
3. Sul percorso di lettura, le data source di Grafana puntano al query gateway del sito con *Forward OAuth Identity*. Il gateway valida il token, mappa i gruppi dell'IdP sui tenant consentiti e imposta da sé `X-Scope-OrgID`, con liste federate `a|b` solo per i ruoli SRE e platform. Applica anche i limiti di query e registra ogni query nel tenant `security`. Gli endpoint di query dei backend accettano traffico solo dal gateway e dai ruler interni.
4. Organizzazioni, data source e dashboard sono gestiti da Git, e il ruolo Org Admin è riservato al service account di provisioning.
5. Le regole di alerting girano nei ruler dei backend, tenant per tenant, quindi il paging non dipende dal gateway, da Grafana o dall'IdP.

## Conseguenze

Dal punto di vista della sicurezza, scrittura e lettura condividono lo stesso punto di enforcement e lo stesso registro, Tempo è coperto senza contare su una funzione Enterprise che non lo supporta e ogni query è attribuibile a un utente. Resta un rischio: un collector della piattaforma compromesso può instradare in modo errato i dati tra i tenant del proprio cluster. Lo mitigano le immagini firmate, la protezione in admission e il riallineamento automatico del drift.

Il prezzo operativo è un componente HA in più per sito, il query gateway, in carico a SRE. L'onboarding di un team crea un tenant, una voce nel registro, i limiti e un'organizzazione Grafana; è automatizzato tramite il catalogo e rientra nell'obiettivo di onboarding di ≤1 giorno lavorativo.

Non c'è abbonamento, ma l'effort di costruzione e manutenzione del gateway deve comparire sul lato OSS del TCO (vedi [10](../10-cost-and-tco.md)). È il fattore principale che può ribaltare il confronto tra OSS e supportato.

Ci sono infine due dipendenze. L'IdP locale del sito deve validare i token senza Central, e le viste di flotta cross-site richiedono che il gateway remoto si fidi dell'issuer dell'altro sito. Entrambe sono trattate in [ADR 0011](0011-south-recovery-dependencies.md): ogni sito ha il proprio IdP e le chiavi di firma sono sincronizzate insieme ai dati di identità (F-15).

## Validazione

Nel pilota, su dati sintetici, il test T-14 viene esteso a tre casi: un header di tenant falsificato; un attributo OTLP `k8s.namespace.name` e campi dei log falsificati; query cross-tenant attraverso l'API di Grafana, attraverso il gateway e direttamente sugli endpoint dei backend. Il test passa se non compare alcun risultato cross-tenant e ogni rifiuto lascia un log attribuibile.

Una seconda prova simula il guasto del gateway: i dashboard diventano indisponibili mentre il paging continua. Il CISO accetta la soluzione sulla base delle evidenze del pilota, prima che venga integrata la telemetria di produzione.

## Trigger di revisione

- L'isolamento in lettura a livello di label, sotto il tenant, diventa un requisito.
- Oltre ~40 organizzazioni di team, il provisioning per organizzazione diventa ingestibile.
- L'effort del gateway supera il valore di break-even dell'abbonamento nel TCO.
- Grafana Enterprise introduce un LBAC supportato per Tempo self-hosted.
- Le organizzazioni cambiano in modo sostanziale nella major version di Grafana adottata.

In ciascun caso si registra un ADR sostitutivo.
