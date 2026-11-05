# Contratto di integrazione per i due workstream Kiratech in corso

## A. Applicazione di riferimento a tre livelli: LGTM single-cluster in carico a un ingegnere

Dell'applicazione esistente manteniamo la separazione tra presentazione, applicazione e dati, il riferimento Prometheus/Loki/Grafana/Alloy per metriche, log e dashboard, l'ownership e il metodo di deployment attuali per tutta la durata del pilota, e la strumentazione e le dashboard di base che già funzionano.

Cambiano invece la strumentazione e la destinazione dei dati. L'applicazione adotta il trace context di OpenTelemetry, con label coerenti per servizio, sito, ambiente e owner e con la redazione dei dati sensibili. Una volta testata la nuova configurazione, la raccolta dei dati di piattaforma passa ad Alloy locale al sito e ai backend Mimir/Loki/Tempo; il Prometheus locale resta solo per scrape tattici o per valutare regole dove serve. Le definizioni delle dashboard e i metadati di rilascio passano in gestione GitOps, e gli alert applicativi diventano SLO di servizio con il relativo instradamento. La retention del Loki locale dell'applicazione non va scambiata per l'impegno di retention aziendale.

Per l'accettazione serve una demo che navighi da un guasto web sintetico allo SLO sulla metrica, al log corrispondente già sanificato, all'ID della trace e allo SHA del deployment in GitLab, con un owner dell'alert documentato. La demo deve anche mostrare che disattivare il collector locale della demo non causa interruzioni in produzione.

## B. Golden path self-service di South: in carico a un ingegnere senior

Del golden path manteniamo la scansione, la SBOM e la firma in GitLab CI, l'RBAC basato su namespace, le quote, la policy default-deny, i Pod Security Standards, un policy engine, i secret esterni e la definizione dichiarativa dell'ambiente. Sono asset centrali, **non** prototipi da buttare.

Il golden path diventa un template del catalogo dei servizi di Backstage, con un contratto di MR e approvazione in GitLab. Richiede conformità alle policy e metadati di owner e di costo, e aggiunge TTL e teardown, approvazioni granulari dell'egress, registrazione nell'osservabilità di piattaforma e archivio delle evidenze. I secret esterni vanno validati come valori che non vengono mai committati in Git. L'output del namespace va normalizzato come artefatto di riconciliazione Flux, e i template di Backstage non devono contenere credenziali.

Il golden path non viene promosso in produzione così com'è. Per arrivarci deve superare anche la classificazione di cluster e di multi-tenancy, l'autorizzazione delle modifiche, l'iscrizione a backup e DR, la policy sui dati e i controlli di separazione dei compiti. Il golden path di produzione riusa template e scansioni, ma non il privilegio di creazione non presidiata degli ambienti dev/test. La promozione è la milestone G della roadmap ([07](07-roadmap.md)): i primi 3 servizi di produzione passano dal template di produzione firmato con zero eccezioni alle policy e sono inclusi in un drill DR.

Se il golden path esistente usa un policy engine diverso da Kyverno, la piattaforma si allinea a quello nella revisione di Fase 0, invece di far girare due engine ([ADR 0001](adr/0001-platform-toolchain.md)).

Il contratto di richiesta, cioè l'input del template, fissa tre regole. Lo schema impone che `ttlDays` non superi 30 per gli ambienti dev e 90 per quelli test; `dataClassification` è limitato a `public` e `internal`; le destinazioni di egress sono opzionali e, se indicate, rendono la richiesta soggetta ad approvazione.

## Piano di integrazione tra i workstream

| Finestra | Attività congiunta | Responsabili |
|---|---|---|
| Settimane 1–2 | Revisione delle due implementazioni e accordo sui contratti per label, percorsi GitLab, identità dei tenant, secret ed evidenze di policy | Architetto Kiratech + i due ingegneri |
| Settimane 3–6 | L'applicazione di riferimento invia tutti e 3 i segnali all'LGTM del sito pilota; il golden path emette i metadati di owner per la telemetria | Ingegnere dell'applicazione di riferimento + SRE |
| Settimane 6–10 | Il golden path dimostra un ambiente conforme in South usando il template del catalogo, con CI protetta e Flux | Ingegnere di South + Platform Engineering |
| Mesi 3–5 | I due workstream confluiscono in un'unica baseline C4/ADR e negli stessi test di accettazione; nessuno stack di vendor concorrente in parallelo | Architetto Kiratech + governance del cliente |

Il principio di controllo delle modifiche è conservare i prototipi funzionanti come asset di validazione finché la sostituzione enterprise non si è dimostrata valida, e non sostituire mai contemporaneamente, in un ambiente attivo, raccolta, deployment e policy di admission.
