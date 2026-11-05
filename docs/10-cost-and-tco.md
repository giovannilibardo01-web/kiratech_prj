# Costi del programma e TCO a tre anni dell'osservabilità

Questi numeri sono **scenari, non offerte**: non avevamo a disposizione prezzi dei vendor, tariffe del cliente o quotazioni hardware. Tutte le cifre escono da `python tools/capacity_model.py --full`, che applica alle quantità di [06](06-nfr-and-capacity.md) i costi unitari illustrativi riportati sotto. Prima di qualsiasi decisione di investimento quei costi unitari vanno sostituiti con le tariffe del cliente e con le proposte dei vendor. I valori sono espressi in migliaia di euro (k€) su 3 anni.

## 1. Assunzioni sui costi unitari (A-16)

| Parametro | Basso | Base | Alto | Copre |
|---|---:|---:|---:|---|
| € per vCPU-anno | 200 | 350 | 600 | Ammortamento dell'hardware, licenza dell'hypervisor, ~4 GiB di RAM per vCPU, energia e spazio |
| € per TiB utile-anno | 150 | 300 | 600 | Storage on-prem a oggetti o a blocchi, compreso l'overhead di protezione |
| Fattore storage fisico/logico | 2× | 2× | 2× | Scenario di erasure coding o di replica |
| Abbonamenti e appliance, € l'anno | 0 | 70k | 270k | Basso: solo OSS. Base: segnaposto per HSM/KMS e software di backup. Alto: base più un segnaposto per Grafana Enterprise (150k l'anno) ed eventuale supporto per broker o Backstage |
| Impegno incrementale di esercizio del cliente, FTE (SRE / Platform Eng. / Data Eng. / Network Sec.) | 4,0 (1,5 / 1,5 / 0,6 / 0,4) | 5,5 (2,1 / 2,0 / 0,8 / 0,6) | 7,5 (3,0 / 2,6 / 1,1 / 0,8) | Impegno a regime, applicato al 50% nel primo anno e al 100% negli anni 2–3. La quota SRE comprende l'impegno di osservabilità del §3 |
| Ingaggio Kiratech (mesi-persona su 18 mesi) | 60 | 80 | 110 | Architetto e ingegneri, Fasi 0–6 |
| Costo pieno per FTE-anno | 110k | 110k | 110k | Un'unica tariffa media per tutte le persone, per mantenere confrontabili gli ordini di grandezza. **Non è una tariffa commerciale Kiratech**: il prezzo dell'ingaggio è oggetto di una proposta commerciale separata |

Sono esclusi, perché esistono già oggi, il contratto GitLab Ultimate, l'istanza GitLab esistente e la capacità di produzione attuale di Central. Il calcolo riguarda quindi solo la piattaforma incrementale.

## 2. Costo complessivo del programma

| k€, 3 anni | Basso | **Base** | Alto |
|---|---:|---:|---:|
| Infrastruttura: compute (~1.410 vCPU incrementali, dettaglio sotto) | 847 | **1.482** | 2.541 |
| Infrastruttura: sovrapposizione della migrazione (una tantum, 112,5 vCPU-anno) | 22 | **39** | 68 |
| Infrastruttura: storage (205,5 TiB fisici) | 92 | **185** | 370 |
| Abbonamenti e appliance | 0 | **210** | 810 |
| Persone: esercizio del cliente | 1.100 | **1.512** | 2.062 |
| Persone: ingaggio Kiratech | 550 | **733** | 1.008 |
| **Totale** | **2.612** | **4.163** | **6.859** |

Il compute si distribuisce così (vCPU, uguali in tutti gli scenari):

| Voce | vCPU |
|---|---:|
| Riserva DR di South per la produzione | **540** |
| Control plane, 30 cluster | 360 (di cui 120 DR) |
| Non-produzione di South | 150 |
| LGTM: Central 86 + South dimensionato per il failover 94 | 180 |
| Incremento per GitLab HA + secondario Geo | 48 |
| Servizi abilitanti di South | 48 |
| Workload di gestione | 32 |
| Collector | 30 |
| Broker | 24 |

Lo storage si distribuisce così (TiB logici, ×2 fisici):

| Voce | TiB |
|---|---:|
| LGTM Central | 6,5 |
| South, compresa la copia di audit, al limite del failover | 15,6 |
| Archivio di audit di North | 4,1 |
| Broker e volumi locali | 1,5 |
| Copia GitLab Geo | 10 |
| Registry di South | 5 |
| Replica dei dati di produzione in South | 20 |
| Backup di produzione in North | 40 |

