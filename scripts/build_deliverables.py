#!/usr/bin/env python3
"""Export the two page-constrained deliverables with ReportLab (pip install reportlab).

Every number is read from tools/capacity_model.py so the PDFs cannot drift from the model;
wording is a concise rendering of docs/00 and docs/06. Outputs are proposal documents,
not evidence of implementation.
"""
from pathlib import Path
import sys
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle, PageBreak
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'tools'))
sys.dont_write_bytecode = True
from capacity_model import (Assumptions, SizingAssumptions, SCENARIOS, calculate, site_sizing, fleet,  # noqa: E402
                            programme_cost, observability_tco, dr_summary)

OUT = ROOT/'deliverables'; OUT.mkdir(exist_ok=True)
FONTS = [('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'),
         ('C:/Windows/Fonts/arial.ttf', 'C:/Windows/Fonts/arialbd.ttf')]
font, bold = 'Helvetica', 'Helvetica-Bold'
for regular, heavy in FONTS:
    if Path(regular).exists() and Path(heavy).exists():
        pdfmetrics.registerFont(TTFont('Body', regular)); pdfmetrics.registerFont(TTFont('Body-Bold', heavy))
        font, bold = 'Body', 'Body-Bold'; break

NAVY = HexColor('#172C44'); TEAL = HexColor('#157D89'); GRAY = HexColor('#516273')
S = {
 'title': ParagraphStyle('t', fontName=bold, fontSize=16, leading=19, textColor=NAVY, spaceAfter=3),
 'subtitle': ParagraphStyle('s', fontName=font, fontSize=8.6, leading=11, textColor=GRAY, spaceAfter=6),
 'h2': ParagraphStyle('h', fontName=bold, fontSize=10.2, leading=12.5, textColor=TEAL, spaceBefore=6, spaceAfter=3.5),
 'body': ParagraphStyle('b', fontName=font, fontSize=8.0, leading=11.0, textColor=NAVY, spaceAfter=3.5),
 'small': ParagraphStyle('sm', fontName=font, fontSize=7.0, leading=9.2, textColor=NAVY, spaceAfter=2),
 'table': ParagraphStyle('tb', fontName=font, fontSize=6.9, leading=9.0, textColor=NAVY),
 'tablehead': ParagraphStyle('th', fontName=bold, fontSize=6.9, leading=9.0, textColor=colors.white),
 'call': ParagraphStyle('c', fontName=bold, fontSize=7.8, leading=10.4, textColor=NAVY),
}
def P(t, k='body'): return Paragraph(t, S[k])
def heading(text): return P(text, 'h2')
def table(rows, widths, header=True, pad=3.0):
    grid = [[P(str(v), 'tablehead' if header and ri == 0 else 'table') for v in row] for ri, row in enumerate(rows)]
    t = Table(grid, colWidths=widths, hAlign='LEFT', repeatRows=1 if header else 0)
    style = [('VALIGN', (0, 0), (-1, -1), 'TOP'), ('LEFTPADDING', (0, 0), (-1, -1), pad), ('RIGHTPADDING', (0, 0), (-1, -1), pad),
             ('TOPPADDING', (0, 0), (-1, -1), pad), ('BOTTOMPADDING', (0, 0), (-1, -1), pad),
             ('GRID', (0, 0), (-1, -1), 0.3, HexColor('#DBE2E7')), ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, HexColor('#F7F9FB')])]
    if header: style += [('BACKGROUND', (0, 0), (-1, 0), NAVY)]
    t.setStyle(TableStyle(style)); return t

def footer(canvas, doc):
    canvas.saveState(); w, h = A4
    canvas.setStrokeColor(TEAL); canvas.setLineWidth(0.6); canvas.line(36, h-34, w-36, h-34)
    canvas.setFont(font, 6.8); canvas.setFillColor(GRAY)
    canvas.drawString(36, 22, 'PIATTAFORMA IDP SU TRE SITI  |  PROPOSTA DI ARCHITETTURA, NON VALIDATA IN PRODUZIONE  |  numeri: tools/capacity_model.py --full')
    canvas.drawRightString(w-36, 22, f'2026-11-05  ·  {doc.page}')
    canvas.restoreState()

def build(path, title, story):
    d = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=36, rightMargin=36, topMargin=42, bottomMargin=36,
                          title=title, author='Proposta di architettura')
    d.build(story, onFirstPage=footer, onLaterPages=footer)

