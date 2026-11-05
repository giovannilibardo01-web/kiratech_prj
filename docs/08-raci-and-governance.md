# RACI e governance dell'architettura

## Colonne e convenzioni

Le colonne della matrice indicano i quattro team del cliente e Kiratech: PE è Platform Engineering, SRE è il team SRE, DE è Data Engineering, NS è Network Security e K è Kiratech. I quattro team sono usati così come esistono oggi, senza introdurne di nuovi.

Le lettere seguono la convenzione abituale: A è il responsabile (accountable), R esegue il lavoro, C viene consultato, I viene informato. Ogni riga ha **esattamente una A**, assegnata sempre a uno dei quattro team del cliente: Kiratech non è mai responsabile di un servizio del cliente. R\* indica che Kiratech esegue il lavoro durante l'ingaggio, insieme al team del cliente, e lo consegna entro la Fase 6; dopo il passaggio di consegne la cella diventa I.

Le autorità esecutive di approvazione (CISO, CIO, CFO) sono descritte a parte più sotto: approvano decisioni, ma non sono team di delivery.

## Matrice delle responsabilità

| Attività | PE | SRE | DE | NS | K |
|---|---|---|---|---|---|
| Progettazione dell'architettura e redazione degli ADR durante l'ingaggio | A | C | C | C | R |
| Provisioning e upgrade di vSphere e dei cluster (upgrade ring non-prod → DR → prod) | A/R | C | I | C | C |
| Template del catalogo e modifiche a pipeline GitLab e policy di sicurezza | A/R | C | C | C | R* |
| Deployment GitOps e baseline di configurazione (lockdown di Flux) | A/R | C | I | C | R* |
| Eccezioni alle policy: gestione tecnica (approvazione del delegato del CISO) | A/R | C | C | C | C |
| Admission control e produzione delle evidenze di conformità | A/R | C | I | C | C |
| Definizione degli SLO, ownership e instradamento degli alert | R | A/R | C | C | C |
| Costruzione, esercizio, capacità e quote per tenant di LGTM | R | A/R | C | C | R* |
| Registro dei tenant di telemetria e isolamento del percorso di lettura (query gateway) | C | A/R | I | C | R* |
| Coesistenza con il monitor black-box legacy e dismissione per singolo check | C | A/R | I | C | C |
| Object storage, broker e altri servizi di supporto (backing service) per i dati | C | C | A/R | C | C |
| Replica dei database di produzione e ripristino dei dati | C | C | A/R | C | C |
| Backup di cluster e applicazioni e drill di recovery | R | A/R | R | C | C |
| GitLab Geo, contratto di rilascio verso il registry di South e runner protetti | A/R | C | C | C | C |
| Firewall tra siti, DNS e flussi approvati | C | C | C | A/R | C |
| IdP, PKI, secret manager e HSM/KMS per sito (autonomia di South), owner secondo A-17 | C | C | I | A/R | C |
| Chiavi di firma delle immagini e custodia delle trust root, owner secondo A-17 | R | I | I | A/R | C |
| Esercizio della pipeline di audit e del doppio archivio immutabile (retention approvata dal CISO) | C | A/R | R | C | C |
| Dichiarazione di perdita del sito, fencing e incident command | R | A/R | R | R | C |
| Onboarding dei cluster esistenti e migration factory | A/R | R | R | C | R* |
| Promozione del golden path in produzione (milestone G) | A/R | C | C | C | R* |
| Costi, chargeback e previsione della capacità | C | A/R | C | I | C |
| Roadmap architetturale e standard dopo l'ingaggio | A/R | C | C | C | I |

## Autorità di approvazione (non team di delivery)

