# Disponibilità, backup e disaster recovery

Questo documento poggia su cinque ADR: [ADR 0002](adr/0002-multi-site-topology.md) per la topologia e la perdita di un sito, [ADR 0005](adr/0005-backup-disaster-recovery.md) per la protezione dei dati e il percorso critico, [ADR 0007](adr/0007-source-control-and-recovery.md) per GitLab, [ADR 0010](adr/0010-audit-evidence-and-retention.md) per l'audit e [ADR 0011](adr/0011-south-recovery-dependencies.md) per le dipendenze di South.

Nulla di quanto descritto qui è stato testato. Le durate sono stime di modello e i punti che richiedono una verifica sono segnalati dove compaiono. **L'RTO di 4 ore è un progetto credibile e condizionato, non uno SLO raggiunto.**

## 1. Disponibilità, DR e backup sono cose diverse

Teniamo separati tre livelli di protezione. L'HA locale copre la perdita di un host, di un nodo, di un pod o di un fault domain di storage all'interno di un sito, con almeno 3 fault domain VMware per sito attivo, repliche, anti-affinity e PDB.

Il recovery di sito (DR) copre la perdita di Central: South subentra dopo dichiarazione e fencing, con cluster caldi, dati replicati in continuo e servizi abilitanti già in esecuzione in South.

Il backup protegge da corruzione, ransomware e cancellazioni per errore, e dalla perdita di entrambi i siti attivi: sono copie versionate e immutabili in North, con evidenze di restore. **La replica non può sostituire il backup, perché replica anche le cancellazioni.**

## 2. Perimetro e tier di recovery

| Servizio | RPO | RTO | Strategia |
|---|---:|---:|---|
| Produzione di Central su cluster gestiti dalla piattaforma (inventario di recovery firmato) | ≤60 min | ≤240 min | Controparti DR calde 1:1 in South, replica continua per classe di dato (§3), artefatti di rilascio già posizionati in South |
| Control plane dell'IDP (catalogo, GitOps, GitLab, secret, identità) | ≤60 min | ≤240 min | Servizi abilitanti già attivi in South ([ADR 0011](adr/0011-south-recovery-dependencies.md)); Backstage primario in South; promozione Geo fuori dal percorso critico |
| Produzione ancora su cluster legacy creati manualmente | Come documentato per singola applicazione | Come documentato per singola applicazione | Fuori perimetro fino alla migrazione; ogni applicazione è elencata con la sua capacità reale e un'eccezione firmata dal CIO ([07](07-roadmap.md)) |
| Namespace self-service di sviluppo e test in South | Nessun RPO | ≤60 min per la ricreazione, una volta disponibile la capacità | Ambienti dichiarativi; sono i primi a essere rimossi se in DR la capacità scarseggia |
| Telemetria operativa | Non replicata | L'osservabilità di South è sempre disponibile | Lo stack LGTM di South è già in esecuzione; solo lo storico del tenant `capacity` viene copiato ogni giorno |
| Audit della piattaforma e di Kubernetes | Ritardo di consegna ≤5 min | Recupero ≤4 h | Doppio archivio immutabile ([ADR 0010](adr/0010-audit-evidence-and-retention.md)) |

Come revisione facoltativa del target, da sottoporre all'accettazione del CIO, la produzione non critica per il business potrebbe essere collocata in un tier con RTO e RPO più lunghi, per esempio 24 h, e recuperata da backup. Questo ridurrebbe la riserva calda; il progetto non lo presuppone.

## 3. Matrice di protezione per classe di dato

