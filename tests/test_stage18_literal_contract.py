from copy import deepcopy
import hashlib
import pytest
from test_stage16_analyst import inputs
from src.analysis_agent.analyst import validate,emphasized


def test_emphasis_escapes_and_retains_two_distinct_phrases():
    assert emphasized('Inicio. Texto <script>. Final.','Inicio.',['Final.'])=='<strong>Inicio.</strong> Texto &lt;script&gt;. <strong>Final.</strong>'


def test_reported_percentage_requires_unambiguous_literal_source(inputs):
    d,p,c=inputs
    p['excerpts'][0]['text']='Ingresos aumentaron 13.3% anual.'
    claim=d['claims'][0];claim['text_template']+=' Cambio {{reported}}.'
    claim['reported_percentages']={'reported':{'excerpt_id':'e','span':'Ingresos aumentaron 13.3% anual.'}}
    assert '13.3%' in validate(d,p,c)['rendered'][claim['claim_id']]
    claim['reported_percentages']['reported']['span']='Ingresos aumentaron 15.3% anual.'
    with pytest.raises(ValueError,match='exact cited span'):validate(d,p,c)


def test_literal_hash_and_content_cannot_drift(inputs):
    d,p,c=inputs;rendered=validate(d,p,c)['rendered']
    title=rendered[d['thesis_claim_id']];bullets=[rendered[cid] for cid in d['summary_claim_ids']]
    markdown='### **'+title+'**\n\n'+'\n'.join('- '+b for b in bullets)+'\n'
    d['literal_user_text']=dict(title=title,bullets_markdown=bullets,original_hash=hashlib.sha256(markdown.encode()).hexdigest())
    validate(d,p,c)
    d['literal_user_text']['bullets_markdown'][0]+=' Alteración.'
    with pytest.raises(ValueError,match='Literal user text changed'):validate(d,p,c)


def test_reject_wrong_short_unit_presentation(inputs):
    d,p,c=inputs
    d['claims'][0]['bindings']['amount']['presentation']='cents_short'
    with pytest.raises(ValueError,match='Invalid binding presentation'):validate(d,p,c)
