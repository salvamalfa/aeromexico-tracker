"""Reproducible editorial preview; never grants approval or writes the consumer."""
from html import escape
import json
from pathlib import Path
from bs4 import BeautifulSoup
from src.config import PATHS


def main():
    root=PATHS.root
    source=root/'prototypes/etapa-17/propuesta_texto_usuario.html'
    page=source.read_text(encoding='utf-8')
    note='<aside class="analysis-context" aria-label="Contexto de la comparación"><strong>Contexto de la comparación.</strong> El crecimiento de ingresos de 2T26 supera al de 3T25 y 4T25. En 1T26, los ingresos crecieron 13.3% anual, por encima del 12.6% de este trimestre. RASK y CASK expresan ingreso y costo por asiento-kilómetro ofrecido.</aside>'
    page=page.replace('<div class="proposal-actions">',note+'<div class="proposal-actions">',1)
    page=page.replace('Propuesta visual · texto proporcionado por ti · pendiente de revisión','Etapa 18 · propuesta de integración para revisión · texto original conservado')
    page=page.replace('</head>','<style>.analysis-context{font-size:13px;line-height:1.7;border-left:3px solid #a8bbd0;padding:12px 16px;margin-top:20px;background:#fafbfc}</style></head>')
    audit=json.loads((root/'analysis_runs/audits/literal_integration_review.json').read_bytes())
    literal=json.loads((root/audit['source_paths'][0]).read_bytes())
    # Put evidence for the literal summary first, distinctly from the full analysis.
    cards=['<section><h3>Evidencia de la lectura ejecutiva</h3><p>El 10.3% de RASK se calcula con los niveles publicados redondeados. El comunicado reporta 10.5% para TRASM. El spread se expresa en centavos de dólar por asiento-kilómetro ofrecido.</p>']
    for item in audit['bullets']:
        cards.append('<details><summary>Hallazgo '+str(item['bullet'])+'</summary><p>'+escape(literal['bullets_markdown'][item['bullet']-1].replace('**',''))+'</p>')
        for calc in item.get('calculations',[]):
            cards.append('<p>'+escape(f"{calc['key']} · {calc['period_id']} · {calc['value']:.6g} {calc['unit']}")+'</p><p class="hash">'+escape(calc['calculation_id'])+'</p>')
        cards.append('</details>')
    cards.append('</section><hr><h3>Evidencia del análisis completo</h3>')
    anchor='<dialog aria-labelledby="proposal-evidence-title"'
    # Locate the modal structurally, then replace only that fragment to preserve runtime.
    soup=BeautifulSoup(page,'html.parser');dialog=soup.find('dialog',id='proposal-evidence')
    original=str(dialog)
    dialog.select_one('.modal-content').insert(0,BeautifulSoup(''.join(cards),'html.parser'))
    if original not in page: raise ValueError('Preview modal anchor changed')
    page=page.replace(original,str(dialog),1)
    output=root/'prototypes/etapa-18/resumen_ejecutivo_revision.html'
    output.parent.mkdir(parents=True,exist_ok=True);output.write_text(page,encoding='utf-8')
    print(output)


if __name__=='__main__': main()
