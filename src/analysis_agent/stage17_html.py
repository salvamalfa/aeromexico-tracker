"""Audit findings and version comparison around the local analysis review."""
from html import escape
import json
from pathlib import Path

from src.config import PATHS
from .analyst import validate
from . import lifecycle
from .stage16_html import render as analysis_html


def render(old, new, initial_audit, final_audit, adversarial, root=lifecycle.ROOT):
    p,c,checks=lifecycle.verified_inputs(new)
    previous=validate(old['draft'],p,c)
    status=lifecycle.state(new,root)
    lifecycle.audit_contract(final_audit,new)
    lifecycle.audit_contract(initial_audit,old)
    if lifecycle.state(old,root)['audit']['report']!=initial_audit:
        raise ValueError('Initial review differs from the recorded audit')
    if status['state'] not in ('validated','approved') or not status['audit'] or status['audit']['report']!=final_audit:
        raise ValueError('Review view requires the current passing audit of this exact version')
    if adversarial['version']!=new['version'] or len(adversarial['cases'])!=4 or any(x['actualverdict']!='reject' for x in adversarial['cases']):
        raise ValueError('Adversarial review is incomplete or refers to another version')
    e=lambda x:escape(str(x),quote=True)
    claim_labels={'summary_business':'Ingresos y capacidad','summary_outlook':'Combustible y expectativas',
                  'company_drivers':'Explicaciones de la compañía','questions_open':'Preguntas pendientes','methodology':'Precisión y comparabilidad'}
    check_labels={'numbers':'Cifras','units':'Unidades','comparisons':'Comparaciones','semantic_support':'Respaldo de las afirmaciones',
                  'causality':'Causalidad','contradictions':'Coherencia con el comunicado','editorial':'Claridad','lineage':'Trazabilidad','temporal':'Fecha de corte'}
    html=analysis_html(new,checks,p,c)
    html=html.replace('ETAPA 16','ETAPA 17').replace('Primera lectura para tu revisión','Análisis auditado para tu revisión')
    html=html.replace('Borrador · sin auditoría ni aprobación','Auditoría superada · aprobación pendiente')
    html=html.replace('Borrador para revisión · cifras calculadas desde el expediente al corte','Versión revisada por auditor independiente · aprobación humana pendiente')
    blocks=[]
    old_claims={x['claim_id']:x for x in old['draft']['claims']}
    for claim in new['draft']['claims']:
        cid=claim['claim_id'];before=old_claims.get(cid)
        if before!=claim:
            text_changed=previous['rendered'].get(cid)!=checks['rendered'][cid]
            comparison=(f'<p><strong>Antes</strong></p><blockquote>{e(previous["rendered"].get(cid,""))}</blockquote><p><strong>Ahora</strong></p><blockquote>{e(checks["rendered"][cid])}</blockquote>' if text_changed else '<p>Texto conservado; se añadió respaldo explícito de evidencia o cálculo.</p>')
            blocks.append(f'<details><summary>{e(claim_labels.get(cid,cid))} · {"Texto y respaldo" if text_changed else "Referencia ampliada"}</summary>{comparison}</details>')
    resolutions={
      'A17-001':'Añadí la cita que respalda la presión del combustible durante el trimestre. La cita anterior solo explicaba la expectativa futura.',
      'A17-002':'Aclaré que el paquete conserva distintas precisiones: algunas cifras vienen de tablas redondeadas y otras de importes más precisos del texto del comunicado.',
      'A17-003':'Vinculé directamente la mejora del ingreso por ASK con su cálculo, para facilitar la consulta de esa afirmación.',
      'A17-004':'Reduje limitaciones repetidas y añadí contexto del comunicado sobre la demanda de junio y los ajustes de capacidad.'}
    findings=''.join(f'<li><strong>{e(f["id"])} · {"Corrección necesaria" if f["severity"]=="blocking" else "Mejora recomendada"}</strong><p>{e(resolutions.get(f["id"],f["issue"]))}</p><span class="badge">Resuelto en la nueva versión</span></li>' for f in initial_audit['findings'])
    checklist=''.join(f'<li><strong>{e(check_labels[x["key"]])}</strong>: {e(x["detail"])}</li>' for x in final_audit['checks'])
    aside=f'''<aside class="review"><small>SOLO REVISIÓN DEL AGENTE · NO VA AL DASHBOARD</small><h2>Auditoría terminada; tu aprobación sigue pendiente</h2><p>El auditor encontró una cita incompleta y mejoras de precisión, trazabilidad y repetición. Las correcciones ya se incorporaron y la nueva versión pasó una segunda revisión independiente.</p><div class="chips"><span>Estado: {e(status['state'])}</span><span>{checks['summary_words']} palabras de resumen</span><span>{checks['detail_words']} palabras de detalle</span><span>Sin hallazgos bloqueantes abiertos</span></div><h3>Qué cambió</h3><ul>{findings}</ul><details><summary>Comparar la versión anterior y la revisada</summary>{''.join(blocks)}</details><details><summary>Comprobaciones del auditor</summary><ul>{checklist}</ul></details><details><summary>Pruebas contra afirmaciones engañosas</summary><p>El auditor rechazó cuatro casos: correlación presentada como causa, expectativa presentada como garantía, órdenes dentro de una fuente y sustitución de RASK por CASK con una referencia existente. El último caso supera el control mecánico y demuestra por qué se necesita revisión semántica independiente.</p></details><h3>Dos decisiones distintas</h3><p><strong>Aceptar la Etapa 17</strong> permite continuar con la integración. <strong>Aprobar este análisis</strong> autoriza esta versión exacta para incorporarla posteriormente al dashboard. Ninguna decisión se ha registrado automáticamente.</p><p>Puedes pedir cambios en Codex. Si deseas aprobar el contenido, identifica la versión que aparece abajo; conservaré el mensaje y la versión autorizada en el expediente.</p><p class="hash">Versión anterior: {e(old['version'])}<br>Versión revisada: {e(new['version'])}<br>Contenido: {e(new['content_hash'])}<br>Auditor: {e(final_audit['reviewer_task'])}<br>Modelo del auditor: no disponible; sin etiqueta inferida.</p><p class="muted">El registro es local y verificable mediante huellas. No es una firma digital ni autentica al usuario fuera de Codex. Solo el coordinador registra una autorización explícita recibida en la conversación.</p></aside>'''
    start=html.index('<aside class="review">');end=html.index('</aside>',start)+len('</aside>')
    html=html[:start]+aside+html[end:]
    if status['state']=='approved':
        html=html.replace('aprobación pendiente','aprobación registrada').replace('aprobación humana pendiente','aprobación humana registrada').replace('tu aprobación sigue pendiente','tu aprobación está registrada').replace('Ninguna decisión se ha registrado automáticamente.','La aprobación de contenido se registró desde una autorización explícita; no implica publicación ni aceptación de la siguiente etapa.')
    return html


