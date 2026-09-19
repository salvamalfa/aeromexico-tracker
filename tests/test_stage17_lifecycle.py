from copy import deepcopy
from datetime import datetime, timezone
import json
import sqlite3

import pytest

from test_stage16_analyst import inputs
from src.analysis_agent.analyst import save, validate
from src.analysis_agent import lifecycle as flow


def fresh(authorization):
    authorization['authorized_at']=datetime.now(timezone.utc).isoformat()
    return authorization


@pytest.fixture
def case(inputs,tmp_path,monkeypatch):
    d,p,c=inputs;record,_,_=save(d,p,c,tmp_path/'drafts')
    monkeypatch.setattr(flow,'verified_inputs',lambda r:(p,c,validate(r['draft'],p,c)))
    report=dict(version=record['version'],content_hash=record['content_hash'],reviewer='independent_codex_agent',
                reviewer_task='test-only/auditor',model=None,model_unavailable_reason='Synthetic test fixture',
                package_id=d['package_id'],calculation_fingerprint=d['calculation_fingerprint'],
                reviewed_claim_ids=[x['claim_id'] for x in d['claims']],decision='pass',findings=[],
                checks=[dict(key=k,result='pass',detail='Synthetic test only') for k in sorted(flow.CHECKS)])
    authorization=dict(decision='approve_analysis',version=record['version'],content_hash=record['content_hash'],
                       human_name='TEST ONLY',verbatim_message='Synthetic authorization, not a real user approval.',
                       conversation_reference='pytest fixture',authorized_at=datetime.now(timezone.utc).isoformat())
    return record,report,authorization,tmp_path/'ledger'


def test_no_audit_or_human_approval_cannot_consume(case):
    r,a,h,root=case
    with pytest.raises(ValueError,match='Publication blocked'): flow.consumer_payload(r,root)
    with pytest.raises(ValueError,match='passing independent'): flow.approve(r,h,root)
    flow.record_audit(r,a,root)
    assert flow.state(r,root)['state']=='validated'
    with pytest.raises(ValueError,match='Publication blocked'): flow.consumer_payload(r,root)


def test_old_presentation_cannot_be_silently_approved_or_consumed(case):
    r,a,h,root=case
    r['code_version']='archived_implementation'
    r['version']=flow.digest({k:r[k] for k in ('draft','prompt_version','code_version')})
    r['analysis_id']=r['draft']['period_id']+'_'+r['version']
    flow.verify_record(r)
    with pytest.raises(ValueError,match='Presentation or instructions changed'):flow.approve(r,h,root)
    with pytest.raises(ValueError,match='Presentation or instructions changed'):flow.consumer_payload(r,root)


@pytest.mark.parametrize('field,value',[('version','wrong'),('content_hash','wrong'),('decision','accept_stage'),('verbatim_message',''),('conversation_reference','')])
def test_stage_acceptance_wrong_version_or_missing_consent_rejected(case,field,value):
    r,a,h,root=case; flow.record_audit(r,a,root);h[field]=value
    with pytest.raises(ValueError): flow.approve(r,h,root)
    assert flow.state(r,root)['state']=='validated'


@pytest.mark.parametrize('mutation',['blocker','self_review','missing_claim','missing_check','wrong_package','failed_check'])
def test_invalid_audit_cannot_validate(case,mutation):
    r,a,h,root=case
    if mutation=='blocker': a['findings']=[dict(id='f',severity='blocking',claim_id='global',issue='Bad claim',recommendation='Fix')]
    if mutation=='self_review': a['reviewer']='analyst'
    if mutation=='missing_claim': a['reviewed_claim_ids'].pop()
    if mutation=='missing_check': a['checks'].pop()
    if mutation=='wrong_package': a['package_id']='wrong'
    if mutation=='failed_check': a['checks'][0]['result']='fail'
    with pytest.raises(ValueError): flow.record_audit(r,a,root)
    assert flow.state(r,root)['state']=='draft'


def test_approval_consumes_only_exact_version_and_no_private_comments(case,inputs,tmp_path):
    r,a,h,root=case;flow.record_audit(r,a,root)
    flow.comment(r,'Private test discussion','TEST',root)
    approval=flow.approve(r,fresh(h),root)
    assert flow.approve(r,h,root)==approval
    payload=flow.consumer_payload(r,root)
    assert 'Private test discussion' not in json.dumps(payload)
    d,p,c=inputs;d['claims'][0]['text_template']+=' Cambio editorial.'
    new,_,_=save(d,p,c,tmp_path/'drafts')
    assert new['version']!=r['version'] and flow.state(new,root)['state']=='draft'
    with pytest.raises(ValueError): flow.consumer_payload(new,root)


def test_changed_content_even_with_old_version_rejected(case):
    r,a,h,root=case;r['draft']['claims'][0]['text_template']+=' Alterado.'
    with pytest.raises(ValueError,match='changed'): flow.state(r,root)


