"""Adversarial contract checks; fixtures are explicitly fictional, not business analysis."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from src.analysis_agent.analyst import SCHEMA, SECTIONS, formatted, load_inputs, save, validate
from src.analysis_agent.stage16_html import render


@pytest.fixture
def inputs():
    source = dict(artifact_id='a', period_id='2026Q2', source_url='https://www.sec.gov/example',
                  version_available_at='2026-07-13', publication_basis='fixture', artifact_sha256='test')
    excerpt = dict(excerpt_id='e', artifact_id='a', locator='table[1]', text='La compañía reporta presión de costos.')
    metric = dict(metric_id='m', excerpt_id='e', record_id='r', metric_key='total_revenue', period_id='2026Q2', formatted_value='10 USD')
    p = dict(period_id='2026Q2', package_id='p', evidence_fingerprint='f', cutoff_date='2026-07-13',
             sources=[source], metrics=[metric], excerpts=[excerpt])
    n = dict(calculation_id='c', period_id='2026Q2', key='total_revenue', unit='USD', value=10,
             status='available', input_ids=['m'], formula='fixture', formatted_value='10 USD')
    c = dict(calculation_fingerprint='q', nodes=[n])
    # Length fixtures only: exercise citation validation without external warehouse dependency.
    text = ('Esta es una oración ficticia para comprobar el contrato editorial. ' * 10).strip()
    claims = [dict(claim_id=key, type='observed_fact', text_template=text, bindings={}, evidence_ids=['e'],
                   confidence_reason='Fictional fixture', limitations=[]) for key in sorted(SECTIONS)]
    claims[0]['text_template'] += ' Valor: {{amount}}.'
    claims[0]['bindings'] = {'amount': dict(calculation_id='c', period_id='2026Q2', unit='USD')}
    d = dict(schema_version=SCHEMA, state='draft', language='es-MX', period_id='2026Q2', package_id='p',
             evidence_fingerprint='f', calculation_fingerprint='q', model=None, model_unavailable_reason='fixture',
             claims=claims, thesis_claim_id=claims[0]['claim_id'], summary_claim_ids=[x['claim_id'] for x in claims[:2]],
             sections=[dict(key=x['claim_id'], title='Sección', claim_ids=[x['claim_id']]) for x in claims])
    return d, p, c


def test_valid_draft_stays_unapproved(inputs):
    d, p, c = inputs
    check = validate(d, p, c)
    assert check['analysis_state'] == 'draft' and check['audit'] == 'pending' and check['approval'] == 'absent'


@pytest.mark.parametrize('field,value', [('unit','MXN'), ('period_id','2025Q2'), ('calculation_id','missing')])
def test_wrong_binding_rejected(inputs, field, value):
    d,p,c = inputs
    d['claims'][0]['bindings']['amount'][field] = value
    with pytest.raises(ValueError): validate(d,p,c)


@pytest.mark.parametrize('field,value', [('state','approved'), ('package_id','other'), ('calculation_fingerprint','other')])
def test_promotion_or_wrong_inputs_rejected(inputs, field, value):
    d,p,c = inputs; d[field] = value
    with pytest.raises(ValueError): validate(d,p,c)


@pytest.mark.parametrize('text', [' El margen fue 20%.', ' {{missing}}', ' {{broken'])
def test_invented_numbers_or_templates_rejected(inputs, text):
    d,p,c = inputs; d['claims'][0]['text_template'] += text
    with pytest.raises(ValueError): validate(d,p,c)


def test_unavailable_value_rejected(inputs):
    d,p,c = inputs; c['nodes'][0]['value'] = None
    with pytest.raises(ValueError): validate(d,p,c)


def test_attribution_requires_verbatim_support(inputs):
    d,p,c = inputs; claim=d['claims'][0];claim['type']='company_attribution'
    with pytest.raises(ValueError): validate(d,p,c)
    claim['support_spans']=[dict(excerpt_id='e',text='La compañía reporta presión de costos.')]
    assert validate(d,p,c)['status']=='passed'
    claim['support_spans'][0]['text']='La compañía garantiza crecimiento.'
    with pytest.raises(ValueError): validate(d,p,c)


def test_hypothesis_requires_limit_and_missing_evidence_rejected(inputs):
    d,p,c=inputs; d['claims'][1]['type']='hypothesis'
    with pytest.raises(ValueError): validate(d,p,c)
    d['claims'][1]['limitations']=['No estimar.']; d['claims'][1]['evidence_ids']=['unknown']
    with pytest.raises(ValueError): validate(d,p,c)


def test_versions_immutable_repeatable_and_changed_content_new_version(inputs,tmp_path):
    d,p,c=inputs; before=deepcopy(d)
    a,_,path=save(d,p,c,tmp_path)
    b,_,same=save(d,p,c,tmp_path)
    assert a==b and path==same and d==before
    d['claims'][0]['text_template'] += ' Revisión editorial.'
    revised,_,new=save(d,p,c,tmp_path)
    assert new!=path and revised['version']!=a['version']
    assert json.loads(path.read_bytes())==a


def test_html_escapes_source_and_prose_and_keeps_controls_inside_card(inputs,tmp_path):
    d,p,c=inputs; d['claims'][0]['text_template'] += ' <script>alert("x")</script>'
    record, checks,_=save(d,p,c,tmp_path)
    html=render(record,checks,p,c)
    assert '<script>alert("x")</script>' not in html and '&lt;script&gt;' in html
    assert html.index('id="executive"') < html.index('data-open="full"') < html.index('<aside')
    assert 'sin auditoría ni aprobación' in html
    assert 'C:\\Users' not in html


def test_formatter_uses_units_and_percentage_scaling():
    assert formatted(dict(value=.849,unit='fraction'))=='84.9%'
    assert formatted(dict(value=-.8,unit='pp'))=='-0.8 pp'
    assert formatted(dict(value=28.5714,unit='percent_change'))=='28.6%'


@pytest.mark.local_data
def test_frozen_inputs_replay_and_tampering_rejected(tmp_path):
    root=Path(__file__).resolve().parents[1]
    review=json.loads((root/'docs/referencias/etapa-14/2026Q2_review.json').read_bytes())
    p=tmp_path/'p.json'; p.write_text(json.dumps(review['package']))
    calc=root/'docs/referencias/etapa-15/calculations.json'
    package, calculations=load_inputs(p,calc)
    bad=deepcopy(calculations);bad['nodes'][0]['value']+=1
    target=tmp_path/'bad.json';target.write_text(json.dumps(bad))
    with pytest.raises(ValueError,match='replay'): load_inputs(p,target)
