# Sintesi decisionale per CIO, CISO e CFO

Chiediamo di approvare una piattaforma interna per sviluppatori su tre siti che parte dall'osservabilità e applica le policy per costruzione, e di finanziarne una **prima fase delimitata** (discovery, bootstrap minimo e pilota) prima di qualsiasi acquisto di storage, broker o riserva DR.

## Perché cambiare

Oggi la piattaforma ha tre problemi: il monitoraggio si limita ai check ping/HTTP di uno strumento legacy e non esiste elaborazione dei log; i cluster Kubernetes sono costruiti a mano, senza una baseline comune; c'è un'unica istanza GitLab, in Central. Di conseguenza i team non possono creare da soli i propri ambienti con costi controllati, sicurezza verificabile e alert di cui fidarsi.

## Che cosa si costruisce, e in quale ordine

1. Prima l'osservabilità. Grafana LGTM per sito in Central e South, creato come codice; la produzione esistente osservata in sola lettura; isolamento dei tenant in scrittura e in lettura; alert legati agli SLO e instradati ai quattro team; un doppio archivio di audit immutabile (una copia in North e una in South), conservato per almeno un anno. Il monitor legacy resta in funzione finché i suoi check non sono replicati, uno per uno.
2. Poi il self-service sicuro: Backstage → GitLab Ultimate (security policy non aggirabili) → OpenTofu + Cluster API → Flux, con policy di admission, immagini firmate e secret esterni. I team non possono indebolire la baseline.
3. Infine la resilienza, prima della migrazione. South esegue in proprio identità, PKI, secret, DNS, vCenter e registry, e ospita controparti DR calde 1:1 della produzione con una riserva di capacità. I dati sono replicati in continuo, quindi durante un disastro non va ripristinato nulla. La produzione passa ai cluster gestiti solo coorte per coorte, quando questa protezione è in funzione.

| Mesi | Risultato |
|---|---|
| 0–2 | Inventario, decisioni, acquisti; i cluster di osservabilità si possono creare da codice |
| 1–6 | Pilota, poi osservabilità per sito; produzione esistente visibile; archivio di audit dimostrato |
| 5–8 | Self-service conforme in South; i tentativi di escalation vengono negati |
| 6–10 | Fondamenta del recupero in South; dimostrato che South funziona con Central scollegato |
| 9–15 | Cluster esistenti migrati con le controparti DR: 50% della produzione entro il mese 12, 100% o eccezioni firmate entro il mese 15. Golden path promosso in produzione nei mesi 11–13 |
| 15–18 | Drill di perdita di Central sull'intero inventario, poi l'impegno su RPO/RTO; 30 cluster / 1.500 pod entro gli SLO; passaggio di consegne |

## Quanto costa: circa 4,2 M€ in 3 anni (intervallo da 2,6 M€ a 6,9 M€)

Le cifre sono illustrative, non quotazioni.

| 3 anni | Basso | Base | Alto |
|---|---:|---:|---:|
| Infrastruttura (~1.410 vCPU, ~206 TiB fisici, sovrapposizione durante la migrazione) | 0,96 M€ | 1,71 M€ | 2,98 M€ |
| Abbonamenti e appliance | 0,00 M€ | 0,21 M€ | 0,81 M€ |
| Persone: impegno operativo del cliente + ingaggio Kiratech | 1,65 M€ | 2,25 M€ | 3,07 M€ |
| Totale del programma (calcolato prima degli arrotondamenti) | 2,61 M€ | **4,16 M€** | 6,86 M€ |

La voce infrastrutturale più grande è la riserva DR in South, circa 0,57 M€ nel caso base, che cresce con l'impronta di produzione *misurata*. Rispetto all'1:1, il DR condiviso (pooled) farebbe risparmiare solo circa 0,09 M€ e il DR a livelli (tiered) circa 0,04 M€. Per la sola osservabilità il confronto è tra 0,96 M€ in OSS e 1,21 M€ con supporto commerciale (abbonamento segnaposto): l'OSS resta preferibile a meno che una quotazione non scenda sotto 66 k€/anno o che il personale necessario per l'OSS superi circa 2,9 FTE. Sono esclusi il contratto GitLab esistente, la capacità di produzione esistente e la tariffa commerciale di Kiratech; il dettaglio è in [10](10-cost-and-tco.md).

## Rischi principali

1. Il recupero in quattro ore è un progetto condizionato. Il percorso è modellato in 175 minuti, 235 con l'attesa delimitata, e non è stato misurato. Regge solo se la riserva in South è finanziata, se South esegue in proprio i servizi abilitanti e se ogni dataset in perimetro è replicato.
2. Le evidenze e la fonte di verità dipendono da due verifiche. La semantica di immutabilità dell'archivio di audit va verificata sul prodotto di storage scelto; GitLab Geo è asincrono, quindi il DR della produzione si appoggia alle release già copiate in South.
3. Il carico operativo è di circa 5,5 FTE nel caso base: SRE 2,1, Platform Engineering 2,0, Data Engineering 0,8 e Network Security 0,6.

## Decisioni richieste

- Al CIO chiediamo di decidere il perimetro di recupero e le eccezioni per i cluster legacy, la delega del potere di dichiarare il disastro e il trattamento dei disastri dichiarati al di fuori dello SLO di disponibilità.
- Al CISO chiediamo di approvare il modello delle evidenze di audit, le root of trust per la firma, l'autorità sulle eccezioni e l'accettazione dell'isolamento in lettura, e di stabilire chi è owner di identità, PKI e secret (A-17).
- Al CFO chiediamo il finanziamento della prima fase delimitata, la riserva in South dimensionata sulle richieste di produzione misurate e quotazioni reali prima della decisione sul supporto commerciale.

Il go/no-go si fonda su due condizioni. Nessuna coorte di produzione si sposta prima che South abbia dimostrato di funzionare con Central scollegato e che la controparte DR della coorte sia pronta. **Nessun impegno su RPO/RTO viene preso verso il business** finché un drill di perdita di Central sull'intero inventario non rispetta RPO ≤1 h e RTO ≤4 h.
