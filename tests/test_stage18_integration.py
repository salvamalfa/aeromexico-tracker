import json
from pathlib import Path
import pytest
from bs4 import BeautifulSoup
from test_stage16_analyst import inputs
from test_stage17_lifecycle import case, fresh
from src.analysis_agent import lifecycle as flow
from src.analysis_agent import stage18
from src.dashboard.executive_summary import build_executive_payload
from src.dashboard.flights import build_flight_payload
from src.dashboard.flights_html import integrated_flights_css, integration_flight_payload


def test_unapproved_cannot_replace_existing_dashboard(case,tmp_path):
    record,audit,auth,root=case
    out=tmp_path/'dashboard.html';out.write_text('existing')
    with pytest.raises(ValueError,match='Publication blocked'):
        stage18.publish([record],out,build_executive_payload(),root)
    assert out.read_text()=='existing'
    assert not (root/'publications').exists()


def test_publish_retries_and_excludes_private_comments(case,tmp_path):
    record,audit,auth,root=case
    flow.record_audit(record,audit,root)
    flow.comment(record,'PRIVATE DISCUSSION NOT FOR HTML','TEST',root)
    flow.approve(record,fresh(auth),root)
    out=tmp_path/'dashboard.html';dashboard=build_executive_payload()
    first=stage18.publish([record],out,dashboard,root)
    assert flow.state(record,root)['state']=='published'
    assert stage18.publish([record],out,dashboard,root)==first
    assert len(list((root/'publications').glob('*.published.json')))==1
    page=out.read_text(encoding='utf-8');soup=BeautifulSoup(page,'html.parser')
    assert 'PRIVATE DISCUSSION NOT FOR HTML' not in page
    assert not soup.select('aside.review')
    assert len(soup.select('.narrative-card [data-analysis-open]'))==1
    assert len(soup.select('dialog.analysis-dialog'))==1
    payload=json.loads(soup.find(id='dashboard-data').string)
    assert all('narrative' not in view for view in payload['views'].values())
    tabs=soup.select('.reader-tabs [role="tab"]')
    assert [tab.get_text(strip=True) for tab in tabs]==['Lectura ejecutiva','Economía unitaria','Vuelos']
    flights=soup.select_one('#panel-flights [data-testid="flights-dashboard-root"]')
    assert flights is not None
    assert not soup.select('#panel-reading .kpi-card')
    economy_kpis=soup.select('#panel-economy .reader-economy-kpis .kpi-card')
    assert [card['data-kpi'] for card in economy_kpis]==[
        'rask_cents_per_km','cask_cents_per_km','ask_km','unit_margin_cents_per_km'
    ]
    assert '--accent:var(--altitude-green)' in page
    assert len(flights.select('.flight-kpi'))==4
    assert 'route-expand-toggle' in page
    assert 'route-direction-detail' in page
    assert 'aria-expanded="false"' in page
    assert '.route-table-total strong { font-size: 10.9px; }' in page
    assert flights.select_one('#quarter-status') is None
    assert not soup.select("#panel-economy [data-kpi='load_factor_reported'], #panel-economy [data-kpi='passengers']")
    ids=[node['id'] for node in soup.select('[id]')]
    assert len(ids)==len(set(ids))
    assert soup.select_one('#forecast-chart') is None
    assert soup.select_one('#passenger-period option[selected]').get_text(strip=True)=='Trimestral'
    embedded_flights=json.loads(soup.select_one('#flight-dashboard-data').string)
    assert embedded_flights==integration_flight_payload(build_flight_payload())
    assert not {'forecast','sources','agent_eligibility'} & embedded_flights.keys()
    tab_script=soup.find_all('script')[-1].string
    assert '(i+1)%tabs.length' in tab_script
    assert 'tabs.length-1' in tab_script
    scoped_css=integrated_flights_css()
    assert '#panel-flights .kpi-value {' in scoped_css
    assert '\n.kpi-value {' not in scoped_css
    assert '\nfooter {' not in scoped_css
    flow.revoke(record,'Test revocation','TEST',root)
    assert flow.state(record,root)['state']=='validated'
    with pytest.raises(ValueError,match='Publication blocked'):stage18.publish([record],out,dashboard,root)


def test_interrupted_replacement_preserves_old_html_and_retry(case,tmp_path,monkeypatch):
    record,audit,auth,root=case
    flow.record_audit(record,audit,root);flow.approve(record,fresh(auth),root)
    out=tmp_path/'dashboard.html';out.write_text('old')
    original=stage18.os.replace
    with monkeypatch.context() as patch:
        patch.setattr(stage18.os,'replace',lambda *a:(_ for _ in ()).throw(OSError('interrupted')))
        with pytest.raises(OSError):stage18.publish([record],out,build_executive_payload(),root)
    assert out.read_text()=='old'
    assert not list((root/'publications').glob('*.published.json'))
    stage18.publish([record],out,build_executive_payload(),root)
    assert len(list((root/'publications').glob('*.published.json')))==1

