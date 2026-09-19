import pytest
from test_stage16_analyst import inputs
from src.analysis_agent.analyst import validate,save,formatted
from src.analysis_agent.stage16_html import render


@pytest.fixture
def business(inputs):
    d,p,c=inputs;d['summary_format']='business_bullets_v1'
    d['summary_claim_ids']=[x['claim_id'] for x in d['claims'][:3]]
    for i,claim in enumerate(d['claims'][:3]):
        claim['lead']='El negocio cambió.'
        claim['text_template']=claim['lead']+' Esta es una oración ficticia para comprobar el contrato editorial.'*7
        if i==0:claim['text_template']+=' Valor: {{amount}}.'
    return d,p,c


def test_summary_has_semantic_bullets_and_supported_bold_prefix(business,tmp_path):
    d,p,c=business;r,checks,_=save(d,p,c,tmp_path)
    html=render(r,checks,p,c)
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'html.parser')
    assert len(soup.select('#executive .business-summary > li'))==3
    assert [s.get_text() for s in soup.select('#executive .business-summary > li strong')]==['El negocio cambió.']*3
    assert checks['analysis_state']=='draft'


@pytest.mark.parametrize('lead',['Afirmación no incluida.','<script>El negocio cambió.</script>','El negocio cambió 99%.',''])
def test_bold_cannot_add_unvalidated_claim_or_markup(business,lead):
    d,p,c=business;d['claims'][0]['lead']=lead
    with pytest.raises(ValueError,match='Lead'):validate(d,p,c)


def test_business_units_preserve_denominator_without_unexplained_ask():
    node={'value':.434959,'unit':'cents_USD_per_ASK'}
    assert formatted(node,True)=='0.43 centavos de dólar por asiento-kilómetro ofrecido'
    assert formatted(node)=='0.43 centavos USD por ASK'
