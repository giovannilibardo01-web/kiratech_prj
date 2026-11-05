# ADR 0011: dipendenze del ripristino in South senza appoggi nascosti su Central

- Stato: proposta; diversi punti sono bloccanti della Fase 0, in attesa dell'inventario delle funzioni di IdP, PKI, DNS, vCenter e secret manager già presenti presso il cliente (RAID Q-08, Q-14)
- Data: 2026-11-05
- Decisori: Network Security (identità, PKI, DNS, firewall)
- Realizzazione: Platform Engineering (integrazione con vCenter, registry, GitOps), Data Engineering (servizi dati replicati)
- Revisori: CISO, che approva custodia e recupero delle chiavi
- Documenti correlati: [progetto DR](../05-reliability-and-dr.md), [ADR 0005](0005-backup-disaster-recovery.md), [ADR 0007](0007-source-control-and-recovery.md), [baseline di sicurezza §5](../04-security-and-tenancy.md)

## Contesto

Dopo la perdita di Central, il control plane della piattaforma e la produzione devono essere ripristinabili in South con RPO di 1 h e RTO di 4 h. Avere cluster caldi in South non serve a nulla se per accedere, emettere certificati, leggere secret, risolvere nomi, creare VM o scaricare immagini occorre ancora un servizio che esiste solo in Central.

Stabilire che South non debba dipendere da API presenti solo in Central non basta: ogni servizio abilitante va progettato per South, uno per uno. E oggi le topologie del cliente per identità, PKI, DNS, vCenter e secret manager sono **sconosciute**.

## Opzioni considerate

La prima strada è ripristinare i servizi condivisi durante il disastro, riportando in South IdP, PKI, secret manager e DNS dai backup di North. Ognuno di questi servizi finirebbe sul percorso critico prima di qualsiasi workload, con il proprio tempo di restore e la banda necessaria da North. Dentro 4 h non è credibile, e l'abbiamo scartata.

La seconda tiene ogni servizio abilitante attivo in South in ogni momento, sincronizzato in continuo da Central, e al failover si limita a verificarlo. Costa una seconda istanza in esercizio per ogni servizio e flussi di sincronizzazione permanenti, ma toglie i restore dal percorso critico.

La terza si affida ai servizi di Central e accetta che il ripristino in South abbia bisogno di Central. Contraddice lo scenario stesso, in cui Central è perso, ed è scartata.

## Decisione

Scegliamo la seconda opzione. Ogni servizio della tabella deve **essere in esercizio in South prima del disastro**; al failover lo si *verifica*, non lo si *ricostruisce*.

