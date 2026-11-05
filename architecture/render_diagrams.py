#!/usr/bin/env python3
"""Generate source DOT, SVG and PNG C4-style views from architecture/model.json.

Only Python stdlib and Graphviz CLI (`dot`) are required. The seven views select
canonical nodes/relationship IDs from one model, avoiding manually edited diagrams.
"""
import argparse
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
import textwrap

ROOT = Path(__file__).resolve().parent
PALETTE = {
    'Person': ('#fff8ec', '#a67327'),
    'External System': ('#edf4f9', '#3b667c'),
    'Software System': ('#e8f0ff', '#3366a8'),
    'Container': ('#e7f4fa', '#277896'),
    'Component': ('#e4f3f2', '#247b72'),
    'Deployment Node': ('#edf3e8', '#63834c'),
    'Data Store': ('#f5eafd', '#835a9f'),
}

# Display labels only: model values (type, site) stay unchanged because colours and checks depend on them.
KIND_LABEL = {
    'Person': 'Persona', 'External System': 'Sistema esterno', 'Software System': 'Sistema software',
    'Container': 'Container', 'Component': 'Componente', 'Deployment Node': 'Nodo di deployment', 'Data Store': 'Archivio dati',
}
SITE_LABEL = {
    'central': 'Central', 'south': 'South', 'north': 'North', 'central/south': 'Central/South', 'multi': 'più siti',
    'unknown': 'sito non noto', 'south (primary) / central (standby)': 'South (primario) / Central (standby)',
}

def q(s): return json.dumps(str(s), ensure_ascii=False)

def code_id(s): return re.sub(r'[^a-zA-Z0-9_]', '_', s)

def fmt(s, width=25):
    return '\n'.join(textwrap.wrap(str(s), width=width, break_long_words=False, break_on_hyphens=False))

def node_line(nid, data):
    kind = data['type']; fill, stroke = PALETTE[kind]
    title = fmt(data['name'], 28)
    tech = data.get('technology', '')
    site = SITE_LABEL.get(data.get('site', ''), data.get('site', ''))
    detail = f"[{KIND_LABEL.get(kind, kind)}" + (f": {tech}" if tech else '') + "]" + (" | " + site if site else '')
    # Use Graphviz plaintext \n sequences encoded directly into quoted labels.
    label = title+'\n'+fmt(detail, 34)
    if data.get('owner'):
        label += '\n'+fmt('Owner: '+data['owner'], 34)
    tooltip = f', tooltip={q(data["description"])}' if data.get('description') else ''
    return (f'{q(nid)} [label={q(label)}, fillcolor={q(fill)}, color={q(stroke)}, '
            f'fontcolor="#182c3d", penwidth=1.4, fontsize=11, width=2.4, margin="0.16,0.12"{tooltip}];')

LEGEND = ('Notazione in stile C4 resa con Graphviz (non Structurizr). Riquadro: nome, [tipo C4: tecnologia] | sito, owner; '
          'nel file SVG la descrizione compare al passaggio del mouse.')
LEGEND_DEPLOY = 'Freccia rossa tratteggiata: flusso tra siti attraverso i firewall di Network Security, con il relativo F-ID (docs/12).'

def graph_label(title, legend):
    """HTML-like Graphviz label: large title, small status line and legend."""
    e = html.escape
    rows = [e(title), '<FONT POINT-SIZE="12">Architettura proposta | non è un sistema in esercizio</FONT>']
    rows += [f'<FONT POINT-SIZE="10" COLOR="#496377">{e(line)}</FONT>' for line in legend.split('\n')]
    return '<' + '<BR/>'.join(rows) + '>'

def render(model, output_dir, only=None):
    assert shutil.which('dot'), 'Graphviz `dot` executable not found'
    output_dir.mkdir(parents=True,exist_ok=True)
    nodes, rels = model['nodes'], model['relationships']
    count=0
    for vid,v in model['views'].items():
        if only and vid not in only: continue
        wanted=set(v['nodes'])
        legend = LEGEND + ('\n' + LEGEND_DEPLOY if v.get('c4_level') == 'Deployment' else '')
        lines=['digraph G {',
            '  graph [fontname="Arial", bgcolor="white", labeljust=l, labelloc=t, '
            'fontsize=19, fontcolor="#18344e", pad=0.35, nodesep=0.65, ranksep=0.90, '
            'splines=polyline, overlap=false, concentrate=false, outputorder=edgesfirst];',
            f'  graph [label={graph_label(v["title"], legend)}, rankdir={v.get("direction","LR")}];',
            '  node [shape=box, style="rounded,filled", fontname="Arial"];',
            '  edge [fontname="Arial", fontsize=8.5, color="#60778c", fontcolor="#526478", arrowsize=0.67, penwidth=1.3];']
        seen=set()
        for i,(name,ids) in enumerate(v.get('groups',{}).items()):
            local=[x for x in ids if x in wanted]
            if not local: continue
            lines.extend([f'  subgraph cluster_{i} {{',f'    label={q(name)}; style="rounded,dashed"; color="#b3c2d3";'
                          '    fontname="Arial"; fontsize=11; fontcolor="#496377"; margin=16;'])
            for nid in local:
                lines.append('    '+node_line(nid,nodes[nid]));seen.add(nid)
            lines.append('  }')
        for nid in v['nodes']:
            if nid not in seen: lines.append('  '+node_line(nid,nodes[nid]));seen.add(nid)
        for rid in v['relationships']:
            r=rels[rid]
            if r['from'] not in wanted or r['to'] not in wanted: raise ValueError(f'Missing relation target {vid} {rid}')
            s1=nodes[r['from']].get('site','');s2=nodes[r['to']].get('site','')
            rem= bool(s1 and s2 and s1 != s2 and s1 not in ['multi','multi','unknown','central/south'] and s2 not in ['multi','unknown','central/south'])
            edge_color='#b25354' if rem else '#60778c'
            label=fmt(r['label'],20)
            lines.append(f'  {q(r["from"])} -> {q(r["to"])} [label={q(label)}, color={q(edge_color)}, '
                         f'style={q("dashed" if rem else "solid")}];')
        lines.append('}')
        dot='\n'.join(lines)+'\n'
        (output_dir/f'{vid}.dot').write_text(dot,encoding='utf-8',newline='\n')  # LF on every OS for stable diffs
        for ext in ('svg','png'):
            subprocess.run(['dot',f'-T{ext}',str(output_dir/f'{vid}.dot'),'-o',str(output_dir/f'{vid}.{ext}')],check=True)
        count+=1
    return count

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--model',type=Path,default=ROOT/'model.json')
    p.add_argument('--output',type=Path,default=ROOT/'rendered')
    p.add_argument('--only',nargs='*')
    args=p.parse_args()
    model=json.loads(args.model.read_text(encoding='utf-8'))
    print(f"Rendered {render(model,args.output,args.only)} view(s) in {args.output}")

if __name__=='__main__': main()
