"""Business reader tabs and source-only superscript citations."""
import json
from urllib.parse import quote, urlparse
from bs4 import BeautifulSoup, NavigableString
from src.dashboard.flights_html import integrated_flights_css, render_flights_panel
from src.dashboard.navigation import READER_TAB_SPECS
from .analyst import formatted, lineage


def refine(page, entries, flights_payload):
    soup=BeautifulSoup(page,'html.parser')
    kpis=soup.select_one('.kpi-grid');card=soup.select_one('.narrative-card')
    kpis['class']=[*kpis.get('class',[]),'reader-economy-kpis']
    kpis['aria-label']='Indicadores de economía unitaria'
    for kpi in kpis.select('.kpi-card'):
        if kpi.get('data-kpi') in {'load_factor_reported','passengers'}:kpi.decompose()
    margin=BeautifulSoup('''<article class="kpi-card" data-kpi="unit_margin_cents_per_km" data-accent="green"><span class="kpi-info" title="Diferencia entre RASK y CASK por asiento-kilómetro ofrecido." aria-label="Diferencia entre RASK y CASK por asiento-kilómetro ofrecido.">i</span><p class="kpi-label">Margen unitario</p><p class="kpi-value" id="kpi-unit_margin_cents_per_km-value">—</p><div class="kpi-comparisons"><div class="comparison-chip"><span>vs. trimestre anterior</span><strong id="kpi-unit_margin_cents_per_km-qoq">—</strong></div><div class="comparison-chip"><span>vs. año anterior</span><strong id="kpi-unit_margin_cents_per_km-yoy">—</strong></div></div></article>''','html.parser')
    kpis.append(margin.article)
    tab_buttons=''.join(f'<button id="tab-{spec.key}" role="tab" aria-selected="{str(index == 0).lower()}" aria-controls="panel-{spec.key}"'+('' if index == 0 else ' tabindex="-1"')+f'>{spec.title}</button>' for index,spec in enumerate(READER_TAB_SPECS))
    tab_panels=''.join(f'<section id="panel-{spec.key}" role="tabpanel" aria-labelledby="tab-{spec.key}"'+('' if index == 0 else ' hidden')+'></section>' for index,spec in enumerate(READER_TAB_SPECS))
    tabs=BeautifulSoup(f'<div class="reader-tabs" role="tablist" aria-label="Vistas del dashboard">{tab_buttons}</div>{tab_panels}','html.parser')
    kpis.insert_before(tabs)
    reading=soup.find(id='panel-reading');economy=soup.find(id='panel-economy')
    reading.append(card.extract())
    unit=soup.find(id='unit-heading').find_parent('section')
    economy.append(kpis.extract())
    for element in [unit,soup.select_one('.chart-grid'),soup.select_one('details.disclosure')]:economy.append(element.extract())
    flights=soup.find(id='panel-flights')
    flights.append(BeautifulSoup(render_flights_panel(flights_payload),'html.parser'))
    for button in soup.select('[data-analysis-open$="evidence"]'):button.decompose()
    for dialog in soup.select('dialog[id$="evidence"]'):dialog.decompose()
    for record,authorized,package,calculations,checks in entries:
        nodes={n['calculation_id']:n for n in calculations['nodes']}
        excerpts={e['excerpt_id']:e for e in package['excerpts']};sources={s['artifact_id']:s for s in package['sources']}
        claims={c['claim_id']:c for c in record['draft']['claims']};numbers={}
        def cite(container,claim):
            for binding in claim.get('bindings',{}).values():
                node=nodes[binding['calculation_id']]
                if node['period_id']!=package['period_id'] or binding.get('presentation')=='period_label':continue
                if not (node['formula'].startswith('Reported normalized') or node['key']=='ask'):continue
                leaves=lineage(node['calculation_id'],package,calculations)
                if len(leaves)!=1:continue
                metric=leaves[0];excerpt=excerpts[metric['excerpt_id']];source=sources[metric['artifact_id']]
                url=source['source_url']
                if urlparse(url).scheme!='https' or urlparse(url).hostname not in ('www.sec.gov','sec.gov','ir.aeromexico.com'):continue
                cells=[c.strip() for c in excerpt['text'].split('|') if c.strip()]
                # Range directive spans table cells, whose separators are parser-only.
                fragment=quote(cells[0],safe='').replace('-','%2D')
                if len(cells)>1:fragment+=','+quote(cells[1],safe='').replace('-','%2D')
                href=url.split('#')[0]+'#:~:text='+fragment
                number=numbers.setdefault(href,len(numbers)+1)
                value=formatted(node,business=True)
                for text in list(container.find_all(string=True)):
                    if value not in str(text) or text.parent.name in ('a','sup'):continue
                    before,after=str(text).split(value,1)
                    sup=soup.new_tag('sup');a=soup.new_tag('a',href=href,target='_blank',rel='noopener noreferrer',attrs={'class':'source-note','aria-label':f'Fuente {number}: abrir dato original'})
                    a.string=str(number)
                    a['title']='Reporte original · '+cells[0]+(': '+cells[1] if len(cells)>1 else '')+(' millones de asientos-milla; convertido a asientos-kilómetro.' if node['key']=='ask' else '')
                    sup.append(a);text.replace_with(NavigableString(before+value),sup,NavigableString(after));break
        period=authorized['period_id'];block=soup.select_one(f'[data-analysis-period="{period[-1]}T{period[2:4]}"]')
        for li,cid in zip(block.select('.analysis-summary li'),record['draft']['summary_claim_ids']):cite(li,claims[cid])
        dialog=soup.find(id='analysis-'+period+'-full')
        intro=dialog.select_one('.modal-content > .muted')
        if intro:intro.decompose()
        private=record['draft'].get('reader_private_section_keys',[])
        for section in record['draft']['sections']:
            if section['key'] not in private:continue
            for heading in dialog.find_all('h3'):
                if heading.get_text()==section['title']:heading.decompose()
            for cid in section['claim_ids']:
                button=dialog.find(attrs={'data-evidence':cid})
                if button:button.find_parent('p').decompose()
        for button in list(dialog.select('[data-evidence]')):
            cite(button.find_parent('p'),claims[button['data-evidence']]);button.decompose()
    flight_style=soup.new_tag('style');flight_style.string=integrated_flights_css();soup.head.append(flight_style)
    style=soup.new_tag('style');style.string='''.reader-tabs{display:flex;gap:8px;border-bottom:1px solid #d7e2f0;margin:20px 0;overflow-x:auto}.reader-tabs button{font:inherit;font-size:14px;font-weight:700;background:transparent;border:0;border-bottom:3px solid transparent;color:#63748b;padding:12px 16px;cursor:pointer;white-space:nowrap}.reader-tabs button[aria-selected=true]{color:#073576;border-bottom-color:#073576}[role=tabpanel][hidden]{display:none!important}.reader-economy-kpis{grid-template-columns:repeat(4,minmax(0,1fr))}.reader-economy-kpis .kpi-card[data-accent=green]{--accent:var(--altitude-green);--open:#e8f6f1}.analysis-summary{font-size:13px;line-height:1.65}.analysis-summary li{margin:12px 0}.narrative-card h3{font-size:21px}.analysis-context{font-size:12px}.source-note{color:#2463a4;text-decoration:none;padding:0 3px;font-size:10px}.source-note:hover{text-decoration:underline}.source-note:focus-visible,.reader-tabs button:focus-visible{outline:2px solid #b98505;outline-offset:3px}@media(max-width:900px){.reader-economy-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:700px){.reader-economy-kpis .kpi-card:last-child{grid-column:auto}}@media(max-width:420px){.reader-tabs{gap:0}.reader-tabs button{flex:1;padding:10px 4px;font-size:10px}}''';soup.head.append(style)
    style.string+=' .analysis-dialog .modal-content p{font-size:13px;line-height:1.7;margin:12px 0 18px}.analysis-dialog .modal-content h3{font-size:17px;line-height:1.4;margin:24px 0 10px}.analysis-dialog .modal-content strong{font-weight:700;color:#082a56}'
    flight_data=soup.new_tag('script',id='flight-dashboard-data',type='application/json');flight_data.string=json.dumps(flights_payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('&','\\u0026').replace('<','\\u003c').replace('>','\\u003e').replace('\u2028','\\u2028').replace('\u2029','\\u2029');soup.body.append(flight_data)
    from src.dashboard.flights_html import JS_PATH
    flight_script=soup.new_tag('script');flight_script['data-runtime']='flights-dashboard';flight_script.string=JS_PATH.read_text(encoding='utf-8');soup.body.append(flight_script)
    script=soup.new_tag('script');script.string='''(()=>{const tabs=[...document.querySelectorAll('.reader-tabs [role=tab]')];function activate(tab){tabs.forEach(t=>{const on=t===tab;t.setAttribute('aria-selected',String(on));t.tabIndex=on?0:-1;document.getElementById(t.getAttribute('aria-controls')).hidden=!on});const panel=document.getElementById(tab.getAttribute('aria-controls'));requestAnimationFrame(()=>Promise.all([...panel.querySelectorAll('.js-plotly-plot')].map(p=>Plotly.Plots.resize(p))).then(()=>window.dispatchEvent(new CustomEvent('reader-tab-visible',{detail:{panelId:panel.id}}))))}tabs.forEach((t,i)=>{t.addEventListener('click',()=>activate(t));t.addEventListener('keydown',e=>{let index;if(e.key==='ArrowRight')index=(i+1)%tabs.length;if(e.key==='ArrowLeft')index=(i-1+tabs.length)%tabs.length;if(e.key==='Home')index=0;if(e.key==='End')index=tabs.length-1;if(index!==undefined){e.preventDefault();activate(tabs[index]);tabs[index].focus()}})});})();''';soup.body.append(script)
    return str(soup)