| Servizio | Design in South (stato normale) | Durante la perdita di Central | Se fallisce l'istanza di South | Owner |
|---|---|---|---|---|
| Identità (OIDC) per persone e servizi | Istanza o replica dell'IdP in South, sincronizzata dalla directory aziendale, che serve Grafana, Backstage, GitLab, API Kubernetes e query gateway | Gestisce tutti gli accessi in locale | Account locali break-glass sigillati (Kubernetes, GitLab, vCenter, Grafana), in doppio controllo | Network Security |
| PKI | Root CA offline. Una CA emittente per sito (Central, South), entrambe trusted su tutta la piattaforma. cert-manager in ogni cluster usa l'issuer del proprio sito. I certificati a vita breve riducono la dipendenza dai controlli di revoca. Gli endpoint di revoca sono pubblicati per sito | South emette e rinnova in autonomia | Cerimonia della root per riemettere l'intermedia di South (custodia del CISO) | Network Security |
| Secret manager | Istanza HA per sito, con unseal tramite l'HSM/KMS del sito. I secret di produzione sono presenti in South con un ritardo ≤60 min dalla modifica, per replica nativa o doppia scrittura ([04](../04-security-and-tenancy.md) §5) | L'istanza di South serve direttamente External Secrets | Quote di recupero affidate a custodi nominati dal CISO, compreso un gruppo di custodi in South | Network Security (approvazione del CISO) |
| HSM / KMS | Chiavi per sito per la firma delle immagini, la firma dei manifest e l'unseal | Si usano le chiavi di South | Backup dell'HSM secondo le modalità del vendor; cerimonia delle chiavi documentata | Network Security (custodia del CISO) |
| DNS | Zone autorevoli della piattaforma servite da secondari in South. I record commutabili per il DR hanno TTL ≤60 s. I record GSLB o LB degli endpoint applicativi sono predisposti in anticipo | South gestisce la risoluzione; Network Security commuta i record | Secondario in North come resolver di ultima istanza per le zone della piattaforma (da verificare) | Network Security |
| Tempo (NTP) | Almeno 2 sorgenti di tempo locali per sito | Locale | Monitorato; i numeri di sequenza proteggono l'ordinamento dell'audit | Network Security |
| vCenter / gestione VMware | vCenter di South indipendente da Central (gestione propria, nessuna dipendenza dall'SSO di Central). Il Cluster API Provider vSphere (CAPV) del management cluster di South usa un'identità di cluster solo di South | CAPV scala i worker pool DR di South senza Central | Worker pool predimensionati (vedi [05](../05-reliability-and-dr.md) §5) | Platform Engineering (con l'owner di VMware) |
| Container registry e stato desiderato | Il registry OCI di South riceve ogni rilascio di produzione: immagini, attestazioni e l'artifact OCI di Flux firmato. Il rilascio non è completo finché la copia in South non è verificata. La replica Geo del registry di GitLab va configurata esplicitamente, perché per impostazione predefinita non avviene | I cluster DR riconciliano dal registry di South; **GitLab non serve sul percorso critico** | Nuovo push dal GitLab promosso con Geo, oppure dal backup di North | Platform Engineering |
| Git / CI | Secondario GitLab Geo in South (sola lettura) | Promosso in parallelo, fuori dal percorso critico ([ADR 0007](0007-source-control-and-recovery.md)) | Restore di GitLab dal backup di North; la produzione continua dagli artifact OCI | Platform Engineering |
| Trust cross-site dei token (viste di flotta) | Ogni query gateway si fida delle chiavi di firma dell'IdP di entrambi i siti, sincronizzate insieme ai dati di identità (F-15) | Le viste di flotta si degradano; le viste locali di ciascun sito restano intatte | Solo viste locali | Network Security |
| Load balancer / ingress | VIP e ingress controller predisposti nei cluster DR | Attivati insieme ai workload | Seconda coppia di LB in South | Network Security |
| Backstage (catalogo) | Primario in South, perché serve il self-service di South; istanza di standby calda in Central con replica del database | Nessun impatto | Promozione dello standby di Central se si perde South | Platform Engineering |
| Osservabilità e audit | Indipendenti per sito ([03](../03-observability-deep-dive.md), [ADR 0010](0010-audit-evidence-and-retention.md)) | Lo stack di South continua a funzionare | Non applicabile | SRE |
| Paging / ITSM | Raggiungibili da South senza attraversare Central | Usati per l'incidente DR | Albero telefonico conservato offline | SRE |

La regola che ne discende è semplice: qualsiasi passo di ripristino che richieda un servizio presente solo in Central fa fallire il test DR.

Tre situazioni sono bloccanti della Fase 0: un unico vCenter in Central che gestisce anche gli host di South, un IdP o una directory presenti solo in Central, un secret manager senza un modello cross-site. Ognuna va cambiata, oppure accettata formalmente dal CIO dichiarando la conseguenza sull'RTO.

## Conseguenze

Il costo è una seconda istanza in esercizio, in South, di IdP, CA, secret manager, HSM/KMS, DNS, vCenter e registry, più i flussi di sincronizzazione da F-13 a F-16 descritti in [12](../12-firewall-flows.md). In [10](../10-cost-and-tco.md) è valorizzato come voce a sé ("servizi abilitanti di South", 48 vCPU), accanto alla riserva DR.

Sul piano della sicurezza aumentano le istanze da sottoporre a hardening e ad audit. In compenso le chiavi per sito riducono il raggio d'impatto di una chiave compromessa, e la fiducia nelle CA emittenti e nelle chiavi di firma di entrambi i siti è dichiarata esplicitamente nella configurazione di admission e di mTLS.

Sul piano operativo l'affermazione "è in esercizio in South" perde valore se non viene verificata con continuità. Per questo da South gira ogni giorno un controllo sintetico per ciascun servizio.

## Validazione

Il test T-18 misura l'autonomia di South. Si bloccano tutti i flussi Central↔South, in due varianti: una con North raggiungibile e una senza. Da South devono riuscire queste operazioni:

- accedere con OIDC;
- emettere un certificato;
- leggere una versione di un secret di produzione creata ≤60 min prima;
- scalare un worker pool DR tramite CAPV;
- scaricare un'immagine firmata e riconciliare un artifact OCI di Flux dal registry di South;
- risolvere e commutare un record DNS di DR;
- interrogare Grafana di South;
- ricevere una chiamata di paging.

Ogni passo è registrato con il proprio timestamp. Il test si esegue prima dell'impegno in produzione e poi ogni trimestre.

## Trigger di revisione

L'ADR va rivisto in tre casi: se i servizi esistenti del cliente offrono già capacità cross-site equivalenti, e allora il disegno si semplifica; se il CIO accetta una dipendenza da Central con un RTO più lungo; se cambia il prodotto scelto per il registry o per il secret manager.