# ------------------------------------------------------------------ number formatting (dot for thousands, comma for decimals)
def fmt(x, spec='g'):
    return format(x, spec).replace(',', '_').replace('.', ',').replace('_', '.')
def n0(x): return fmt(x, ',')
def m1(keur): return f'{fmt(keur/1000, ".1f")} M€'
def m2(keur): return f'{fmt(keur/1000, ".2f")} M€'
def vg(t): return f'{fmt(t[0], ",g")} vCPU / {fmt(t[1], ",g")} GiB'
def pct(x): return f'{x*100:.0f}%'

# ------------------------------------------------------------------ numbers from the model
A, SZ = Assumptions(), SizingAssumptions()
V = calculate(A); SITES = site_sizing(A, SZ); FL = fleet(A, SZ); DR = dr_summary()
PC = {k: programme_cost(A, SZ, c) for k, c in SCENARIOS.items()}
BASE = SCENARIOS['base']
TCO = observability_tco(A, SZ, BASE)
st = SITES['storage_logical']; ph = SITES['storage_physical_scenarios']; sh = SITES['shares_central']
c, sn, sf = SITES['central'], SITES['south_normal'], SITES['south_after_failover']
W = A4[0]-72
raw_capacity_gb = round(V['metric_capacity_13mo_logical_gb']/A.provision_headroom, 1)
reserve_keur = FL['south_dr_reserve_vcpu_gib'][0]*BASE.eur_per_vcpu_year*3/1000
pooled_keur = FL['pooled_dr_variant_saving_vcpu_gib'][0]*BASE.eur_per_vcpu_year*3/1000
tiered_keur = FL['tiered_dr_variant_saving_vcpu_gib'][0]*BASE.eur_per_vcpu_year*3/1000
fte = BASE.run_fte_by_team
def cores(s): return f'{fmt(s["mimir_distributor_cores"])} ({fmt(s["burst_3x_distributor_cores"])}) / {fmt(s["mimir_ingester_cores"])}'
def broker(s): b = s['broker']; return f'{fmt(b["write_mb_per_s"])} ({fmt(b["burst_3x_write_mb_per_s"])}) MB/s; ~{fmt(b["disk_per_broker_gb_2x_headroom"])} GB'
def phys(site): return [fmt(ph[k][site], '.1f') for k in ('x1.5', 'x2.0', 'x3.0')]

# ------------------------------------------------------------------ NFR & capacity note (3 pages)
n = [P('Nota NFR e capacità', 'title'), P('Piattaforma interna per sviluppatori su tre siti · obiettivi misurabili · pagina 1/3', 'subtitle'),
     heading('1. Obiettivi di accettazione misurabili')]
