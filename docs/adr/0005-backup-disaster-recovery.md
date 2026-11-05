# ADR 0005: backup e disaster recovery, con protezione per classe di dato, percorso critico e fencing

- Stato: proposta. Finché i drill sull'intero inventario non vengono superati, è un progetto condizionato e non uno SLA.
- Data: 2026-11-05
- Decisori: SRE
- Revisori: Data Engineering, che approva per i servizi stateful; CIO, che approva perimetro ed eccezioni; consultati Platform Engineering e Network Security
- Documenti correlati: [disegno del DR](../05-reliability-and-dr.md), [ADR 0002](0002-multi-site-topology.md), [ADR 0007](0007-source-control-and-recovery.md), [ADR 0010](0010-audit-evidence-and-retention.md), [ADR 0011](0011-south-recovery-dependencies.md)

## Contesto

Se si perde Central, il control plane della piattaforma e la produzione devono essere recuperabili con **RPO di 1 h e RTO di 4 h**. Gli ambienti self-service di South si ricreano dal codice e non hanno RPO. North è il sito di backup off-site; i collegamenti hanno un RTT di 10–20 ms e una banda ancora sconosciuta.

Tre vincoli danno forma al progetto. La replica non protegge da corruzione, ransomware o cancellazioni per errore, perché anche questi si replicano. Un ripristino da backup è limitato dalla banda: un TiB a 1 Gbps con un'efficienza del 70% richiede circa 3,5 h, a 100 Mbps circa 35 h. Uno snapshot etcd, infine, ricostruisce lo *stesso* cluster e non è un mezzo per spostare i carichi su un cluster diverso in South.

## Opzioni considerate

La ricostruzione a freddo in South a partire dai backup di North (opzione 1) ha un costo di standby basso, ma ricostruire i cluster e poi ripristinare i dati non sta in 4 h: la scartiamo per la produzione.

Le scritture sincrone tra siti, con database estesi (opzione 2), legano latenza e disponibilità di Central a South e richiedono un quorum su due siti più un arbitro. Le escludiamo come default e le ammettiamo per singola applicazione solo se il suo owner ne dimostra il funzionamento.

L'opzione 3 combina cluster caldi in South, replica asincrona continua per classe di dato, backup immutabili in North e un failover dichiarato da una persona e protetto da fencing. È quella che scegliamo: il costo dello standby è compensato dal fatto che i ripristini restano fuori dal percorso critico.

## Decisione

Adottiamo l'opzione 3, con le cinque regole che seguono.

1. Per la produzione in perimetro nessun ripristino sta sul percorso critico. Ogni dataset di produzione in perimetro ha una copia replicata in continuo in South, con replica nativa del database oppure a livello di storage. Il ritardo di replica genera un alert a 15 min; il limite di progetto è 60 min. I backup in North coprono corruzione e ransomware e fanno da ripiego, ma non sono il percorso primario di DR. Un dataset recuperabile solo da backup va riprogettato, oppure coperto da un'eccezione firmata dal CIO che ne riporta l'RTO reale.

2. La protezione segue la classe di dato; la matrice completa è in [05](../05-reliability-and-dr.md) §3.

   | Classe di dato | Meccanismo | RPO |
   |---|---|---|
   | SQL/NoSQL di produzione | Replica asincrona nativa verso South più backup point-in-time verso North | ≤60 min |
   | Dati PVC di produzione | Replica di storage o applicativa; backup Velero con CSI data mover su object storage, come candidato per le copie in North | ≤60 min |
   | Oggetti runtime Kubernetes non presenti in Git | Backup ogni ≤30 min; i manifest sono al 100% in Git | ≤30 min |
   | Artifact rilasciati e stato desiderato | Copiati nel registry di South come parte del rilascio | 0 |
   | Git e CI | GitLab Geo più backup giornalieri verso North | ≤60 min |
   | State OpenTofu | Versionato, replicato in South | ≤60 min |
   | Secret | Manager per sito | ≤60 min |
   | Audit | Doppio archivio immutabile | Ritardo ≤5 min |
   | Metriche di capacità | Copia giornaliera | ≤24 h |
   | Telemetria operativa | Non replicata: South riparte da zero | Non applicabile |
   | Dev/test | Ricreati dal codice | Nessun RPO |

   Gli snapshot etcd di ogni cluster vanno in North e servono solo per ricostruire il cluster sul posto.

