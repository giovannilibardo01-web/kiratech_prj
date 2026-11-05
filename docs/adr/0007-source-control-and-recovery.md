# ADR 0007: resilienza di GitLab Ultimate, contratto di rilascio e sicurezza del GitOps

- Stato: proposta, subordinata alla validazione dell'architettura di riferimento di GitLab, della versione adottata e del comportamento di Geo
- Data: 2026-11-05
- Decisori: Platform Engineering
- Revisori: Network Security, che approva i flussi di Geo e del registry
- Documenti correlati: [progetto DR](../05-reliability-and-dr.md), [ADR 0011](0011-south-recovery-dependencies.md), [ADR 0010](0010-audit-evidence-and-retention.md)

## Contesto

GitLab Ultimate è già a contratto e il cliente vuole usarne quante più funzioni possibile. Oggi gira come unica istanza self-managed in Central. Con ambienti definiti in Git e un RTO di 4 h in caso di perdita di Central, quell'istanza non può restare l'unica autorità da cui dipende l'automazione.

Il comportamento di GitLab Geo che conta per questa decisione è stato verificato sulla documentazione di GitLab il 2026-11-05 e va ricontrollato sulla versione adottata. La replica è asincrona, quindi un failover non pianificato può perdere i dati più recenti. Il failover richiede un intervento umano (`gitlab-ctl geo promote`, preceduto dai controlli preliminari) e il fencing del vecchio primario per evitare lo split-brain. In rete è il secondario ad avviare le connessioni verso il primario, sia per la replica PostgreSQL (TCP 5432) sia per la sincronizzazione dei repository via Git su HTTPS; il registry è indicato sulla porta TCP 5000, e la documentazione raccomanda di aprire le porte in entrambe le direzioni per semplificare il failover. Il container registry, per impostazione predefinita, **non viene replicato automaticamente**. Geo, infine, non è un backup.

## Opzioni considerate

1. Mantenere l'istanza di Central e affidarsi al suo ripristino da backup. È la strada che cambia meno, ma un restore completo non sta dentro un RTO di 4 h.
2. Aggiungere un secondario Geo in South e far arrivare lo stato desiderato della produzione *solo* da GitLab. Si ottiene una copia calda di repository e CI, ma Geo entra nel percorso critico: un secondario in ritardo o in pausa blocca il ripristino.
3. Aggiungere un secondario Geo in South e, in più, un contratto di rilascio che pre-posiziona in un registry di South le immagini firmate e gli artifact OCI di Flux firmati. Costa storage, un servizio di registry e tempo di pipeline, ma il ripristino della produzione non dipende più dalla promozione di Geo.
4. Sostituire GitLab con GitHub o con una suite commerciale per la gestione della flotta. Contraddice il contratto e l'investimento del cliente; l'abbiamo scartata.

## Decisione

Scegliamo l'opzione 3. GitLab resta lo strumento con cui si producono e si approvano le modifiche, ma esce dal percorso critico del ripristino della produzione.

Il primario resta in Central, dimensionato secondo l'architettura di riferimento di GitLab per il numero di utenti; la taglia è da confermare. In South gira un secondario Geo con la **replica del container registry configurata esplicitamente**. L'URL esterno di GitLab è un nome DNS che Network Security sposta su South al momento della promozione, così runner, sorgenti Git di Flux e utenti continuano a usare lo stesso indirizzo.

Nella matrice dei flussi ([12](../12-firewall-flows.md)) F-01 è registrato con il secondario di South come iniziatore e con direzione logica dei dati Central → South. I percorsi di ritorno si aprono per il failover come indica GitLab, e le porte esatte si prendono dalla documentazione della versione adottata.

Il contratto di rilascio è il punto che rende South autonomo. Un rilascio di produzione è completo solo quando sono verificate tutte e tre queste condizioni:

- immagini e attestazioni sono nel registry di GitLab;
- gli stessi digest sono nel registry OCI di South;
- lo stato desiderato Flux del rilascio è pubblicato come artifact OCI firmato nel registry di South.

Le Kustomization di produzione dei cluster DR usano sorgenti `OCIRepository` che puntano al registry di South, verificate con le chiavi pubbliche cosign del sito. Con una chiave pubblica statica Flux verifica la firma dentro il cluster, senza contattare un servizio di trasparenza; il comportamento è da verificare sulle versioni di Flux e cosign adottate.

Quando si perde Central, i cluster DR riconciliano dal registry di South. La promozione di Geo procede in parallelo, fuori dal percorso critico, e serve a riavere CI e merge request per le modifiche successive. Dopo la promozione lo stream degli eventi di audit viene ripuntato sul relay di South ([ADR 0010](0010-audit-evidence-and-retention.md)), si abilitano i runner protetti di South e la firma passa alla chiave di South.

Se Geo non si può promuovere, la produzione continua a girare dagli artifact OCI già pubblicati e GitLab si ripristina dal backup in North, con un RTO più lungo che riguarda solo la CI. Una modifica d'emergenza si può costruire, firmare con la chiave di South in doppio controllo e pubblicare come artifact OCI da una workstation approvata; l'operazione viene registrata e rivista.

I backup supportati di GitLab vanno in North ogni giorno e il loro restore si prova ogni mese. Deploy key, branch protetti, variabili CI, registrazione dei runner e modifiche alle policy di admission sono riservati a gruppi protetti e imposti tramite progetti di security policy ([ADR 0003](0003-tenancy-and-policy.md)).

La corrispondenza tra le funzioni di GitLab Ultimate e i requisiti è mantenuta nella decisione sulla toolchain della piattaforma ([ADR 0001](0001-platform-toolchain.md)).

## Conseguenze

Paghiamo storage per GitLab e per il registry in South, banda di replica, un servizio di registry in South, il tempo che la pipeline di rilascio impiega a verificare la copia di South e aggiornamenti di Geo da eseguire in lockstep sulle due istanze.

In cambio, ritardo o corruzione di Geo non decidono più l'RTO della produzione, e l'ultima versione rilasciata di ogni applicazione di produzione è sempre presente in South.

Restano due rischi. Le modifiche già in merge ma non ancora rilasciate al momento T0 si perdono dallo stato di produzione; restano in Git solo se Geo le aveva già replicate. Anche la storia della CI non rilasciata può andare persa, com'è coerente con la semantica asincrona di Geo documentata.

## Validazione e trigger di revisione

| Test | Scenario | Condizione di superamento |
|---|---|---|
| T-13 | GitLab di Central perso durante l'isolamento del sito | I cluster DR riconciliano dal registry di South prima che Geo venga promosso. Geo viene poi promosso seguendo il runbook specifico della versione. Dopo la commutazione DNS sono utilizzabili repository, registry, runner, CI, stream di audit e sorgenti Git di Flux |
| T-13b | Secondario Geo reso indisponibile di proposito | Il ripristino della produzione riesce comunque dagli artifact OCI |

L'ADR va rivisto se cambiano l'architettura di riferimento di GitLab o le funzioni di Geo per la versione adottata, oppure se il cliente sceglie un prodotto diverso come registry degli artifact.
