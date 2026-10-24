"""Review formatting cannot accept arbitrary values or change financial units."""
import pytest
from src.analysis_agent.presentation import reviewed_value

@pytest.mark.parametrize('value,unit,mode,text',[
    (1619000000,'USD','usd_millions_0','US$1,619 millones'),
    (48700000,'USD','usd_millions_1','US$48.7 millones'),
    (-3.2,'percent_change','decline_percent','3.2%'),
    (.42,'fraction','integer_percent','42%'),
    (2.1,'multiple','multiple_number','2.1'),
    (17.2,'cents_USD_per_ASM','native_cents_number','17.2'),
    (1619000000,'USD','period_year','2026'),
])
def test_reviewed_rendering_from_replayed_values(value,unit,mode,text):
    assert reviewed_value(dict(value=value,unit=unit,period_id='2026Q3'),mode)==text

@pytest.mark.parametrize('value,unit,mode',[
    (1619,'count','usd_millions_0'),(3.2,'percent_change','decline_percent'),
    (42,'percent_change','integer_percent'),(2.1,'fraction','multiple_number'),
    (17.2,'cents_USD_per_ASK','native_cents_number'),(1,'USD','arbitrary'),
])
def test_incompatible_units_and_invented_format_refused(value,unit,mode):
    with pytest.raises(ValueError):
        reviewed_value(dict(value=value,unit=unit,period_id='2026Q3'),mode)


def test_review_period_not_derived_from_an_unrelated_period():
    with pytest.raises(ValueError):
        reviewed_value(dict(value=1,unit='USD',period_id='2026YTD9'),'period_year')


def test_ytd_revenue_requires_quarter_then_ytd_column_heading(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from src.analysis_agent import quarterly_editorial as e
    monkeypatch.setattr(e,'PATHS',SimpleNamespace(bronze=tmp_path))
    (tmp_path/'release.html').write_text('<table></table><table><tr><td>Total revenue (USD millions)</td><td>4440</td></tr></table>')
    with pytest.raises(ValueError,match='Quarter/YTD heading'):
        e.ytd_metric({'sources':[{'artifact_id':'release','source_file':'release.html'}]})


def test_editorial_source_set_cannot_expand_to_another_issuer():
    from src.analysis_agent.quarterly_editorial import supplement
    with pytest.raises(ValueError,match='Unexpected editorial sources'):
        supplement([{'artifact_id':'financial_pdf','source_url':'https://example.com/report.pdf'}])

@pytest.mark.parametrize('stamp,accepted',[
    ('2026-10-24T23:30:00-12:00',False),
    ('2026-10-25T01:30:00+03:00',True),
])
def test_capture_cutoff_is_utc_not_local_date(tmp_path,monkeypatch,stamp,accepted):
    import hashlib,json
    from types import SimpleNamespace
    from src.analysis_agent import quarterly_editorial as e
    monkeypatch.setattr(e,'PATHS',SimpleNamespace(bronze=tmp_path))
    class Page:
        def extract_text(self):return 'Aeroméxico September 2026 Traffic Results'
    monkeypatch.setattr(e,'PdfReader',lambda raw:SimpleNamespace(pages=[Page()]*(13 if raw.getvalue()==b'financial'else 2)))
    sources=[]
    for key,url,raw in [('financial_pdf',e.FINANCIAL,b'financial'),('september_traffic',e.TRAFFIC,b'traffic')]:
        name=key+'.pdf';(tmp_path/name).write_bytes(raw);sha=hashlib.sha256(raw).hexdigest()
        proof=json.dumps({'url':url,'status':200,'sha256':sha,'bytes':len(raw),'captured_at':stamp}).encode();(tmp_path/(name+'.meta.json')).write_bytes(proof)
        sources.append({'artifact_id':key,'source_url':url,'source_file':name,'artifact_sha256':sha,'capture_proof_sha256':hashlib.sha256(proof).hexdigest(),'captured_at':stamp})
    if accepted:assert len(e.supplement(sources))==15
    else:
        with pytest.raises(ValueError,match='beyond cutoff'):e.supplement(sources)


def test_private_review_status_absent_from_entire_public_json():
    import json
    from src.web_export.analysis import _drop_private_sections
    secret='PRIVATE_ADMIN_SENTENCE sin aprobación humana'
    record={'draft':{'thesis_claim_id':'title','summary_claim_ids':['summary'],
        'context_claim_ids':['context'],'reader_private_section_keys':['questions'],
        'sections':[{'key':'financial','claim_ids':['public','shared']},
                    {'key':'questions','claim_ids':['private','shared']}]}}
    public={'sections':[{'title':'Financial','paragraphs':['Visible','Shared']},
                        {'title':'Pending','paragraphs':[secret,'Shared']}],
        'claims':[{'claim_id':key,'text':text}for key,text in [('title','Title'),('summary','Summary'),
                  ('context','Context'),('public','Visible'),('shared','Shared'),('private',secret)]]}
    result=_drop_private_sections(public,record)
    assert secret not in json.dumps(result,ensure_ascii=False)
    assert [c['claim_id']for c in result['claims']]==['title','summary','context','public','shared']
    assert len(result['sections'])==1
