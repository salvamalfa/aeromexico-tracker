from copy import deepcopy
import json
from pathlib import Path
import pytest

from src.analysis_agent.quantitative import build, calculate, comparison, node, previous, MILES_TO_KM
from src.analysis_agent.evidence import REVIEW


def n(value, unit='USD', key='x', basis=None):
    return node('2026Q2',key,unit,value,[value,value],[], 'fixture',basis=basis)


@pytest.mark.parametrize('period,lag,expected',[('2026Q1',1,'2025Q4'),('2021Q1',4,'2020Q1'),('2026Q2',1,'2026Q1')])
def test_calendar_comparables(period,lag,expected):
    assert previous(period,lag)==expected


@pytest.mark.parametrize('base',[0,-10])
def test_nonpositive_base_has_no_percentage(base):
    assert comparison(n(10),n(base),'2026Q2','change','percent')['value'] is None
    assert comparison(n(10),n(base),'2026Q2','change','absolute')['value']==10-base


def test_missing_quarter_does_not_skip_to_available_quarter():
    assert comparison(n(10),None,'2026Q2','change','percent')['status']=='unavailable'


def test_percentage_points_and_units():
    result, intermediate=comparison(n(.849,'fraction'),n(.844,'fraction'),'2026Q2','load','absolute')
    assert result['value']==pytest.approx(.5)
    assert result['unit']=='pp'
    with pytest.raises(ValueError,match='units'):
        calculate('2026Q2','bad','subtract',[n(1,'USD'),n(1,'liters')],'USD')


def test_currency_and_adjustment_are_not_interchangeable():
    result=comparison(n(1,basis={'currency':'USD'}),n(1,basis={'currency':'MXN'}),'2026Q2','bad','percent')
    assert result['status']=='unavailable'
    result=comparison(n(1,basis={'condition':'reported'}),n(1,basis={'condition':'adjusted'}),'2026Q2','bad','absolute')
    assert result['status']=='unavailable'


def test_denominator_interval_crossing_zero_is_unavailable():
    denominator=node('2026Q2','d','liters',.1,[-.1,.3],[],'fixture')
    assert calculate('2026Q2','ratio','divide',[n(1),denominator],'USD_per_liter')['value'] is None


@pytest.fixture(scope='module')
def calculation():
    p=json.loads((REVIEW/'2026Q2_review.json').read_bytes())['package']
    return p,build(p)


@pytest.mark.local_data
def test_frozen_package_is_not_mutated_and_results_repeat(calculation):
    p,result=calculation
    original=deepcopy(p)
    assert build(p)==result and p==original


@pytest.mark.local_data
def test_conversion_and_bridge_closure(calculation):
    p,result=calculation
    lookup={(n['period_id'],n['key']):n for n in result['nodes']}
    assert lookup['2026Q2','ask']['value']==pytest.approx(9256e6*MILES_TO_KM)
    assert lookup['2026Q2','rask']['value']==pytest.approx(16/MILES_TO_KM)
    assert lookup['2026Q2','spread']['value']==pytest.approx(.7/MILES_TO_KM)
    assert all(b['status']=='passed' and abs(b['error'])<1e-10 for b in result['bridges'])
    assert len(result['identity_bridges'])==4
    assert all(b['status']=='passed' for b in result['identity_bridges'])


@pytest.mark.local_data
def test_lineage_graph_has_resolved_acyclic_references(calculation):
    p,result=calculation
    known={m['metric_id'] for m in p['metrics']}
    for node in result['nodes']:
        assert all(i in known for i in node['input_ids'])
        assert node['calculation_id'] not in known
        known.add(node['calculation_id'])


@pytest.mark.local_data
def test_cost_differences_are_not_hidden_as_success(calculation):
    p,result=calculation
    differences=[c for c in result['checks'] if c['status']=='not_reconciled']
    assert len(differences)==5
    assert all(c['identity']=='cask_cost_identity' for c in differences)
    assert result['analysis_constraints']['allow_spread_to_financial_margin_attribution'] is False
    assert not [c for c in result['checks'] if c['status']=='failed']


def test_blocked_history_cannot_enter_engine():
    p=json.loads((REVIEW/'2021Q1_review.json').read_bytes())['package']
    with pytest.raises(ValueError,match='Blocked'):
        build(p)
