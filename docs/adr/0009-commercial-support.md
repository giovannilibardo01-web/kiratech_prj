# ADR 0009: supporto commerciale per l'osservabilità

- Stato: proposta, in attesa della revisione di progetto con il cliente e dell'offerta del vendor
- Data: 2026-11-05
- Decisori: SRE, per l'esercizio
- Revisori: CFO, che approva la spesa, e CISO, che approva le evidenze di isolamento in lettura; Platform Engineering, consultato

## Contesto

Si parte dall'open source: un abbonamento a pagamento deve ripagare quello che costa. Lo stack di osservabilità è basato su Grafana per scelta del cliente, e software e dati restano nei suoi data center.

Il confronto tra le edizioni non si riduce al prezzo, perché cambiano anche le funzioni. In Grafana OSS i permessi sulle data source non esistono, quindi l'isolamento in lettura richiede un'organizzazione per team più un query gateway ([ADR 0012](0012-telemetry-tenancy-and-read-isolation.md)). Grafana Enterprise con GEM/GEL aggiunge i permessi sulle data source e il controllo d'accesso basato su label (LBAC) per metriche e log. LBAC però **non copre Tempo self-hosted**: un controllo di isolamento per le trace serve in entrambe le edizioni.

## Opzioni considerate

- A, tutto OSS con personale interno. Non c'è abbonamento, ma la costruzione e l'esercizio del query gateway restano a carico del cliente e pesano sulle FTE.
- B, abbonamenti Grafana Enterprise e GEM/GEL per i componenti on-prem supportati. Portano il supporto del vendor e l'isolamento a livello di label per metriche e log, al prezzo della sottoscrizione; per le trace servono comunque un gateway o la separazione per organizzazione.
- C, Grafana Cloud gestito o in SaaS. Viola il vincolo di residenza on-prem dei dati ed è scartata.

## Decisione

Per il pilota, che ha una durata limitata, scegliamo in via provvisoria l'opzione A. Prima del rollout in produzione serve una verifica di prezzo commerciale.

Perché il confronto regga, le due opzioni vanno misurate sullo stesso perimetro: un orizzonte di 3 anni, un costo delle FTE che per l'opzione A comprenda l'effort di costruzione ed esercizio del query gateway, lo SLA del vendor e i volumi di storage di [06](../06-nfr-and-capacity.md).

Il modello in [10](../10-cost-and-tco.md) §3, nello scenario base e senza offerte reali, dà questi valori:

| | Infrastruttura | Persone | Abbonamento | Totale a 3 anni |
|---|---|---|---|---|
| OSS | 264 k€ (dal modello di capacità) | 2,1 FTE, compreso l'effort del query gateway | nessuno | **957 k€** |
| Supportato | 264 k€ | 1,5 FTE | 150 k€/anno (segnaposto) | **1.209 k€** |

L'abbonamento porta i due scenari in pareggio se costa al massimo 66 k€/anno, che è quindi la soglia di break-even per un'offerta reale. Sul fronte del personale il crossover è intorno a 2,9 FTE: oltre quella soglia, l'OSS costa più dell'opzione supportata.

## Conseguenze

Il rischio della scelta OSS sta nel personale. L'autosupporto può richiedere più FTE e più competenze di reperibilità di quanto stimato, e il calcolo del break-even in [10](../10-cost-and-tco.md) mostra quanto la decisione sia sensibile a questo fattore.

Il SaaS resta escluso per la residenza dei dati. Passare a Enterprise in un secondo momento non elimina il controllo di isolamento delle trace, né il disegno a organizzazioni e gateway per Tempo.

## Validazione e trigger di revisione

La decisione si riapre quando arriva un'offerta del vendor, quando il pilota misura l'effort operativo reale, se l'effort del gateway supera il break-even dell'abbonamento o se il CISO rende obbligatorio l'isolamento a livello di label. In ciascun caso si registra un ADR che sostituisce questo, invece di modificare senza traccia la decisione storica.