| # | Classe di dato | Esempi | Meccanismo | Ritardo / frequenza | RPO | Percorso di ripristino al failover | Copia anche in North | Owner |
|---|---|---|---|---|---:|---|---|---|
| D1 | SQL di produzione | RDBMS applicativi | Replica asincrona cross-site nativa verso una replica in South | Continua; allarme a 15 min di ritardo | ≤60 min | **Promozione della replica** (nessun restore) | Backup point-in-time (base + log) | Data Engineering |
| D2 | NoSQL di produzione | Document store o key-value store | Replica cross-site nativa; in sua assenza snapshot + log shipping ≤30 min | Continua / ≤30 min | ≤60 min | Promozione, oppure applicazione dell'ultimo log | Snapshot | Data Engineering |
| D3 | Dati PVC di produzione (file/block fuori da un database) | Upload, code su disco | Replica di storage o applicativa verso South; backup Velero con CSI data mover su object storage per la copia in North (candidato, da verificare sulla versione adottata) | Continua / ≤30 min | ≤60 min | Collegamento del volume replicato; il restore da backup è solo il fallback | Sì | Data Engineering + Platform Engineering |
| D4 | Oggetti runtime Kubernetes non presenti in Git | Risorse generate dagli operator, certificati | Backup Velero per namespace; ogni manifest di produzione è in Git | ≤30 min | ≤30 min | In gran parte rigenerati; si ripristina il resto | Sì | Platform Engineering |
| D5 | Artefatti di rilascio e stato desiderato | Immagini firmate, attestazioni, artefatti OCI di Flux | Push nel registry di South come parte di ogni rilascio, con verifica della copia | Al rilascio | 0 per le versioni rilasciate | Già in South | Backup di GitLab | Platform Engineering |
| D6 | Git, merge request, metadati delle pipeline, registry GitLab | GitLab | Replica Geo (con replica del registry configurata esplicitamente) + backup giornaliero in North | Continua; allarme a 15 min di ritardo | ≤60 min | Promozione Geo (fuori dal percorso critico) | Backup giornaliero | Platform Engineering |
| D7 | Stato dell'infrastruttura | State OpenTofu, oggetti CAPI dei cluster gestiti da South | Backend versionato replicato in South (F-23), senza valori di secret nello state; i cluster di South sono gestiti dal management cluster di South | ≤60 min | ≤60 min | Già locale | Sì | Platform Engineering |
| D8 | Snapshot di etcd | Ogni cluster | Snapshot cifrato in North ogni 6 h | 6 h | n/a | **Solo ricostruzione in place dello stesso cluster**, mai per il DR cross-site | Sì | Platform Engineering |
| D9 | Secret e chiavi | Dati del secret manager, chiavi HSM/KMS | Secret manager per sito, propagazione ≤60 min; chiavi per sito | ≤60 min | ≤60 min | Già in South | Materiale di recovery sigillato | Network Security |
| D10 | Database di piattaforma | Backstage (primario in South), Grafana (per sito) | Replica PostgreSQL South→Central per Backstage (F-22); dashboard Grafana da Git | Continua | ≤60 min | Backstage non risente della perdita di Central | Sì | Data Engineering |
| D11 | Audit | Tutte le fonti di audit | Doppio archivio immutabile | ≤5 min | ≤5 min | Già in South e in North | Sì | SRE (approvazione del CISO) |
| D12 | Telemetria | Metriche, log, trace | Tenant capacity copiato ogni giorno; il resto non è replicato | 24 h | 24 h (solo capacity) | Caricamento di `capacity-central` in South | No | SRE |
| D13 | Sviluppo e test | Namespace di South | Ricreati dal codice | n/a | Nessuno | Ricreazione | No | Platform Engineering |

Il motivo per cui nessun restore sta sul percorso critico è il tempo di trasferimento (stima). Spostare 1 TiB con un'efficienza del collegamento del 70% richiede `2^40 × 8 / (bandwidth × 0.7)`: 34,9 h a 100 Mbps, 3,49 h a 1 Gbps e 0,35 h a 10 Gbps. La banda tra i siti non è nota (A-05), quindi qualunque dataset in perimetro che dipenda da un restore è incompatibile con un RTO di 4 h.

## 4. Servizi abilitanti di South

South esegue in proprio, già prima di un disastro, IdP, CA emittente, secret manager, HSM/KMS, DNS, NTP, vCenter, registry OCI, load balancer, il primario di Backstage, l'osservabilità e il relay di audit. Al failover questi servizi si verificano, non si ricostruiscono. Lo stato normale di ciascuno, il relativo fallback e l'owner sono in [ADR 0011](adr/0011-south-recovery-dependencies.md).

Tre situazioni sono bloccanti in Fase 0, a meno che il CIO non accetti la conseguenza sull'RTO: un unico vCenter in Central, un IdP o una directory presenti solo in Central, un secret manager privo di un meccanismo cross-site.

## 5. Stato caldo del DR, riserva di capacità e parità

Ogni cluster DR esegue il control plane, un pool minimo di worker, gli add-on di piattaforma (Flux, admission, collector, ingress) e i namespace di produzione attraverso un overlay DR: Deployment e StatefulSet a 0 repliche, CronJob e consumer delle code sospesi, Kustomization di produzione sospese. Un'attivazione accidentale non può quindi consumare code né scrivere sui database.

La riserva di capacità è una condizione di finanziamento vincolante. South riserva CPU, RAM, IOPS e indirizzi IP pari alle request della produzione di Central, sotto forma di resource reservation di vSphere. CAPV scala i worker pool DR dentro quella riserva **in parallelo alla promozione dei dati**, in 40 minuti secondo il modello, e gli ambienti di sviluppo e test di South possono essere sospesi per liberare capacità. Senza la riserva, i control plane caldi non servono a nulla.

