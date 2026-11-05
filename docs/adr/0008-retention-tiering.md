# ADR 0008: livelli di retention delle metriche e separazione dello storage di audit

- Stato: proposta, in attesa della revisione di progetto con il cliente
- Data: 2026-11-05
- Decisori: SRE, per i livelli della telemetria
- Revisori: CISO, che approva la retention dell'audit; Data Engineering, consultato per lo storage

## Contesto

Il cliente chiede di conservare le metriche per 30 giorni a piena risoluzione e quelle utili al capacity planning per 13 mesi, i log operativi per 30 giorni, le trace per 7 giorni e l'audit della piattaforma e di Kubernetes per almeno un anno.

Due caratteristiche dei prodotti condizionano il progetto. La compattazione di Mimir **non riduce la risoluzione temporale**: ogni giorno di serie grezze occupa lo stesso spazio, che la retention sia breve o lunga, e il costo cresce in proporzione ai giorni conservati. Lo storage dei log operativi, da solo, non ha il valore probatorio che serve per l'audit.

## Opzioni considerate

La soluzione più diretta (opzione A) tiene 13 mesi di tutte le metriche a piena risoluzione e un anno di tutti i log in Loki. È semplice, ma richiede circa 13× lo storage delle metriche e mescola l'evidenza di audit con i log operativi.

L'opzione B separa i dati in base all'uso. I tenant Mimir con i dati grezzi restano a 30 giorni, e un tenant `capacity` separato, a bassa cardinalità, conserva 13 mesi. Loki resta a 30 giorni e Tempo a 7. L'audit va in un archivio immutabile separato in North, conservato 400 giorni. Il prezzo è una copertura di lungo periodo limitata a un insieme scelto di serie e alcune regole da rispettare nei dashboard, descritte nelle conseguenze.

L'opzione C prevede un'aggregazione scritta a mano in un database separato. L'abbiamo scartata perché sta fuori dallo stack Grafana e aggiunge un componente su misura.

Per produrre le serie di capacity abbiamo valutato tre varianti. Un secondo scrape a bassa frequenza (B1) duplica la configurazione di raccolta su ogni cluster e non permette di aggregare tra cluster. Un export da Grafana (B3) non è affidabile per uno storico continuo. Resta la variante B2, le recording rule federate di Mimir possedute dal tenant `capacity`, che è quella scelta.

## Decisione

Scegliamo l'opzione B con il produttore B2.

Le recording rule del tenant `capacity` leggono da `platform` e dai tenant `t-*` (`source_tenants`) ogni **300 s** e scrivono circa 40.000 serie in allowlist: CPU, memoria, storage, numero di pod e di richieste per sito, cluster, namespace e team. Servono due prerequisiti: il ruler di Mimir e la federazione dei tenant in query devono essere abilitati, e l'accesso in lettura a `capacity` va riservato a SRE e capacity planner, perché il tenant aggrega dati di molti tenant. La retention è di 395 giorni, impostata con un override per tenant del compactor.

Poiché il lookback predefinito di PromQL è di 5 minuti, i dashboard di capacity usano funzioni di range (per esempio `last_over_time(x[10m])`) con uno step di almeno 5 minuti. Se si osservano buchi, si può ripiegare su un intervallo inferiore a 300 s: a 120 s, per esempio, il tier passerebbe da circa 41 GB a circa 102 GB, margine compreso.

Per proteggere lo storico dalla perdita di Central, i blocchi `capacity` di Central vengono copiati ogni giorno in un prefisso DR separato in South (flusso F-05) e, dopo un failover, si possono caricare in South come `capacity-central`. L'RPO dello storico di capacity è quindi al massimo di 24 ore. Per dati di pianificazione è accettabile, e non va confuso con un RPO di produzione.

L'audit è conservato per 400 giorni (almeno 365 richiesti, più un margine) in un doppio archivio immutabile: North più una copia in South, entrambi in compliance mode e amministrati separatamente. Lo alimenta un relay dedicato con acknowledgement, spool locale e manifest concatenati con hash. Il tenant `security` di Loki tiene solo una copia ricercabile di 30 giorni; gli eventi più vecchi si ripristinano su richiesta in un tenant temporaneo. Il modello di evidenza completo, che è una decisione del CISO, è in [ADR 0010](0010-audit-evidence-and-retention.md).

## Conseguenze

La copertura di capacity è limitata all'allowlist: ciò che non vi rientra scompare dopo 30 giorni, e ogni modifica all'allowlist passa dal processo di change dell'osservabilità.

La disciplina sul lookback diventa una regola per chi scrive i dashboard e si controlla nella review dei dashboard as code.

Le regole di lifecycle dell'object store non devono cancellare oggetti che i compactor di Loki o Mimir referenziano ancora.

## Validazione e trigger di revisione

Nel pilota si eseguono quattro prove:

- una query di trend su 13 mesi con dati di prova;
- una query a cavallo di un cambio di mese;
- il caricamento in South della copia di capacity di Central;
- un tentativo di cancellare un oggetto di audit prima della scadenza.

La decisione si riapre se i capacity planner hanno bisogno di serie fuori dall'allowlist, se le regole federate mostrano errori di valutazione su larga scala o se il CISO cambia la retention dell'audit. In quel caso si registra un nuovo ADR che sostituisce questo, senza riscrivere la storia.