3. Rientra nel perimetro tutta la produzione sui cluster di Central gestiti dalla piattaforma. I carichi ancora sui cluster creati a mano restano **fuori perimetro finché non vengono migrati**: ognuno è elencato con la sua reale capacità di recupero e accettato dal CIO, senza esclusioni implicite. Una suddivisione in livelli, con un RTO più lungo per la produzione non critica, viene offerta come proposta di revisione dell'obiettivo e non è data per acquisita.

4. Il failover è dichiarato da una persona, l'incident commander SRE, su delega del CIO. I criteri sono osservati da South e confermati da un secondo punto di osservazione. Il fatto che un sito sia irraggiungibile non viene mai preso come prova che il fencing sia avvenuto: Network Security applica la policy di quarantena di Central già predisposta, e i vecchi primari vengono declassati o ricostruiti al loro ritorno. Una probe di raggiungibilità da North è solo un input *consultivo*, così North non diventa una nuova dipendenza.

5. Un runbook puramente sequenziale richiederebbe 15 + 20 + 40 + 90 + 50 + 25 = **240 min, senza alcun margine**. Il percorso parallelo progettato è di 175 min (modellati). Comincia con rilevamento, dichiarazione e fencing; prosegue con la promozione dei dati in parallelo alla verifica dei servizi abilitanti, alla promozione di Geo e allo scale-out dei worker; si chiude con attivazione, validazione, switch del traffico e sign-off. Restano 65 min di margine (27%) rispetto ai 240 e l'obiettivo interno di ≤180 min è rispettato. Le sensibilità sono analizzate in [05](../05-reliability-and-dr.md) §7.

## Conseguenze

Le voci di costo dominanti del DR sono la capacità riservata in South, i collegamenti di replica continua e le istanze in South dei servizi abilitanti ([ADR 0011](0011-south-recovery-dependencies.md)).

Data Engineering deve fornire un pattern di replica per ogni prodotto database usato in produzione. Un prodotto che non sa replicare in modo asincrono tra siti è un elemento bloccante per la Fase 0 (RAID R-24).

L'RPO si misura per dataset, come intervallo tra l'ultima transazione durevole in Central e l'ultima transazione replicata in South, non come esito positivo dei job di backup. Anche le evidenze hanno un limite: due drill sono la prova funzionale di due esiti, e per parlare di percentili servono misure ripetute per singolo passo, come previsto nella validazione.

## Validazione

| Test | Cosa dimostra | Cadenza |
|---|---|---|
| T-11, drill di perdita di Central sull'intero inventario | Ogni applicazione in perimetro recuperata in ≤240 min, con timestamp per passo e RPO misurato per dataset | Prima dell'impegno sulla produzione, poi ogni anno |
| Drill su una coorte rappresentativa | Lo stesso, su un sottoinsieme | Game day trimestrale |
| Misura dei tempi per passo (promozione del database, prova della promozione Geo, prova a secco dell'attivazione DR, switch DNS) | Costruisce una distribuzione per passo. Si riportano mediana e massimo; i percentili si citano solo dopo ≥20 campioni per passo | Mensile |
| T-18, test di autonomia di South | Nessuna dipendenza da Central | Trimestrale |
| T-19, partizione senza perdite | Nessun failover e nessun doppio scrittore quando Central è isolato ma attivo | Due volte l'anno |

## Trigger di revisione

- La banda misurata o il ritardo di replica rendono irraggiungibile un RPO ≤60 min per un dataset.
- Il massimo misurato di un passo supera il budget assegnato.
- Il CIO accetta la suddivisione in livelli.
- L'inventario dei carichi cambia il perimetro.