def main():
    base=PATHS.root
    if (base/'analysis_runs/stage17/business_record_path.txt').exists():
        return business_main()
    old=json.loads((base/'analysis_runs/drafts/2026Q2/8b5dcd5b599e7a0647dbaab1466b0c0eda7c9364292142187aad2342e2d3f118.json').read_bytes())
    path=Path((base/'analysis_runs/stage17/revised_record_path.txt').read_text(encoding='utf-8'))
    new=json.loads(path.read_bytes())
    reports=[json.loads((base/'analysis_runs/audits'/name).read_bytes()) for name in ('initial_review.json','final_review.json','adversarial_review.json')]
    target=base/'prototypes/etapa-17/audited_analysis.html';target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(render(old,new,*reports),encoding='utf-8')
    print(target)


def business_main():
    base=PATHS.root
    old=json.loads((base/'analysis_runs/drafts/2026Q2/efa01d1304aeca7348887b0c34a2f89687c4ec3c11be29746538c509313128cc.json').read_bytes())
    new=json.loads(Path((base/'analysis_runs/stage17/business_record_path.txt').read_text(encoding='utf-8')).read_bytes())
    p,c,checks=lifecycle.verified_inputs(new)
    report=json.loads((base/'analysis_runs/audits/business_review.json').read_bytes())
    lifecycle.audit_contract(report,new)
    current=lifecycle.state(new)
    if current['state'] not in ('validated','approved') or not current['audit'] or current['audit']['report']!=report:
        raise ValueError('Business revision requires its own passing audit')
    e=lambda x:escape(str(x),quote=True)
    html=analysis_html(new,checks,p,c).replace('ETAPA 16','ETAPA 17')
    html=html.replace('Primera lectura para tu revisión','Una lectura del negocio, con cifras verificables')
    html=html.replace('Borrador · sin auditoría ni aprobación','Auditoría superada · aprobación pendiente')
    html=html.replace('Borrador para revisión · cifras calculadas desde el expediente al corte','Lectura de negocio · revisada por auditor independiente · aprobación pendiente')
    previous=validate(old['draft'],p,c)
    changes=''.join(f'<details><summary>Viñeta {i}</summary><p><strong>Antes</strong></p><blockquote>{e(previous["rendered"][cid])}</blockquote><p><strong>Ahora</strong></p><blockquote>{e(checks["rendered"][cid])}</blockquote></details>' for i,cid in enumerate(new['draft']['summary_claim_ids'],1))
    aside=f'''<aside class="review"><small>SOLO REVISIÓN DEL AGENTE · NO VA AL DASHBOARD</small><h2>Tu pauta de negocio, aplicada al agente</h2><p>Actualicé las instrucciones para todos los reportes: título directo, viñetas con la idea principal en negritas y conceptos explicados antes de sus siglas. El análisis completo también adopta ese tono.</p><p>Conservé el asiento-kilómetro ofrecido como unidad de ingreso y costo. El combustible se presenta como la mayor presión identificada; no añadí la afirmación de que los ingresos crecieron más rápido que en trimestres pasados, porque no está demostrada en esta lectura.</p><div class="chips"><span>{checks['summary_words']} palabras de resumen</span><span>{checks['detail_words']} palabras de detalle</span><span>Revisión independiente superada</span><span>Aprobación humana pendiente</span></div><details><summary>Comparar con la redacción anterior</summary>{changes}</details><details><summary>Qué comprobó el auditor</summary><p>Respaldo de las afirmaciones, cifras, unidades, comparaciones, causalidad, coherencia, claridad y fecha de corte. La auditoría corresponde a esta nueva versión; no se trasladó la revisión anterior.</p><p>{e(report['decision'])} · {len(report['findings'])} observaciones abiertas.</p></details><p>Seguimos en la Etapa 17. Puedes pedir cambios de redacción; esta revisión todavía no aprueba el análisis ni autoriza su publicación.</p><p class="hash">Versión anterior: {e(old['version'])}<br>Versión de negocio: {e(new['version'])}<br>Contenido: {e(new['content_hash'])}</p></aside>'''
    start=html.index('<aside class="review">');end=html.index('</aside>',start)+len('</aside>')
    html=html[:start]+aside+html[end:]
    if current['state']=='approved':
        html=html.replace('aprobación pendiente','aprobación registrada').replace('Aprobación humana pendiente','Aprobación humana registrada').replace('esta revisión todavía no aprueba el análisis ni autoriza su publicación.','la aprobación de contenido está registrada, pero no constituye publicación.')
    target=base/'prototypes/etapa-17/audited_analysis.html'
    target.write_text(html,encoding='utf-8');print(target)


if __name__=='__main__':main()
