# ADR 0002: control plane indipendenti per sito, DR caldo 1:1 in South e comportamento alla perdita di un sito

- Stato: proposta; restano aperte le verifiche su capacità, banda e inventario.
- Data: 2026-11-05
- Decisori: Platform Engineering
- Revisori: SRE, che approva; CIO, che accetta i rischi residui
- Documenti correlati: [architettura](../02-architecture.md), [disegno del DR](../05-reliability-and-dr.md), [ADR 0005](0005-backup-disaster-recovery.md), [ADR 0011](0011-south-recovery-dependencies.md)

## Contesto

Central ospita la produzione critica per il business. South ospita gli ambienti non di produzione ed è il secondo sito di deployment. North è il sito di backup off-site.

I collegamenti tra i siti hanno un RTT di 10–20 ms e ogni flusso tra siti passa da un firewall. La latenza è abbastanza bassa per una replica asincrona. Un quorum etcd esteso tra i siti, però, legherebbe tra loro i domini di guasto: due siti non possono formare un quorum che sopravviva alla perdita di uno dei due, e un terzo votante in North trasformerebbe North in una dipendenza a runtime.

La perdita di Central impone RPO ≤1 h e RTO ≤4 h per la produzione e per il control plane della piattaforma. Entro 18 mesi la piattaforma dovrebbe arrivare a circa 30 cluster e 1.500 pod; è un obiettivo di pianificazione, non una topologia imposta.

Questo ADR stabilisce quanti cluster, e di quale tipo, girano in ciascun sito, dove risiede il piano di gestione e che cosa succede quando si perde **un sito qualsiasi**.

## Opzioni considerate

### Topologia

L'opzione 1, cluster estesi tra i siti, è scartata: richiede un quorum tra siti, porta con sé la complessità di partizioni e fencing e fa condividere ai siti lo stesso raggio d'impatto. Anche l'opzione 2, una gestione concentrata in Central con ripristino in South su richiesta, è scartata, perché rende South dipendente da Central e perché la ricostruzione rischia di superare le 4 h. L'opzione 3 prevede piani di gestione e di osservabilità indipendenti in Central e in South, uno standby caldo della produzione in South e North dedicato ai backup immutabili e alle evidenze.

### Mappatura dei cluster DR nell'opzione 3

| Variante | Descrizione | Cluster (totale) | Credibilità dell'RTO | Costo relativo |
|---|---|---:|---|---|
| A. Controparti calde 1:1 | 10 cluster DR in South rispecchiano i 10 cluster di produzione di Central | 30 | La più alta: stessi confini di isolamento, nessun ricollocamento durante il disastro | Overhead di control plane di 10 cluster in più, circa 120 vCPU / 480 GiB (stima) |
| B. A livelli | 1:1 per i 5 cluster più critici; 2 cluster DR condivisi per gli altri 5 | 27 | Alta per il tier 1; per il livello condiviso l'isolamento va riconvalidato | Risparmia 3 control plane: circa 36 vCPU / 144 GiB, ~38 k€ in 3 anni (scenario base, stima) |
| C. In pool | 3 cluster DR condivisi ospitano tutti i namespace di produzione | 23 | Media: durante il DR la produzione perde l'isolamento a livello di cluster, quindi il CISO deve riapprovare | Risparmia 7 control plane: circa 84 vCPU / 336 GiB, ~88 k€ in 3 anni (scenario base, stima) |
| D. Ricostruzione a freddo con CAPV | Nessun cluster DR permanente | 20 | Bassa: il provisioning sta sul percorso critico | Il costo di standby più basso |

Le stime assumono 3 VM di control plane da 4 vCPU / 16 GiB per cluster. La riserva di worker per la produzione ripristinata è la stessa in A, B e C, perché devono girare gli stessi carichi: la differenza tra A e B/C sta quindi soltanto nell'overhead dei control plane.

Durante la migrazione la flotta supera temporaneamente i 30 cluster, perché i cluster legacy vengono dismessi una coorte alla volta ([roadmap](../07-roadmap.md)).

## Decisione

Adottiamo la topologia dell'opzione 3 e, come progetto di partenza, la **variante A** per la mappatura DR. La variante B resta la leva di costo documentata, da riconsiderare dopo l'inventario dei carichi (Q-01, Q-09).

| Sito | Cluster | Numero |
|---|---|---:|
| Central | 1 management cluster, 1 di osservabilità, 10 di produzione | 12 |
| South | 1 management cluster, 1 di osservabilità, 10 DR caldi, 6 non di produzione condivisi | 18 |
| North | Nessun Kubernetes. Backup e archivio immutabile amministrati in modo indipendente, endpoint di ripristino, verificatore di integrità | 0 |
| Totale | | 30 |