n.append(table([
 ['Obiettivo', 'Target di accettazione ed evidenza'],
 ['Disponibilità della piattaforma', 'SLI ≥99,9% per catalogo, GitOps e osservabilità, misurato su un <b>trimestre di orario lavorativo</b> (assunto 08–18, 660 h, quindi 39,6 minuti di budget) e riportato ogni mese. In più, al massimo un\'interruzione non pianificata per trimestre, cioè almeno 5 minuti lavorativi consecutivi sotto soglia fuori dalle finestre di manutenzione. Sono due vincoli indipendenti. I disastri di sito dichiarati seguono RPO e RTO (proposta per il CIO).'],
 ['Disponibilità della produzione (proposta)', 'API dei cluster di produzione, ingress e admission ≥99,95% al mese, misurati 24×7. Gli alert che toccano la produzione chiamano il reperibile 24×7; gli SLO applicativi li fissano gli owner dei servizi partendo dai template di piattaforma.'],
 ['Recovery', f'Perdita di Central: RPO ≤60 min e RTO ≤240 min dopo dichiarazione e fencing, per tutta la produzione inventariata sui cluster gestiti e per il control plane della piattaforma. Path progettato di <b>{DR["designed_min"]} minuti (modellato)</b>, {DR["declare_after_60min_wait_min"]} se si attende al massimo 60 minuti un ripristino di Central. Nessun restore sul percorso critico; le applicazioni ancora su cluster legacy restano sotto eccezioni firmate dal CIO fino alla migrazione. Prima dell\'impegno, drill su tutto l\'inventario.'],
 ['Self-service', 'Namespace pronto in p95 ≤15 minuti dopo l\'approvazione, anche con almeno 20 richieste concorrenti; onboarding di un team in ≤1 giorno lavorativo; ≥99% delle richieste senza intervento manuale; zero risorse orfane dopo il teardown; TTL ≤30 giorni per dev e ≤90 per test, imposto dallo schema.'],
 ['Sicurezza', '100% delle risorse di produzione controllate da admission in modalità enforce. I tenant non possono ottenere diritti di cluster via GitOps, togliere controlli dalla CI o approvarsi eccezioni (test negativi T-02, T-04, T-05, T-14). Nessun secret in Git, nemmeno cifrato; nessun valore segreto nello stato OpenTofu.'],
 ['Audit', 'Almeno 365 giorni con una policy di 400, <b>archivio immutabile duale</b> (North più una copia in South, compliance mode, amministrazione separata), ritardo di archiviazione ≤5 minuti, recupero ≤4 h, verifica d\'integrità giornaliera, rifiuto della cancellazione verificato alla presenza del CISO.'],
 ['Retention', 'Metriche 30 giorni a piena risoluzione; 13 mesi per circa 40.000 serie di capacity, prodotte da recording rule federate perché Mimir non fa downsampling; log 30 giorni; trace 7 giorni. Vale per ogni tenant, quarantine compreso.'],
 ['Qualità degli alert', '≥95% delle page richiede un intervento, ≤2 falsi allarmi a settimana per team, 100% delle route critiche provate ogni trimestre; dead-man\'s switch nell\'altro sito; freschezza ≤2 minuti per il 99,9% dei campioni SLO.'],
 ['Scala', '30 cluster e 1.500 pod entro 18 mesi; burst di ingest 3× nel pilota; scostamento dalla previsione entro ±30%, verificato ogni mese.'],
], [W*.19, W*.81]))
n += [heading('2. Condizioni da tenere presenti'),
      P(f'Sono NFR proposti, non misure. L\'RTO di 4 ore regge solo se la riserva in South è finanziata, se South ha già identità, PKI, secret, DNS, vCenter e registry propri, se ogni dataset in perimetro è replicato in continuo e se il fencing è verificato. Un RTT di 10–20 ms non dice nulla sulla banda: ripristinare 1 TiB a 1 Gbps con un\'efficienza del 70% richiede {fmt(DR["transfer_1tib_hours"]["1gbps"])} h, ed è per questo che i restore restano fuori dal percorso critico.'),
      P('La conformità dell\'audit si dimostra con un rifiuto di cancellazione verificato e con un recupero indipendente, non con un valore di retention su una dashboard. La semantica dei prodotti (Object Lock, broker, organizzazioni Grafana) va verificata sulle versioni adottate prima dell\'acquisto.'),
      PageBreak(),
      P('Nota NFR e capacità', 'title'), P('Volumi di telemetria e storage per sito · pagina 2/3', 'subtitle'),
      heading('3. Volumi di telemetria (intera flotta, modellati)'),
      P(f'Per le metriche: 1.500 pod × 250 + 30 cluster × 10.000 = 675.000 serie, che con il 50% di margine diventano <b>{n0(V["active_series"])} serie attive</b>; con lo scrape a 15 secondi sono <b>{n0(V["samples_per_second"])} campioni/s</b>. Il tier grezzo a 30 giorni vale 2,5 B per campione × 1,5 di overhead × 1,5 di margine, cioè {fmt(V["metric_raw_30d_logical_tb"])} TB logici.'),
      P(f'Il tier di capacity tiene 40.000 serie ogni 300 secondi per 395 giorni: 4,55 miliardi di campioni × 3 B × 2 = {fmt(raw_capacity_gb)} GB, che con il margine di 1,5× diventano {fmt(V["metric_capacity_13mo_logical_gb"])} GB, il valore usato in tutti i totali (la quota del bucket è arrotondata a 50 GB).'),
      P(f'Per i log: 1.500 × 0,28 GiB + 80 GiB = {fmt(V["logs_uncompressed_gib_per_day"])} GiB al giorno non compressi; × 0,35 di compressione × 1,3 di overhead × 30 giorni × 1,5 = {fmt(V["loki_30d_provisioned_tib"], ".1f")} TiB.'),
      P(f'Per l\'audit: 20 GiB al giorno × 0,35 × 400 giorni × 1,5 = {fmt(V["north_audit_400d_provisioned_tib"])} TiB per copia, una in North e una in South. Per le trace: {n0(V["trace_retained_spans_per_second"])} span conservati al secondo × 700 B × 7 giorni × 1,5 = {fmt(V["tempo_7d_provisioned_tb"])} TB.'),
      heading('4. Storage per sito (TiB logici e scenari fisici)'),
      P(f'La quota di Central si ricava da dove girano i 12 + 18 cluster e i 900 + 600 pod: {pct(sh["metrics"])} delle metriche, {pct(sh["logs"])} dei log, {pct(sh["traces"])} delle trace.', 'small'),
      table([['Sito', 'Logico', '×1,5', '×2', '×3', 'Contenuto'],
             ['Central', fmt(st['central_logical_tib']), *phys('central_logical_tib'), 'Quota Central della telemetria operativa e tier di capacity'],
             ['South (normale)', fmt(st['south_normal_logical_tib']), *phys('south_normal_logical_tib'), 'Quota South, seconda copia dell\'audit e copia della capacity di Central'],
             ['South (30 giorni dopo il failover, limite superiore)', fmt(st['south_after_failover_upper_bound_tib']), *phys('south_after_failover_upper_bound_tib'), 'Tutta la telemetria operativa più la copia dell\'audit; cresce da zero dopo lo switch'],
             ['North', fmt(st['north_audit_logical_tib']), *phys('north_audit_logical_tib'), 'Archivio di audit; i backup di produzione sono a parte (§6)']],
            [W*.24, W*.08, W*.08, W*.07, W*.07, W*.46]),
      P('I moltiplicatori sono scenari di erasure coding o di replica, non dati di vendor. Dischi del broker e volumi locali, copia Geo di GitLab, registry South e dati di produzione sono dimensionati e costati a parte (§6). È escluso lo spazio temporaneo per i restore.', 'small'),
      P('Da validare nel pilota: serie per pod e per cluster, byte di log compressi, span dopo il sampling, tasso di eventi di audit con la policy approvata dal CISO, byte per campione sul broker e la collocazione dei workload da cui derivano le quote per sito. Uno scostamento oltre il ±30% richiede una nuova previsione prima dell\'acquisto.'),
      PageBreak(),
      P('Nota NFR e capacità', 'title'), P('Compute, riserva DR e validazione · pagina 3/3', 'subtitle'),
      heading('5. Compute per sito (modellato)'),
      P('Il percorso di scrittura di Mimir segue le guide di capacità Grafana: un distributor ha 1 core e 1 GB ogni 25.000 campioni/s; un ingester 1 core, 2,5 GB di RAM e 5 GB di disco ogni 300.000 serie in memoria (RF 3), valori prudenti. Loki è al tier più piccolo della tabella di dimensionamento Grafana (p90). Gli altri componenti hanno quote fisse per sito; il relay di audit, che gira nel management cluster, è contato nel dimensionamento del sito.', 'small'),
      table([['Componente', f'Central ({pct(sh["metrics"])} delle metriche)', f'South normale ({pct(1-sh["metrics"])})', 'South dopo il failover (100%)'],
             ['Mimir: distributor (burst ×3) / ingester, in core', cores(c), cores(sn), cores(sf)],
             ['Totale LGTM', vg(c['lgtm_vcpu_gib']), vg(sn['lgtm_vcpu_gib']), vg(sf['lgtm_vcpu_gib'])],
             ['LGTM con il 25% di margine per la perdita di un nodo', f'<b>{vg(c["lgtm_with_ha_headroom_vcpu_gib"])}</b>', vg(sn['lgtm_with_ha_headroom_vcpu_gib']), f'<b>{vg(sf["lgtm_with_ha_headroom_vcpu_gib"])}</b>'],
             ['Broker a 3 nodi (Data Engineering): scrittura (×3) e disco per broker', broker(c), broker(sn), broker(sf)]],
            [W*.28, W*.25, W*.21, W*.26]),
      P('South è dimensionato sulla colonna del failover, perché la produzione recuperata emette la sua telemetria in South.', 'small'),
      heading('6. Overhead della flotta e riserva DR (voci del costo di programma)'),
      table([['Voce', 'Dimensionamento', 'Base di calcolo'],
             ['Control plane dei 30 cluster', vg(FL['control_planes_30_clusters_vcpu_gib']), f'3 VM × 4 vCPU / 16 GiB per cluster. I 10 cluster DR valgono {vg(FL["of_which_10_dr_control_planes"])}; il DR tiered farebbe risparmiare {vg(FL["tiered_dr_variant_saving_vcpu_gib"])}, il pooled {vg(FL["pooled_dr_variant_saving_vcpu_gib"])}'],
             ['Riserva DR in South', f'<b>{vg(FL["south_dr_reserve_vcpu_gib"])}</b>', '900 pod di produzione × 0,5 vCPU / 1 GiB × 1,2, da sostituire con le richieste misurate in Central; è un vincolo di finanziamento'],
             ['Servizi abilitanti in South; GitLab HA e Geo', f'{vg(FL["south_enabling_services_vcpu_gib"])}; {vg(FL["gitlab_ha_increment_and_geo_secondary_vcpu_gib"])}', 'IdP, CA, secret manager, DNS, registry, vCenter; incremento HA di GitLab e secondario Geo (copia di 10 TiB, registry South di 5 TiB)'],
             ['Overlap di migrazione (una tantum)', f'{fmt(FL["migration_overlap_vcpu_years"])} vCPU-anno', '25% delle richieste di produzione su cluster legacy e nuovi per circa un anno'],
             ['Dati di produzione', '20 TiB replicati in South; 40 TiB di backup in North (logici)', 'Assunzione, in attesa dell\'inventario di Data Engineering']],
            [W*.24, W*.33, W*.43]),
      heading('7. Validazione e controllo delle previsioni'),
      P('Nelle settimane 1–4 del pilota (Fase 1, dopo la discovery di Fase 0) si misurano cardinalità, byte compressi, span, tasso di audit, payload del broker, carico di query e banda dei link. Nelle settimane 4–8 si sostiene un ingest 3× per almeno 30 minuti, si spengono un ingester, il broker e l\'endpoint di object storage, e si misurano replay del WAL, p99 delle query e tempo di allerta. Nei mesi 3–5 si ricava il costo di retention per tenant dai blocchi reali, con una fixture di retention a 35 giorni e la prova del rifiuto di cancellazione WORM. Ogni mese previsione e consuntivo devono restare entro il ±30%, altrimenti si rifà la previsione prima di crescere.'),
      P('Regola di decisione: se lag di replica, autonomia di South, recovery di GitLab e del registry o riserva in South non superano un controllo, si finanzia la mitigazione oppure si rivedono formalmente RPO e RTO con il CIO. La conformità non si dichiara mai sulla sola base della configurazione.', 'call')]