Per il CFO l'ordine di grandezza è di **circa 4,2 M€ in tre anni**, in un intervallo di 2,6–6,9 M€. Le persone valgono poco più della metà del caso base, l'infrastruttura circa il 41%.

La riserva DR è la decisione infrastrutturale più pesante: 540 vCPU valgono circa 570 k€ nel caso base. Questa voce scala con l'impronta *misurata* della produzione di Central, che è il primo deliverable della Fase 0. Scegliere un DR in pool invece dell'1:1 fa risparmiare solo circa 88 k€ nel caso base (84 vCPU di control plane), e un DR a tier circa 38 k€. La riserva di worker resta la stessa in ogni variante, ed è per questo che [ADR 0002](adr/0002-multi-site-topology.md) mantiene l'1:1.

Restano fuori dal calcolo, come voci di costo aperte, gli eventuali potenziamenti dei collegamenti tra siti se la banda misurata non basta (Q-05), le licenze dei database applicativi per le repliche DR, gli adeguamenti delle licenze VMware oltre la tariffa per vCPU e la tariffa commerciale di Kiratech.

## 3. TCO a tre anni dell'osservabilità: OSS contro supporto commerciale

L'infrastruttura viene dallo stesso modello: 204 vCPU per il compute LGTM di Central, per South dimensionato per il failover e per i broker; 27,7 TiB logici di storage (2× fisici) per LGTM, audit, broker e volumi locali.

L'impegno delle persone, ripartito per attività, è il seguente:

| Attività | FTE OSS | FTE supportato | Nota |
|---|---:|---:|---|
| Operatività e quota di reperibilità | 1,0 | 0,8 | Il supporto del vendor accorcia la risoluzione degli incidenti |
| Upgrade, capacità, matrice di supporto delle versioni | 0,5 | 0,3 | |
| Costruzione ed esercizio del query gateway (isolamento in lettura, [ADR 0012](adr/0012-telemetry-tenancy-and-read-isolation.md)) | 0,3 | 0,1 | LBAC Enterprise copre metriche e log; **Tempo richiede comunque il controllo tramite organizzazione e gateway** |
| Onboarding dei tenant, dashboard come codice | 0,3 | 0,3 | |
| **Totale** | **2,1** | **1,5** | |

Il TCO a tre anni risulta:

| k€, 3 anni | Basso | **Base** | Alto |
|---|---:|---:|---:|
| Infrastruttura | 147 | **264** | 467 |
| OSS: infrastruttura + 2,1 FTE | 840 | **957** | 1.160 |
| Supportato: infrastruttura + 1,5 FTE + abbonamento da 150 k€ l'anno (valore segnaposto) | 1.092 | **1.209** | 1.412 |
| Differenza (supportato − OSS) | +252 | **+252** | +252 |

A parità di infrastruttura, l'abbonamento dovrebbe costare al massimo (2,1 − 1,5) × 110 k€ = **66 k€ l'anno** perché le due opzioni si equivalgano.

La sensibilità rispetto all'organico OSS, con infrastruttura base, è questa:

| FTE OSS | 1,5 | 2,1 | 2,5 | 3,0 |
|---|---:|---:|---:|---:|
| TCO OSS a 3 anni (k€) | 759 | 957 | 1.089 | **1.254** |

Oltre circa 2,9 FTE l'OSS costa più dell'opzione supportata.

La decisione di [ADR 0009](adr/0009-commercial-support.md) resta provvisoriamente sull'OSS e verrà rivista con un'offerta reale e con l'impegno misurato nel pilota. Le incognite decisive sono l'impegno sul gateway e il carico di incidenti, non l'infrastruttura.

## 4. Controlli sui costi

Proponiamo una prima approvazione limitata: si finanziano solo la Fase 0, la Fase 0b e il pilota (Fase 1, composta soprattutto da persone), prima di acquistare storage, host per il broker o la riserva di South. Gli acquisti si fanno poi su input misurati, cioè serie attive, byte di log compressi, tasso di audit con la policy approvata e richieste della produzione di Central, e mai su tassi generici per pod.

Il perimetro non si riduce in silenzio. Se il CFO respinge la riserva di South, **l'RTO o il perimetro vanno rivisti formalmente con il CIO**, senza indebolire il progetto di nascosto.

Il controllo è continuo: ogni trimestre si confrontano budget e consuntivo con una soglia di scostamento del ±30%, si pubblicano dashboard dei costi di telemetria per tenant e si applica il chargeback ai volumi di segnale inattesi. Il supporto commerciale si acquista solo con evidenze, cioè se prezzo, SLA di supporto, supporto delle versioni e riduzione misurata dell'impegno lo giustificano, e l'isolamento di Tempo va contabilizzato a parte.
