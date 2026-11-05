# ADR 0010: evidenze di audit (sorgenti, consegna, retention immutabile e recupero)

- Stato: proposta, che richiede una decisione del CISO sulla modalità di lock e sulla seconda copia
- Data: 2026-11-05
- Decisori: CISO, responsabile del modello di evidenza
- Realizzazione: SRE (pipeline), Data Engineering (servizio di storage), Network Security (flussi)
- Revisori: Platform Engineering, consultato
- Documenti correlati: [baseline di sicurezza](../04-security-and-tenancy.md), [ADR 0008](0008-retention-tiering.md), [approfondimento sull'osservabilità, §2 e §8](../03-observability-deep-dive.md)

## Contesto

Il CISO pone due requisiti (REQ-03 e REQ-04 in [01](../01-scope-and-assumptions.md)): conservare per **almeno dodici mesi** i record di audit della piattaforma e di Kubernetes, e dare al team di sicurezza la prova che i controlli siano applicati davvero, non soltanto dichiarati. Non prescrive né una tecnologia né una modalità di immutabilità.

Un'evidenza di audit serve solo se è completa, se rende rilevabile ogni manomissione, se è conservata e se si può recuperare. I log operativi in Loki, da soli, non hanno nessuna di queste proprietà: gli amministratori possono modificarli, la loro retention è di 30 giorni e condividono i domini di guasto con LGTM.

## Requisiti derivati per questo progetto

Da queste proprietà ricaviamo sei requisiti misurabili, a cui il resto dell'ADR fa riferimento.

La completezza (R1) vuol dire che ogni evento di una sorgente raggiunge l'archivio oppure genera un alert di gap; in regime il ritardo dell'archivio resta entro 5 min, e sorgente e relay hanno uno spool di almeno 72 h. L'integrità (R2) vuol dire che una manomissione è rilevabile: gli oggetti hanno un hash, i manifest sono concatenati con hash e firmati, e un verificatore indipendente gira ogni giorno. La retention (R3) è di almeno 365 giorni assicurati, con una policy di 400, e nessuno può accorciarla, nemmeno gli amministratori dello storage.

La sopravvivenza (R4) chiede che l'evidenza resista alla perdita di un qualsiasi sito. Il recupero (R5) chiede che qualunque evento degli ultimi 400 giorni si possa cercare entro 4 h. La separazione dei compiti (R6) vuol dire che chi scrive non può cancellare, che gli amministratori della piattaforma non possono cambiare la retention e che la retention è amministrata da una persona designata dal CISO, esterna ai gruppi di amministrazione della piattaforma.

## Sorgenti e policy

Per Kubernetes, su tutti i cluster e quindi anche sui cluster legacy una volta integrati, usiamo il backend *log* di kube-apiserver su disco locale, con una rotazione dimensionata per almeno 72 h; uno shipper di proprietà della piattaforma, sui nodi di control plane, legge i file. Sui cluster legacy questo richiede modifiche ai flag dell'API server approvate dall'owner del cluster, ed è un'attività della roadmap.

GitLab usa l'audit event streaming a livello di istanza (GitLab Ultimate, self-managed) verso l'endpoint HTTP del relay del sito, autenticato con il token di verifica dello stream. Poiché la consegna può ripetersi, il relay deduplica sull'`id` dell'evento. Dopo una promozione di Geo la destinazione dello stream deve risolvere sul relay di South; è un passo del runbook in [05](../05-reliability-and-dr.md).

Il secret manager manda al relay un audit device o un log stream, con modalità che dipendono dal prodotto. Flux, Kyverno, Backstage e le pipeline OpenTofu producono eventi strutturati: decisioni di admission, policy report, eventi di riconciliazione, richieste dal catalogo, record di plan e apply. Il log di eventi e task di vCenter viene inoltrato al relay, mentre le azioni dei controller CAPV/CAPI arrivano come eventi e log Kubernetes del management cluster; il meccanismo di inoltro di vCenter dipende dal prodotto ed è da verificare. Lo stesso vale per l'identity provider, che inoltra al relay le modifiche amministrative e gli eventi di autenticazione.

Grafana e il query gateway seguono un percorso diverso. Le modifiche di configurazione si fanno solo via Git, quindi le copre l'audit di GitLab. Grafana OSS non ha un audit log nativo, e l'accesso ai dati è coperto dall'access log del query gateway (utente, tenant, hash della query), che va al relay oltre che al tenant `security` di 30 giorni. Per firewall e rete, Network Security esporta i change record e l'audit log del sistema di gestione dei firewall; anche qui la fattibilità dipende dal prodotto ed è da verificare.

La policy di audit di Kubernetes che proponiamo è approvata dal CISO e versionata nel repository protetto della baseline. Assegna i livelli in questo modo:

- `RequestResponse` per oggetti RBAC, configurazione di admission e dei webhook, policy ed eccezioni alle policy, CRD;
- `Request` per create, update e delete dei workload nei namespace dei tenant;
- `Metadata` per **Secret, ConfigMap e token review**, così i valori non entrano mai nel log, e per tutto ciò che non è elencato altrove;
- `None` per gli endpoint di health e per le letture ad alto volume (`get/list/watch`) dei controller di sistema su lease ed eventi.

Il volume di audit di ~20 GiB/giorno indicato in [06](../06-nfr-and-capacity.md) è una stima, da rimisurare nel pilota con questa policy. Ogni modifica alla policy è a sua volta soggetta ad audit e richiede l'approvazione del CISO tramite una regola di approvazione delle merge request.

## Opzioni considerate

| # | Opzione | Valutazione |
|---|---|---|
| A | Tenere l'audit in Loki con retention di un anno | Scartata: modificabile dagli amministratori, stesso dominio di guasto di LGTM, nessuna evidenza di integrità |
| B | Archivio in North, Object Lock in *governance mode*, copia singola | Debole: chi ha il permesso di bypass può cancellare prima della scadenza |
| C | Archivio in North, Object Lock in *compliance mode*, copia singola | Solida contro la cancellazione logica, ma se si perde North si perde l'evidenza, a meno che il CISO non accetti formalmente quel rischio |
| D | Archivio in North più una seconda copia indipendente in South, entrambi in compliance mode e con amministrazione separata | Soddisfa R1–R6, compresa la perdita di un qualsiasi sito. Aggiunge ~4,1 TiB logici in South e un flusso cross-site |
| E | Inoltro a un SIEM aziendale | Solo complementare. I requisiti non nominano un SIEM e quello del cliente non è noto; si può aggiungere come terzo consumatore senza cambiare questo disegno |

## Decisione

Proponiamo al CISO l'opzione D. L'opzione C è il ripiego documentato se il CISO accetta il rischio di un archivio su un solo sito.

### 1. Pipeline

Gli shipper inviano gli eventi, con acknowledgement, a un relay di audit del sito. Il relay gira su un node pool dedicato e con taint nel management cluster del sito, con almeno 3 repliche e spool persistente. Non sta nel cluster di osservabilità per scelta: così un'indisponibilità di LGTM non può fermare la consegna dell'audit.

Per ogni batch il relay scrive un oggetto compresso, ne calcola lo SHA-256 e lo aggiunge a un manifest concatenato con hash, firmato con una chiave custodita nell'HSM o nel KMS del sito. Le destinazioni sono tre: l'archivio di North (flusso F-04); la copia di South, locale per il relay di South e raggiunta con il flusso F-11 dal relay di Central; una copia ricercabile di 30 giorni nel tenant `security` di Loki.

### 2. Storage

Entrambi gli archivi sono bucket S3-compatibili con versioning, **Object Lock in compliance mode** e retention predefinita di 400 giorni. Le credenziali del relay consentono solo `PutObject`. Gli archivi di North e di South hanno credenziali amministrative diverse, e nessuna delle due è in mano agli amministratori della piattaforma. In caso di incidente il ruolo designato dal CISO può applicare il legal hold.

Il prodotto deve offrire la stessa semantica di riferimento di S3 Object Lock: in compliance mode nessuno, nemmeno root, può cancellare o accorciare la retention; la governance mode si può aggirare con un permesso speciale; una DELETE su un bucket con versioning aggiunge solo un delete marker. L'equivalenza va verificata sul prodotto on-prem scelto dal cliente. Se il prodotto non la offre, il progetto ripiega su un'appliance WORM con garanzie equivalenti.

### 3. Verifica di integrità

Ogni sito che ospita un archivio esegue ogni giorno un verificatore indipendente: quello di North per l'archivio di North, un'istanza in South per la copia di South. Entrambi girano fuori dal dominio degli amministratori della piattaforma. Il verificatore ricalcola gli hash, controlla la catena dei manifest e la continuità delle sequenze per sorgente, riporta sulla dashboard del CISO e chiama il reperibile in caso di discrepanza.

### 4. Recupero

Gli eventi più vecchi di 30 giorni si recuperano con una richiesta che è essa stessa soggetta ad audit. Gli oggetti archiviati per l'intervallo richiesto vengono caricati in un tenant Loki temporaneo in sola lettura (`audit-restore`), interrogabile solo dagli auditor di sicurezza. L'obiettivo è di 4 h al massimo tra la richiesta e la possibilità di interrogare i dati. Non costruiamo un secondo cluster di ricerca permanente.

### 5. Gestione dei gap

Gli alert scattano sul ritardo degli shipper, su uno spool oltre il 50%, su un ritardo di acknowledgement del relay oltre 5 min, su un manifest mancante e su un buco nella sequenza. Sono alert di sicurezza: chiamano il reperibile SRE, notificano Network Security e informano il delegato del CISO. Non si crea un nuovo turno di reperibilità, e lo stato degli SLO non li sopprime mai.

## Conseguenze

Il costo principale sono due archivi, ciascuno di ~4,1 TiB logici con le assunzioni del modello, da moltiplicare per il fattore di protezione dello storage. A questi si aggiungono un flusso cross-site in più (F-11), un servizio di relay per sito e chiavi di firma custodite in HSM o KMS in ogni sito.

In cambio l'evidenza sopravvive alla perdita di qualsiasi sito. Se si perde Central restano le copie di North e di South, e il relay di South continua a funzionare. Se si perde North resta la copia di South, e gli spool trattengono i nuovi eventi finché North non torna. Se si perde South resta la copia di North, e il relay di Central mette in spool il flusso F-11.

Restano tre rischi. Un amministratore di un cluster compromesso può *fermare* l'invio; questo genera un alert di gap ma non permette di riscrivere l'evidenza già archiviata. La distruzione fisica di entrambi i sistemi di storage è fuori perimetro. La manipolazione degli orologi è mitigata dai numeri di sequenza e dal monitoraggio NTP di sito.

Sul piano della governance, l'amministratore della retention è una persona designata dal CISO, non un quinto team, e il RACI lo registra come autorità di approvazione.

## Validazione

Il test T-09 viene esteso: si tenta di cancellare o sovrascrivere un oggetto archiviato come writer del relay, come amministratore dello storage e come root. Ogni tentativo deve essere rifiutato, e la prova produce una trascrizione firmata.

Le altre prove, con la relativa condizione di superamento, sono queste:

- si ferma il relay per 24 h, e dopo il ripristino non manca nessun evento;
- si rimuove un oggetto, e il verificatore lo rileva entro un ciclo;
- si recupera un evento di circa 11 mesi, che diventa interrogabile entro 4 h;
- si promuove GitLab Geo, e lo stream di audit raggiunge il relay di South.

Il superamento di ogni prova è constatato alla presenza del CISO.

## Trigger di revisione

- Il CISO sceglie l'opzione C.
- L'object store on-prem selezionato non offre la semantica della compliance mode.
- Un SIEM diventa obbligatorio.
- Il volume di audit misurato si discosta dalla stima di oltre ±30%.
- Si stabilisce un obbligo legale o regolatorio di retention oltre un anno (RAID Q-11).