Per la parità, un report giornaliero di drift confronta ogni cluster di Central con la sua controparte DR: minor version di Kubernetes, CRD e versioni degli add-on, policy, namespace e overlay. L'anello di upgrade è non-prod → DR → prod, quindi il DR non è mai indietro rispetto alla produzione. Un drift non approvato apre un ticket; un drift più vecchio di 7 giorni fa chiamare il reperibile di Platform Engineering.

## 6. Dichiarazione e fencing

Il disastro si dichiara solo se valgono tutti e tre i criteri seguenti:

1. il metamonitoring di South vede irraggiungibili i servizi di piattaforma e lo stack LGTM di Central da almeno 10 minuti;
2. un secondo punto di osservazione lo conferma: lo strumento black-box legacy, se si trova fuori da Central, una sonda di raggiungibilità in North, oppure una conferma delle operations del sito Central per telefono o tramite ITSM;
3. Central non serve i propri utenti, e le operations di Central confermano la perdita del sito, non sono raggiungibili oppure non sono in grado di impegnarsi a un ripristino credibile entro 60 minuti.

Dichiara l'incident commander SRE, con autorità delegata dal CIO, di norma entro 20 minuti dal rilevamento: è il budget previsto al §7.

Se le operations di Central si impegnano a ripristinare entro 60 minuti, l'incident commander può attendere, ma **per non più di 60 minuti**; se allo scadere il ripristino non è avvenuto, la dichiarazione è immediata. Il caso con attesa si chiude quindi a 175 + 60 = 235 min (valore modellato, `dr_summary()` nel modello di capacità), ancora dentro i 240. North ha solo valore consultivo: se anche North è irraggiungibile, il secondo criterio si soddisfa con una conferma fuori banda.

Se Central è vivo ma isolato e continua a servire i propri utenti, non si esegue alcun failover, perché il terzo criterio non è soddisfatto. Il ritardo di replica cresce e genera allarmi, e l'esposizione sull'RPO viene comunicata al CIO.

Il fencing prevede quattro azioni:

1. Network Security applica sui firewall di South e North la policy di quarantena di Central (Central quarantine) predisposta in anticipo: i flussi di replica e di scrittura in ingresso da Central vengono negati, mentre resta aperto l'ingest del relay di audit, così le evidenze non vanno perse;
2. Data Engineering promuove le repliche in South;
3. al ritorno di Central, i vecchi primari vengono **retrocessi o ricostruiti, mai ripresi**; GitLab segue la procedura Geo per reintrodurre il vecchio primario come secondario;
4. i record delle applicazioni di Central vengono ritirati da GSLB/DNS.

## 7. Runbook per la perdita di Central e percorso critico modellato

Il runbook presuppone alcune condizioni, monitorate in continuo: l'inventario di recovery firmato associa ogni applicazione di produzione al suo cluster DR e alla sua classe di dato; il ritardo di replica non supera i 15 minuti; il registry di South contiene il rilascio corrente; i check sintetici dei servizi abilitanti sono verdi; la riserva è intatta; il report di parità è pulito.

| # | Passo | Owner | Inizio–fine (min) | Durata | Dipende da | Sul percorso critico? |
|---|---|---|---|---:|---|---|
| 1 | Rilevamento, apertura dell'incidente, registrazione di T0 | SRE | 0–15 | 15 | Metamonitoring di South, dead-man's switch | Sì |
| 2 | Dichiarazione (criteri del §6) e fencing | Incident commander SRE + Network Security | 15–35 | 20 | 1 | Sì |
| 3A | Verifica dei servizi abilitanti di South (IdP, PKI, secret, DNS, registry) | Network Security + Platform Engineering | 35–50 | 15 | 2 | No |
| 3B | Promozione di GitLab Geo; reindirizzamento dello stream di audit e dei runner | Platform Engineering | 35–80 | 45 | 2 | No: i cluster DR riconciliano dal registry di South |
| 3C | Promozione in parallelo di database e volumi replicati; controlli di consistenza tramite script | Data Engineering | 35–95 | 60 | 2 | Sì |
| 3D | Scale-out dei worker pool DR via CAPV dentro la riserva | Platform Engineering | 35–75 | 40 | 2, vCenter di South | No, a meno che superi i 60 min |
| 4 | Attivazione dei workload: ripresa delle Kustomization, overlay DR → repliche di produzione, collegamento ai dati promossi | Platform Engineering | 95–125 | 30 | 3A, 3C, 3D | Sì |
| 5 | Validazione applicativa e dei dati | Owner applicativi + Data Engineering | 125–150 | 25 | 4 | Sì |
| 6 | Commutazione del traffico: DNS/GSLB predisposti, TTL ≤60 s | Network Security | 150–160 | 10 | 5 | Sì |
| 7 | Test sintetico end-to-end e approvazione del business | SRE + owner di business | 160–175 | 15 | 6 | Sì |
| | Totale (modellato) | | | **175** | | Margine 65 min (27%) |