- Il CISO, o un delegato nominato, approva il modello delle eccezioni alle policy e le singole eccezioni (tramite la policy di approvazione delle merge request), la policy di audit di Kubernetes e il modello delle evidenze di audit (modalità di lock, seconda copia), la designazione dell'**amministratore della retention** (una persona nominata, esterna ai gruppi di amministrazione della piattaforma), le trust root di firma e la custodia delle chiavi, i custodi per il recupero dei secret e le regole di classificazione dei dati. Spetta al CISO anche accettare l'isolamento in lettura della telemetria sulla base delle evidenze di T-14 e rivedere ogni uso del break-glass.
- Il CIO approva il perimetro del DR e le eccezioni per singola applicazione sui cluster legacy, la delega dell'autorità di dichiarazione di disastro all'incident commander di SRE, il trattamento dei disastri dichiarati al di fuori dello SLO di disponibilità, qualsiasi suddivisione in tier di RTO/RPO e i rischi residui accettati (perdita di South, perdita di due siti).
- Il CFO approva il finanziamento limitato delle Fasi 0–1, l'acquisto della riserva di capacità di South e le decisioni sul supporto commerciale, da prendere su offerte reali.

## Compromessi in questo RACI

Per le eccezioni alle policy, Platform Engineering è responsabile del processo tecnico: il repository protetto, la scadenza e la conformità. Solo il delegato del CISO può approvare un'eccezione. In questo modo ogni riga mantiene una sola A senza inventare un team di sicurezza.

Sull'audit, SRE risponde dell'esercizio della pipeline delle evidenze e Data Engineering del servizio di storage. Le impostazioni di retention sono approvate dal CISO e amministrate dall'amministratore della retention designato. Nell'ADR il responsabile della decisione sul modello delle evidenze è il CISO ([ADR 0010](adr/0010-audit-evidence-and-retention.md)).

Per l'infrastruttura di sicurezza, le descrizioni dei team non indicano un owner per identità, PKI, secret manager, HSM/KMS o chiavi di firma. Abbiamo assegnato Network Security **per assunzione** (A-17, Q-18); l'alternativa è Platform Engineering come owner, con Network Security consultato. In entrambi i casi approva il CISO.

Per i servizi di supporto, nessuno dei quattro team è un team di storage. Object storage e broker sono quindi assegnati a Data Engineering, in quanto infrastruttura dati, anche qui per assunzione (A-03), da confermare rispetto ai mandati effettivi dei team del cliente.

## Governance delle decisioni dopo l'uscita di Kiratech

Dopo l'ingaggio le decisioni architetturali passano a un Architecture Review Board del cliente, composto da rappresentanti dei team esistenti (non da un team riorganizzato), che si riunisce ogni due settimane. Lo presiede Platform Engineering, che tiene anche il registro delle decisioni; SRE, Data Engineering e Network Security esaminano obbligatoriamente ogni modifica che tocca il loro dominio.

Ogni modifica rilevante è una merge request GitLab che porta con sé il modello e le viste aggiornati, l'ADR (`Proposed → Accepted → Superseded`), le implicazioni su minacce, DR e costi, il piano di test con il rollback e le righe del RACI interessate. I trigger di revisione registrati in ogni ADR vengono confrontati ogni mese con i dati misurati (scostamenti di capacità, tempi dei drill, offerte); quando un trigger scatta, si apre un ADR che sostituisce il precedente.

I veti sono meccanismi di passaggio di fase, non un trasferimento dell'autorità di progetto. Il CISO, tramite il suo delegato, ha un veto di sicurezza su eccezioni ai controlli, residenza dei dati, connettività privilegiata e immutabilità; SRE ha un veto sulla disponibilità non dimostrata o sull'error budget; Data Engineering ha un veto sul recupero dei dati non testato.

Le modifiche in break-glass usano un'eccezione documentata e di breve durata, con doppia approvazione, seguita entro due giorni lavorativi da un ADR retrospettivo.

Ogni mese si rivedono il drift architetturale e il registro dei rischi; ogni trimestre si tiene un'esercitazione di disastro e si producono i report sui costi e sugli SLO degli alert.

Al passaggio di consegne Kiratech consegna runbook, evidenze di audit, decisioni registrate, il modello di capacità e costi, la formazione e i rischi aperti. Le approvazioni correnti restano agli owner del cliente.
