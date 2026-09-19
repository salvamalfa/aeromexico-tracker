"""Prepare the exact user summary as a mechanically checked, immutable draft."""
import json
import re
from pathlib import Path
from src.config import PATHS
from .analyst import load_inputs, save
from .stage16_html import render
from .stage18 import consumer_html
from src.dashboard.executive_summary import build_executive_payload


def main():
    root=PATHS.root
    prior=json.loads((root/'analysis_runs/drafts/2026Q2/7f1596741b585d0baafec203b7aa11c623fbc66a1b3cab825d193597bb859938.json').read_bytes())
    draft=prior['draft']
    package,calc=load_inputs(root/'analysis_runs/evidence'/f"{draft['package_id']}.json",root/'analysis_runs/quantitative'/f"{draft['calculation_fingerprint']}.json")
    literal=json.loads((root/'analysis_runs/editorial_overrides/dca2600fa81c556911a1a2abe495bcfc71ba6f7344fb6632519908fb3c9db3a7.json').read_bytes())
    claims={c['claim_id']:c for c in draft['claims']}
    claims['thesis']['text_template']=literal['title']
    replacements=[{'1,479.0 millones de dólares':'total_revenue','12.6%':'total_revenue_yoy_percent'},
                  {'10.3%':'rask_yoy_percent','28.6%':'cask_yoy_percent','0.43 centavos de dólar':'spread'},
                  {'67.9 millones de dólares':'operating_income','4.6%':'operating_margin'},{}]
    for cid,markdown,bindings in zip(draft['summary_claim_ids'],literal['bullets_markdown'],replacements):
        c=claims[cid];c['lead']=re.findall(r'\*\*(.*?)\*\*',markdown)[0]
        c['emphasis']=re.findall(r'\*\*(.*?)\*\*',markdown)[1:]
        c['text_template']=markdown.replace('**','')
        for value,alias in bindings.items():c['text_template']=c['text_template'].replace(value,'{{'+alias+'}}')
    claims['summary_unit']['bindings']['spread']['presentation']='cents_short'
    # Apply the requested editorial rule to the full analysis, retaining its evidence.
    changes={
      'Aquí se presenta como información complementaria, no como efectivo que pueda gastarse o usarse para pagar deuda.':'Aquí se presenta como información complementaria. La disponibilidad de efectivo para gastos y deuda requiere revisar los flujos de caja.',
      'La presión aparece principalmente en cuánto costó ese consumo, no en consumir mucho más.':'La presión se concentra en el costo reconocido de ese consumo.',
      'Aun así, el costo efectivo por litro no es una cotización de mercado: con este expediente no se separan los efectos de contratos, coberturas y otros componentes.':'El costo efectivo por litro reúne el gasto reconocido; el expediente deja pendientes las contribuciones de contratos, coberturas y otros componentes.',
      'Son preguntas concretas para el siguiente análisis, no espacios que deban llenarse con estimaciones sin respaldo.':'Resolver estas preguntas requiere evidencia adicional en el siguiente análisis.',
      'Además, contar viajeros y medir capacidad no es lo mismo: la distancia de los vuelos también influye en cuánta oferta se utiliza.':'La distancia de los vuelos también influye en cuánta oferta se utiliza y complementa el conteo de viajeros.'
    }
    for c in draft['claims']:
        if c['claim_id'] not in draft['summary_claim_ids']:
            for old,new in changes.items():c['text_template']=c['text_template'].replace(old,new)
    nodes={(n['key'],n['period_id']):n for n in calc['nodes'] if n['value'] is not None}
    def binding(key,period,mode='default'):
        n=nodes[key,period]
        return dict(calculation_id=n['calculation_id'],period_id=period,unit=n['unit'],presentation=mode)
    context=dict(claim_id='comparison_context',type='observed_fact',confidence_reason='Comparación calendario y definiciones del expediente.',limitations=[],
      text_template='Contexto de la comparación. El crecimiento de ingresos de {{current_period}} supera al de {{third}} y {{fourth}}. En {{first}}, los ingresos crecieron {{prior_growth}} anual, por encima del {{current_growth}} de este trimestre. RASK y CASK expresan ingreso y costo por asiento-kilómetro ofrecido.',
      bindings={'current_period':binding('total_revenue','2026Q2','period_label'),'third':binding('total_revenue','2025Q3','period_label'),
                'fourth':binding('total_revenue','2025Q4','period_label'),'first':binding('total_revenue','2026Q1','period_label'),
                'current_growth':binding('total_revenue_YoY_percent','2026Q2')},
      reported_percentages={'prior_growth':{'excerpt_id':'exc_69d3d272037c63bf0bb60c1d0c39d062f1e9897b8a51a9d5c1d77702e4af4655','span':'Total revenue reached $1.3 billion, a 13.3% increase as compared to the same period of 2025.'}},
      evidence_ids=[*claims['thesis']['evidence_ids'],'exc_69d3d272037c63bf0bb60c1d0c39d062f1e9897b8a51a9d5c1d77702e4af4655'],support_calculation_ids=[nodes['total_revenue',p]['calculation_id'] for p in ('2025Q3','2025Q4','2024Q3','2024Q4')])
    draft['claims'].append(context);draft['context_claim_ids']=['comparison_context']
    draft['literal_user_text']={'title':literal['title'],'bullets_markdown':literal['bullets_markdown'],'original_hash':literal['content_hash']}
    record,checks,path=save(draft,package,calc)
    assert checks['rendered']['thesis']==literal['title']
    assert [checks['rendered'][cid] for cid in draft['summary_claim_ids']]==[b.replace('**','') for b in literal['bullets_markdown']]
    out=root/'prototypes/etapa-18/analisis_final_revision.html'
    out.write_text(render(record,checks,package,calc),encoding='utf-8')
    display=dict(period_id=draft['period_id'],version=record['version'],content_hash=record['content_hash'],
      thesis=checks['rendered'][draft['thesis_claim_id']],summary_items=[dict(text=checks['rendered'][cid],lead=claims[cid]['lead'],emphasis=claims[cid].get('emphasis',[])) for cid in draft['summary_claim_ids']],
      context=[checks['rendered'][cid] for cid in draft['context_claim_ids']],evidence_fingerprint=draft['evidence_fingerprint'],approval_event=None,audit_hash=None)
    preview=consumer_html(build_executive_payload(),[(record,display,package,calc,checks)])
    preview=preview.replace('Análisis aprobado · cifras del expediente al corte','Versión para revisión · cifras del expediente al corte')
    preview=preview.replace('<section class="narrative-card"','<p class="proposal-label">Etapa 18 · versión estructurada para revisión · pendiente de aprobación final</p><section class="narrative-card"',1)
    (root/'prototypes/etapa-18/resumen_ejecutivo_revision.html').write_text(preview,encoding='utf-8')
    receipt=root/'analysis_runs/stage18/final_record_path.txt';receipt.parent.mkdir(parents=True,exist_ok=True);receipt.write_text(str(path),encoding='utf-8')
    print(json.dumps({'record':str(path),'summary_words':checks['summary_words'],'detail_words':checks['detail_words']}))


if __name__=='__main__':main()