I 10 cluster di produzione sono un perimetro di pianificazione (A-01, A-02) compatibile con l'obiettivo di circa 30 cluster e coerente con un isolamento a livello di cluster per classi di rischio: dati regolamentati, carico elevato, standard condiviso. Il numero viene ricalcolato sull'inventario classificato prima dell'acquisto dei cluster e non è un requisito.

Sui control plane valgono tre regole. etcd e control plane di ogni cluster sono locali al sito, senza membri in altri siti. Il management cluster di ciascun sito gestisce soltanto i cluster del proprio sito, attraverso il proprio vCenter ([ADR 0011](0011-south-recovery-dependencies.md)). In condizioni normali Central è autorevole per la produzione; South subentra solo dopo la dichiarazione di disastro e il fencing ([05](../05-reliability-and-dr.md) §6), e le scritture non sono mai attive su entrambi i siti.

### Cosa succede quando si perde un sito

| Evento | Impatto immediato | Cosa continua a funzionare | Risposta | Obiettivo / rischio accettato |
|---|---|---|---|---|
| Perdita di Central | Produzione e piattaforma di Central ferme | Piattaforma di South, osservabilità di South, Backstage (primario in South), audit (copia in South e North) | Dichiarazione, fencing, promozione dei dati, attivazione dei cluster DR 1:1 ([05](../05-reliability-and-dr.md) §7) | RPO ≤60 min / RTO ≤240 min per la produzione in perimetro (175 min modellati) |
| Perdita di South | Self-service dev/test, capacità di DR, secondario Geo, osservabilità e copia di audit di South, primario di Backstage | Produzione in Central; osservabilità di Central; audit verso North | Promozione dello standby di Backstage in Central; le richieste di produzione passano direttamente da GitLab; al ritorno di South si ristabiliscono il secondario Geo e il DR | **Nessuna protezione DR finché South è giù**: rischio accettato dal CIO con un piano di riprotezione; catalogo ripristinato in orario lavorativo |
| Perdita di North | Backup e archivio di audit di North non disponibili | Produzione, entrambi i siti attivi, la copia di audit in South | Relay e job di backup accodano localmente (≥72 h); oltre questo limite i backup vanno temporaneamente su un target separato in South e l'audit prosegue sulla copia di South | Nessuna perdita di evidenze; protezione dal ransomware ridotta fino al ritorno di North, con il CISO informato |
| Perdita di Central e North | Come per la perdita di Central, ma senza backup off-site | South con il DR | Failover su South; backup locali in South finché North non viene ricostruito | Stesso RTO; capacità di recupero dal ransomware ridotta |
| Perdita di Central e South | Nessuna capacità di esecuzione | Backup e archivio di audit di North | Ricostruzione dell'infrastruttura, poi ripristino da North | **Nessun RTO impegnato** (da giorni a settimane): rischio accettato dal CIO; si può negoziare un livello di disaster recovery separato |
| Perdita di South e North | Nessun DR, nessun backup off-site | Produzione di Central | Accodamento locale; ricostruzione | Rischio accettato dal CIO |
| Partizione Central ↔ South | Crescono i ritardi di replica e di Geo; le viste di flotta si degradano | Entrambi i siti servono localmente | Nessun failover finché Central serve i propri utenti (criteri di dichiarazione) | Esposizione sull'RPO segnalata; nessun doppio scrittore |

## Conseguenze

Il guasto resta contenuto nel sito in cui avviene: durante un disastro nessun carico viene ricollocato oltre i propri confini di isolamento, e il numero di cluster corrisponde all'aspettativa del cliente di circa 30.

Lo paghiamo con control plane e add-on inattivi su 10 cluster DR, con la riserva di worker in South, che è la voce di costo dominante, e con i servizi abilitanti duplicati ([ADR 0011](0011-south-recovery-dependencies.md)). Network Security approva ogni flusso tra siti esplicitamente nominato, senza networking tra cluster con wildcard. Sul piano operativo trenta cluster devono seguire l'anello di aggiornamento non-prod → DR → prod, con verifica automatizzata della parità.

## Validazione e trigger di revisione

La decisione si considera validata quando passano quattro prove: T-11, perdita di Central sull'intero inventario; T-18, autonomia di South; T-19, partizione senza failover; un test di perdita di North in cui relay e backup restano in coda per 72 h senza perdite.

Si torna sulla variante B se l'inventario classificato mostra meno di 10 classi di isolamento o se il CFO richiede la leva di costo. La topologia stessa va rivista se la banda misurata tra i siti non sostiene la replica con un ritardo ≤60 min.