build(OUT/'NFR_Capacity_Note.pdf', 'Nota NFR e capacità', n)

# ------------------------------------------------------------------ executive brief (1 page)
lo, ba, hi = PC['low']['keur_3y'], PC['base']['keur_3y'], PC['high']['keur_3y']
infra = lambda k: k['infrastructure_compute'] + k['migration_overlap_one_off'] + k['infrastructure_storage']
people = lambda k: k['client_people_run'] + k['kiratech_engagement']
e = [P('Piattaforma interna per sviluppatori su tre siti', 'title'), P('Sintesi per le decisioni  |  CIO · CISO · CFO  |  2026-11-05', 'subtitle'),
     P('Chiediamo di approvare una piattaforma IDP su tre siti che parte dall\'osservabilità e applica le policy per costruzione, e di finanziare <b>una prima fase delimitata</b> (discovery, bootstrap minimo, pilota) prima di comprare storage, nodi del broker o la riserva DR. Oggi esistono solo controlli ping/HTTP e nessuna elaborazione dei log, i cluster sono costruiti a mano senza una baseline comune e GitLab è un\'unica istanza in Central: i team non possono crearsi ambienti con costi, sicurezza e alert sotto controllo.'),
     heading('Cosa si costruisce, e in quale ordine'),
     table([['Mesi', 'Risultato'],
            ['0–2', 'Inventario, decisioni, acquisti; toolchain minima per creare da codice i cluster di osservabilità'],
            ['1–6', 'Grafana LGTM per sito; produzione esistente osservata in sola lettura; isolamento dei tenant in scrittura e in lettura; alert SLO verso i quattro team; archivio di audit immutabile duale; il monitor legacy resta fino alla parità, check per check'],
            ['5–8', 'Self-service sicuro in South: Backstage, policy GitLab Ultimate, OpenTofu e Cluster API, Flux; admission control, immagini firmate, secret esterni'],
            ['6–10', 'Fondamenta di recovery in South: identità, PKI, secret, DNS, vCenter e registry locali, riserva di capacità, GitLab HA e Geo; prova che South funziona con Central isolato'],
            ['9–15', 'Migrazione dei cluster esistenti con le controparti DR: 50% della produzione entro il mese 12, 100% o eccezioni firmate dal CIO entro il mese 15; golden path promosso in produzione (mesi 11–13)'],
            ['15–18', 'Drill di perdita di Central su tutto l\'inventario, poi impegno su RPO e RTO; 30 cluster e 1.500 pod dentro gli SLO; passaggio ai team del cliente']], [W*.09, W*.91]),
     heading(f'Quanto costa: circa {m1(ba["total"])} in 3 anni (da {m1(lo["total"])} a {m1(hi["total"])}), cifre indicative e non quotazioni'),
     table([['', 'Basso', 'Base', 'Alto'],
            [f'Infrastruttura (~{n0(PC["base"]["vcpu_total"])} vCPU, ~{fmt(PC["base"]["storage_physical_tib"], ".0f")} TiB fisici, overlap di migrazione)', m2(infra(lo)), m2(infra(ba)), m2(infra(hi))],
            ['Subscription e appliance', m2(lo['subscriptions_appliances']), m2(ba['subscriptions_appliances']), m2(hi['subscriptions_appliances'])],
            ['Persone: esercizio del cliente e ingaggio Kiratech', m2(people(lo)), m2(people(ba)), m2(people(hi))],
            ['<b>Totale del programma</b> (calcolato prima degli arrotondamenti)', f'<b>{m2(lo["total"])}</b>', f'<b>{m2(ba["total"])}</b>', f'<b>{m2(hi["total"])}</b>']],
           [W*.52, W*.16, W*.16, W*.16]),
     P(f'La voce infrastrutturale più grande è la riserva DR in South ({fmt(FL["south_dr_reserve_vcpu_gib"][0])} vCPU, circa {fmt(reserve_keur/1000, ".2f")} M€ nello scenario base), da dimensionare sulle richieste di produzione misurate. Passare dal DR 1:1 al pooled farebbe risparmiare solo {fmt(pooled_keur/1000, ".2f")} M€ circa, il tiered {fmt(tiered_keur/1000, ".2f")} M€. L\'osservabilità da sola costa {fmt(TCO["oss_keur"]/1000, ".2f")} M€ in OSS contro {fmt(TCO["supported_keur"]/1000, ".2f")} M€ con supporto commerciale (subscription segnaposto): l\'OSS resta preferibile a meno di una quotazione sotto {TCO["break_even_subscription_keur_year"]} k€ l\'anno. Sono esclusi il contratto GitLab esistente, la capacità di produzione attuale e la tariffa commerciale di Kiratech.', 'small'),
     heading('Rischi principali'),
     P(f'Il recovery in 4 ore è <b>un design condizionale</b>: {DR["designed_min"]} minuti modellati ({DR["declare_after_60min_wait_min"]} con l\'attesa limitata), non misurati, che reggono solo con la riserva in South finanziata, i servizi abilitanti già attivi in South e ogni dataset in perimetro replicato. Sull\'evidenza, la semantica di Object Lock va verificata sullo storage scelto, e poiché GitLab Geo è asincrono il DR si basa sulle release già copiate in South. Infine il carico di esercizio: circa {fmt(BASE.client_run_fte)} FTE nello scenario base (SRE {fmt(fte[0], ".1f")}, Platform Engineering {fmt(fte[1], ".1f")}, Data Engineering {fmt(fte[2], ".1f")}, Network Security {fmt(fte[3], ".1f")}).'),
     heading('Decisioni richieste'),
     P('Al CIO: perimetro del recovery ed eccezioni per i cluster legacy, delega per dichiarare il disastro, disastri dichiarati fuori dallo SLO di disponibilità. Al CISO: modello di evidenza dell\'audit, trust root delle firme, autorità sulle eccezioni, accettazione dell\'isolamento in lettura, owner di identità, PKI e secret (A-17). Al CFO: finanziamento della prima fase delimitata, riserva in South dimensionata sulle richieste misurate, quotazioni reali prima di decidere sul supporto commerciale.'),
     P('Go/no-go: nessuna coorte di produzione si sposta prima che l\'autonomia di South sia provata e la sua controparte DR sia pronta; nessun impegno su RPO e RTO finché un drill di perdita di Central su tutto l\'inventario non rispetta RPO ≤1 h e RTO ≤4 h.', 'call')]
build(OUT/'Executive_Decision_Brief.pdf', 'Sintesi per le decisioni', e)
print('wrote', *sorted(str(p.name) for p in OUT.glob('*.pdf')))