def test_new_failed_audit_invalidates_old_approval(case):
    r,a,h,root=case;flow.record_audit(r,a,root);flow.approve(r,fresh(h),root)
    a['decision']='changes_requested';a['findings']=[dict(id='f',severity='blocking',claim_id='global',issue='New issue',recommendation='Revise')]
    flow.record_audit(r,a,root)
    assert flow.state(r,root)['state']=='draft'
    with pytest.raises(ValueError): flow.consumer_payload(r,root)


def test_event_tampering_fails_closed(case):
    r,a,h,root=case;flow.record_audit(r,a,root)
    path=next((root/'events').glob('*.json'));data=json.loads(path.read_bytes());data['payload']['report']['decision']='changes_requested'
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError,match='hash mismatch'): flow.state(r,root)


def test_interrupted_approval_has_no_partial_transition(case,monkeypatch):
    r,a,h,root=case;flow.record_audit(r,a,root)
    def fail(*args): raise OSError('simulated interrupted write')
    monkeypatch.setattr(flow.os,'link',fail)
    with pytest.raises(OSError):flow.approve(r,fresh(h),root)
    assert flow.state(r,root)['state']=='validated' and not (root/'writer.lock').exists()
    with pytest.raises(ValueError):flow.consumer_payload(r,root)


def test_concurrent_or_abandoned_lock_fails_closed(case):
    r,a,h,root=case;root.mkdir();(root/'writer.lock').write_text('test-only')
    with pytest.raises(ValueError,match='Ledger busy'):flow.record_audit(r,a,root)
    assert flow.events(root)==[]


def test_removed_tail_cannot_restore_prior_approval(case):
    r,a,h,root=case;flow.record_audit(r,a,root);flow.approve(r,fresh(h),root)
    a['decision']='changes_requested';flow.record_audit(r,a,root)
    sorted((root/'events').glob('*.json'))[-1].unlink()
    with pytest.raises(ValueError,match='head mismatch'):flow.consumer_payload(r,root)


def test_revoked_authorization_and_prepared_payload_cannot_be_reused(case):
    r,a,h,root=case;flow.record_audit(r,a,root);flow.approve(r,fresh(h),root)
    payload=flow.consumer_payload(r,root)
    assert flow.verify_handoff(payload,r,root)
    flow.revoke(r,'Synthetic withdrawal','TEST',root)
    with pytest.raises(ValueError):flow.approve(r,h,root)
    with pytest.raises(ValueError):flow.verify_handoff(payload,r,root)
    with pytest.raises(ValueError):flow.approve(r,fresh(h),root)
    h['conversation_reference']='new synthetic consent'
    flow.approve(r,fresh(h),root)
    assert flow.state(r,root)['state']=='approved'
    with pytest.raises(ValueError):flow.verify_handoff(payload,r,root)
    flow.revoke(r,'Synthetic withdrawal','TEST',root)
    assert flow.state(r,root)['state']=='validated'
    with pytest.raises(ValueError):flow.consumer_payload(r,root)


def test_consumer_transaction_holds_lock_against_revocation(case):
    r,a,h,root=case;flow.record_audit(r,a,root);flow.approve(r,fresh(h),root)
    with flow.authorized_consumption(r,root) as payload:
        assert payload['approval_event'] and payload['audit_hash']
        with pytest.raises(ValueError,match='Ledger busy'):flow.revoke(r,'race','TEST',root)


def test_private_sql_projection_rebuild_keeps_events(case):
    r,a,h,root=case;flow.record_audit(r,a,root);before=flow.events(root)
    path=flow.rebuild_projection([r],root)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT state FROM fact_quarterly_analysis').fetchone()==('validated',)
    db.close()
    path.unlink();flow.rebuild_projection([r],root)
    assert flow.events(root)==before


def test_explicit_publication_request_waits_for_exact_passing_audit(case):
    r,a,h,root=case
    flow.request_publication(r,h,root)
    with pytest.raises(ValueError,match='passing independent'):flow.approve(r,h,root)
    flow.record_audit(r,a,root)
    flow.approve(r,h,root)
    assert flow.state(r,root)['state']=='approved'


@pytest.mark.parametrize('invalidation',['revoke','failed_audit'])
def test_pending_publication_request_does_not_survive_invalidation(case,invalidation):
    r,a,h,root=case
    flow.request_publication(r,h,root)
    if invalidation=='revoke':flow.revoke(r,'TEST withdrawal','TEST',root)
    else:
        bad=deepcopy(a);bad['decision']='changes_requested'
        flow.record_audit(r,bad,root)
    flow.record_audit(r,a,root)
    with pytest.raises(ValueError,match='Fresh human consent'):flow.approve(r,h,root)