I conti che seguono sono stime. Un runbook puramente sequenziale richiederebbe 15 + 20 + 40 + 90 + 50 + 25 = 240 min, senza alcun margine. Il percorso progettato vale 15 + 20 + 60 + 30 + 25 + 10 + 15 = 175 min: rispetta l'obiettivo interno di al massimo 180 min e lascia 65 min di margine rispetto al target di 240. Queste durate restano assunzioni di modello finché non saranno disponibili misure per singolo passo (§9).

La tabella seguente mostra come cambia il totale al variare delle durate.

| Variazione | Nuovo totale | Margine rispetto a 240 |
|---|---:|---:|
| Promozione dei database in 90 min invece di 60 | 205 | 35 |
| Rilevamento + dichiarazione in 60 min invece di 35 | 200 | 40 |
| Attivazione dei workload in 60 min invece di 30 | 205 | 35 |
| Scale-out dei worker in 70 min invece di 40 (termina dopo i dati) | 185 | 55 |
| Promozione Geo necessaria sul percorso e lunga 90 min (nessuna copia nel registry di South) | 205 | 35 |
| Promozione dei database in 90 min e dichiarazione in 60 | 230 | 10 |
| Restore obbligato di un dataset da 1 TiB a 1 Gbps | ≈324 | **RTO violato** |

Dopo la commutazione si riprotegge il servizio: si attivano i backup da South verso North e si decide la capacità DR mentre Central viene ricostruito. Il failback è un change pianificato e separato, con replica inversa, e non è mai automatico.

## 8. Altri scenari di perdita di sito

La tabella degli scenari di perdita di sito (North, South, Central + South, Central + North, partizioni) è in [ADR 0002](adr/0002-multi-site-topology.md).

## 9. Strategia di validazione

In continuo, con riepilogo giornaliero, dashboard e alert seguono il ritardo di replica, il completamento dei backup, il ritardo dell'archivio, lo stato di Geo, l'allineamento del registry di South e i check sintetici dei servizi abilitanti.

Ogni mese si esegue un restore isolato di oggetti campione da North, che corrisponde al percorso di recupero da ransomware, con log del restore e checksum come evidenza. Sempre ogni mese si misurano i tempi dei singoli passi: promozione dei database per ciascun prodotto, prova di promozione Geo su un secondario di test, dry run di attivazione dell'overlay DR e commutazione DNS. Le registrazioni hanno timestamp e se ne ricavano mediana e massimo per passo; i percentili si calcolano solo dopo almeno 20 campioni.

Ogni trimestre si tiene un game day su una coorte rappresentativa (un sottoinsieme di T-11), con tempi end-to-end e RPO misurato per dataset. L'autonomia di South (T-18) si verifica ogni trimestre e la partizione senza perdita (T-19) due volte l'anno, con esito superato o non superato per ogni passo.

La simulazione di perdita di Central sull'intero inventario (T-11) si esegue prima dell'impegno in produzione e poi ogni anno. Ogni applicazione in perimetro deve essere recuperata entro 240 min, e l'RPO si misura per dataset come distanza tra l'ultima transazione durevole in Central e l'ultima transazione replicata in South. **Due drill sull'intero inventario dimostrano due esiti funzionali, non stabiliscono un percentile di coda.**

## 10. Modi di guasto che invalidano il progetto

Il progetto non regge nei casi seguenti:

- un dataset in perimetro senza replica continua, perché ripristinarlo mette il restore sul percorso critico (§7);
- IdP, CA, secret manager, vCenter o registry presenti solo in Central ([ADR 0011](adr/0011-south-recovery-dependencies.md));
- l'assenza della riserva di capacità in South, che lascia control plane caldi senza worker;
- un vecchio primario di Central ripreso al ritorno del sito (split-brain), che il fencing e la regola di retrocessione impediscono;
- GitLab Geo, con replica in pausa o in ritardo, usato come unica fonte dello stato desiderato, caso evitato dalla copia nel registry di South ([ADR 0007](adr/0007-source-control-and-recovery.md));
- un anno di retention dell'audit trattato come se fosse un backup di Loki ([ADR 0010](adr/0010-audit-evidence-and-retention.md)).
