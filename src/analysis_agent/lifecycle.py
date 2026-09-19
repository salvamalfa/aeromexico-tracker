"""Stage 17: local audit/review/approval ledger. No publication operation."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import hashlib
import os
from pathlib import Path
import re
import sqlite3
import tempfile

from src.config import PATHS
from .evidence import canonical, digest
from .analyst import load_inputs, validate, SKILL

ROOT = PATHS.root / 'analysis_runs/lifecycle'
CHECKS = {'numbers', 'units', 'comparisons', 'semantic_support', 'causality', 'contradictions', 'editorial', 'lineage', 'temporal'}


def verify_record(record):
    if record['content_hash'] != digest(record['draft']):
        raise ValueError('Draft content changed after versioning')
    version = digest({k: record[k] for k in ('draft', 'prompt_version', 'code_version')})
    if version != record['version'] or record['analysis_id'] != record['draft']['period_id'] + '_' + version:
        raise ValueError('Version identity mismatch')
    if not re.fullmatch(r'\d{4}Q[1-4]', record['draft']['period_id']):
        raise ValueError('Invalid period')


def verified_inputs(record):
    verify_record(record)
    d = record['draft']
    if not re.fullmatch(r'\d{4}Q[1-4]_[a-f0-9]{64}', d['package_id']) or not re.fullmatch(r'[a-f0-9]{64}', d['calculation_fingerprint']):
        raise ValueError('Invalid input identity')
    p,c = load_inputs(PATHS.root/'analysis_runs/evidence'/f"{d['package_id']}.json",
                      PATHS.root/'analysis_runs/quantitative'/f"{d['calculation_fingerprint']}.json")
    return p,c,validate(d,p,c)


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd,name = tempfile.mkstemp(dir=path.parent, suffix='.tmp')
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(canonical(value)); stream.flush(); os.fsync(stream.fileno())
        os.link(name,path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextmanager
def writer(root):
    root.mkdir(parents=True, exist_ok=True)
    lock = root/'writer.lock'
    try:
        stream=lock.open('x')
    except FileExistsError:
        raise ValueError('Ledger busy or interrupted: inspect writer.lock before manual recovery')
    try:
        stream.write(str(os.getpid())); stream.close()
        yield
    finally:
        lock.unlink(missing_ok=True)


def events(root=ROOT):
    root=Path(root); previous=None; result=[]
    for index,path in enumerate(sorted((root/'events').glob('*.json')),1):
        event=json.loads(path.read_bytes())
        expected=digest({k:v for k,v in event.items() if k!='event_hash'})
        if event.get('sequence')!=index or event.get('previous_hash')!=previous or event.get('event_hash')!=expected or path.name!=f'{index:08d}_{expected}.json':
            raise ValueError('Ledger sequence/hash mismatch; do not promote')
        previous=expected; result.append(event)
    head=root/'head.json'
    if result or head.exists():
        if not head.exists() or json.loads(head.read_bytes())!={'sequence':len(result),'event_hash':previous}:
            raise ValueError('Ledger head mismatch; inspect interruption or removed events')
    return result


def advance_head(root,event):
    # If interrupted between event and head, reads fail closed until inspected.
    fd,name=tempfile.mkstemp(dir=root,suffix='.head.tmp')
    try:
        with os.fdopen(fd,'wb') as stream:
            stream.write(canonical({'sequence':event['sequence'],'event_hash':event['event_hash']}))
            stream.flush();os.fsync(stream.fileno())
        os.replace(name,root/'head.json')
    finally:
        Path(name).unlink(missing_ok=True)


def append(action, record, payload, actor, root=ROOT):
    root=Path(root)
    with writer(root):
        history=events(root)
        # Duplicate retries do not create a new transition or date.
        signature={'action':action,'version':record['version'],'payload':payload,'actor':actor}
        candidates=list(reversed(history))
        if action=='revoke':
            candidates=[e for e in candidates if e['version']==record['version'] and e['action']!='comment'][:1]
        for old in candidates:
            if {k:old[k] for k in signature}==signature:
                return old
        event=dict(signature, period_id=record['draft']['period_id'], sequence=len(history)+1,
                   previous_hash=history[-1]['event_hash'] if history else None,
                   created_at=datetime.now(timezone.utc).isoformat())
        event['event_hash']=digest(event)
        atomic_json(root/'events'/f"{event['sequence']:08d}_{event['event_hash']}.json",event)
        advance_head(root,event)
        return event


def audit_contract(report, record):
    verify_record(record)
    if report.get('version')!=record['version'] or report.get('content_hash')!=record['content_hash']:
        raise ValueError('Audit targets another version/content')
    if report.get('reviewer')!='independent_codex_agent' or not report.get('reviewer_task'):
        raise ValueError('Independent reviewer provenance required')
    if report.get('model') is None and not report.get('model_unavailable_reason'):
        raise ValueError('Unknown audit model requires reason')
    if report.get('package_id')!=record['draft']['package_id'] or report.get('calculation_fingerprint')!=record['draft']['calculation_fingerprint']:
        raise ValueError('Audit input mismatch')
    ids={c['claim_id'] for c in record['draft']['claims']}
    if set(report.get('reviewed_claim_ids',[]))!=ids:
        raise ValueError('Audit must review every claim')
    checked={c['key'] for c in report.get('checks',[]) if c.get('result') in ('pass','limited','fail') and c.get('detail')}
    if checked!=CHECKS:
        raise ValueError('Incomplete audit checklist')
    seen=set()
    for finding in report['findings']:
        if finding['id'] in seen or finding['severity'] not in ('blocking','warning') or finding['claim_id'] not in ids|{'global'} or not finding.get('issue') or not finding.get('recommendation'):
            raise ValueError('Invalid finding')
        seen.add(finding['id'])
    blockers=any(f['severity']=='blocking' for f in report['findings']) or any(c['result']=='fail' for c in report['checks'])
    if report.get('decision') not in ('pass','changes_requested') or (report['decision']=='pass' and blockers):
        raise ValueError('Blocking observations cannot pass audit')


def record_audit(record, report, root=ROOT):
    verified_inputs(record)
    audit_contract(report,record)
    return append('audit',record,{'report':report,'audit_hash':digest(report)},report['reviewer_task'],root)


def state(record, root=ROOT):
    verify_record(record)
    history=[e for e in events(root) if e['version']==record['version']]
    status='draft'; audit=None; approval=None
    for index,event in enumerate(history):
        if event['action']=='audit':
            report=event['payload']['report']; audit_contract(report,record)
            if digest(report)!=event['payload']['audit_hash']:
                raise ValueError('Audit hash mismatch')
            audit=event['payload']; approval=None
            status='validated' if report['decision']=='pass' else 'draft'
        elif event['action']=='approval':
            authorization=event['payload']['authorization']
            check_authorization(authorization,record)
            fresh_authorization(authorization,history[:index])
            if status!='validated' or event['payload']['audit_hash']!=audit['audit_hash']:
                raise ValueError('Approval has no matching passing audit')
            approval=event; status='approved'
        elif event['action']=='revoke':
            status='validated' if audit and audit['report']['decision']=='pass' else 'draft'; approval=None
        elif event['action']=='publication_request':
            check_authorization(event['payload']['authorization'],record)
        elif event['action']!='comment':
            raise ValueError('Unknown lifecycle event')
    publication=None
    if status=='approved':
        # A publication receipt proves consumption only while the target bytes
        # still match and the exact approval remains current.
        for path in sorted((Path(root)/'publications').glob('*.published.json')):
            candidate=json.loads(path.read_bytes())
            intent={k:v for k,v in candidate.items() if k!='published_at'}
            if path.name!=digest(intent)+'.published.json':
                raise ValueError('Publication receipt hash mismatch')
            pairs=list(zip(candidate['versions'],candidate['approval_events']))
            target=Path(candidate['output'])
            if (record['version'],approval['event_hash']) in pairs and target.is_file() and hashlib.sha256(target.read_bytes()).hexdigest()==candidate['html_sha256']:
                publication=candidate;status='published'
    return {'state':status,'version':record['version'],'audit':audit,'approval':approval,'events':history,'publication':publication}


def check_authorization(authorization, record):
    if authorization.get('decision')!='approve_analysis' or authorization.get('version')!=record['version'] or authorization.get('content_hash')!=record['content_hash']:
        raise ValueError('Explicit approval must target this exact analysis version')
    for field in ('human_name','verbatim_message','conversation_reference','authorized_at'):
        if not isinstance(authorization.get(field),str) or not authorization[field].strip():
            raise ValueError('Missing human authorization provenance')
    timestamp=datetime.fromisoformat(authorization['authorized_at'])
    if timestamp.tzinfo is None or timestamp>datetime.now(timezone.utc):
        raise ValueError('Authorization timestamp must be real and timezone-aware')


def approve(record, authorization, root=ROOT):
    authorization=json.loads(canonical(authorization))
    require_current_presentation(record)
    verified_inputs(record)
    check_authorization(authorization,record)
    current=state(record,root)
    if current['state'] in ('approved','published') and current['approval']['payload']['authorization']==authorization:
        return current['approval']
    if current['state']!='validated':
        raise ValueError('Analysis requires a passing independent audit before approval')
    # append rechecks under lock via expected audit to avoid approval racing an audit.
    return approval_event(record,authorization,current['audit']['audit_hash'],root)


def approval_event(record, authorization, audit_hash, root):
    root=Path(root)
    with writer(root):
        current=state(record,root)
        if current['state']!='validated' or current['audit']['audit_hash']!=audit_hash:
            raise ValueError('Audit changed during approval; retry review')
        fresh_authorization(authorization,current['events'])
        history=events(root)
        event=dict(action='approval',version=record['version'],period_id=record['draft']['period_id'],
                   payload={'authorization':authorization,'audit_hash':audit_hash},actor=authorization['human_name'],
                   sequence=len(history)+1,previous_hash=history[-1]['event_hash'] if history else None,
                   created_at=datetime.now(timezone.utc).isoformat())
        event['event_hash']=digest(event)
        atomic_json(root/'events'/f"{event['sequence']:08d}_{event['event_hash']}.json",event)
        advance_head(root,event)
        return event


def fresh_authorization(authorization, history):
    boundary=max(e['created_at'] for e in history if e['action'] in ('audit','revoke'))
    if datetime.fromisoformat(authorization['authorized_at']) <= datetime.fromisoformat(boundary):
        # Explicit publication requests may await the first passing audit of
        # these exact bytes. A failed audit or revocation cancels that request.
        requests=[i for i,e in enumerate(history) if e['action']=='publication_request' and e['payload']['authorization']==authorization]
        pending=history[requests[-1]+1:] if requests else []
        if not requests or not any(e['action']=='audit' for e in pending) or any(e['action'] not in ('audit','comment') or (e['action']=='audit' and e['payload']['report']['decision']!='pass') for e in pending):
            raise ValueError('Fresh human consent after the latest audit/revocation is required')
    if any(e['action']=='approval' and e['payload']['authorization']['conversation_reference']==authorization['conversation_reference'] for e in history):
        raise ValueError('A previously used consent message cannot be reused after invalidation')


def request_publication(record, authorization, root=ROOT):
    """Record actual user consent for exact reviewed bytes, pending audit only."""
    require_current_presentation(record)
    verified_inputs(record)
    check_authorization(authorization,record)
    if state(record,root)['state'] not in ('draft','validated'):
        raise ValueError('Publication request is only for an unpublished review version')
    return append('publication_request',record,{'authorization':authorization},authorization['human_name'],root)


def comment(record, text, actor, root=ROOT):
    verify_record(record)
    if not text.strip() or not actor.strip(): raise ValueError('Comment and author required')
    return append('comment',record,{'text':text},actor,root)


def revoke(record, reason, actor, root=ROOT):
    verify_record(record)
    if not reason.strip() or not actor.strip():raise ValueError('Revocation reason and actor required')
    return append('revoke',record,{'reason':reason},actor,root)


def consumer_payload(record, root=ROOT):
    """Fail-closed handoff contract for stage 18. No writes or publication here."""
    require_current_presentation(record)
    _,_,checks=verified_inputs(record)
    current=state(record,root)
    if current['state'] not in ('approved','published'):
        raise ValueError('Publication blocked: exact analysis version has no human approval')
    d=record['draft']
    payload={'period_id':d['period_id'],'version':record['version'],'content_hash':record['content_hash'],
            'thesis':checks['rendered'][d['thesis_claim_id']],
            'summary':[checks['rendered'][cid] for cid in d['summary_claim_ids']],
            'summary_format':d.get('summary_format','paragraphs'),
            'summary_items':[{'claim_id':cid,'lead':next(x for x in d['claims'] if x['claim_id']==cid).get('lead'),
                              'emphasis':next(x for x in d['claims'] if x['claim_id']==cid).get('emphasis',[]),
                              'text':checks['rendered'][cid]} for cid in d['summary_claim_ids']],
            'sections':[{'title':s['title'],'paragraphs':[checks['rendered'][cid] for cid in s['claim_ids']]} for s in d['sections']],
            'claims':[{'claim_id':claim['claim_id'],'type':claim['type'],'text':checks['rendered'][claim['claim_id']],
                       'calculation_ids':sorted(set([b['calculation_id'] for b in claim.get('bindings',{}).values()]+claim.get('support_calculation_ids',[]))),
                       'evidence_ids':claim.get('evidence_ids',[])} for claim in d['claims']],
            'evidence_fingerprint':d['evidence_fingerprint'],'package_id':d['package_id'],
            'approval_event':current['approval']['event_hash'],'audit_hash':current['audit']['audit_hash'],
            'version_event_head':current['events'][-1]['event_hash']}
    payload['context']=[checks['rendered'][cid] for cid in d.get('context_claim_ids',[])]
    return payload


def require_current_presentation(record):
    code=digest({name:hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                 for name in ('analyst.py','stage16_html.py')})
    if record['code_version']!=code or record['prompt_version']!=hashlib.sha256(SKILL.read_bytes()).hexdigest():
        raise ValueError('Presentation or instructions changed: create and audit a new version before approval/consumption')


def verify_handoff(payload, record, root=ROOT):
    """Call immediately before stage 18 writes. A prepared payload is not authority."""
    if payload!=consumer_payload(record,root):
        raise ValueError('Prepared payload or approval changed; prepare again')
    return True


@contextmanager
def authorized_consumption(record, root=ROOT):
    """Hold the ledger writer lock through the future atomic consumer write."""
    with writer(Path(root)):
        yield consumer_payload(record,root)


def materialize(records, root=ROOT):
    """Private, regenerable projection. Never Gold; events remain authoritative."""
    rows=[]
    for record in records:
        current=state(record,root); d=record['draft']
        rows.append({'analysis_id':record['analysis_id'],'period_id':d['period_id'],'version':record['version'],
                     'state':current['state'],'content_hash':record['content_hash'],'content':d,
                     'created_at':record['created_at'],'model':d['model'],
                     'audit_hash':current['audit']['audit_hash'] if current['audit'] else None,
                     'approval_event':current['approval']['event_hash'] if current['approval'] else None})
    return {'table':'fact_quarterly_analysis','scope':'private_local','rows':rows}


def rebuild_projection(records, root=ROOT):
    """Rebuild local SQL tables from immutable records and ledger; no private Gold."""
    root=Path(root)
    with writer(root):
        table=materialize(records,root)
        fd,name=tempfile.mkstemp(dir=root,suffix='.sqlite.tmp');os.close(fd)
        try:
            db=sqlite3.connect(name)
            try:
                db.execute('CREATE TABLE fact_quarterly_analysis (analysis_id TEXT PRIMARY KEY, period_id TEXT, version TEXT UNIQUE, state TEXT, content_hash TEXT, content_json TEXT, created_at TEXT, model TEXT, audit_hash TEXT, approval_event TEXT)')
                for row in table['rows']:
                    db.execute('INSERT INTO fact_quarterly_analysis VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (row['analysis_id'],row['period_id'],row['version'],row['state'],row['content_hash'],canonical(row['content']).decode(),row['created_at'],row['model'],row['audit_hash'],row['approval_event']))
                db.execute('CREATE TABLE analysis_events (sequence INTEGER PRIMARY KEY, event_hash TEXT UNIQUE, version TEXT, action TEXT, event_json TEXT)')
                for event in events(root):
                    db.execute('INSERT INTO analysis_events VALUES (?,?,?,?,?)',(event['sequence'],event['event_hash'],event['version'],event['action'],canonical(event).decode()))
                db.commit()
            finally:
                db.close()
            os.replace(name,root/'analysis.sqlite')
        finally:
            Path(name).unlink(missing_ok=True)
    return root/'analysis.sqlite'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('operation',choices=['status','audit','comment','approve','revoke','check-consumption'])
    p.add_argument('--record',required=True);p.add_argument('--input')
    args=p.parse_args();record=json.loads(Path(args.record).read_bytes())
    if args.operation=='audit':
        record_audit(record,json.loads(Path(args.input).read_bytes()))
    elif args.operation=='approve':
        approve(record,json.loads(Path(args.input).read_bytes()))
    elif args.operation=='comment':
        value=json.loads(Path(args.input).read_bytes());comment(record,value['text'],value['actor'])
    elif args.operation=='revoke':
        value=json.loads(Path(args.input).read_bytes());revoke(record,value['reason'],value['actor'])
    elif args.operation=='check-consumption':
        consumer_payload(record)
    s=state(record)
    if args.operation in ('audit','comment','approve','revoke'):
        identities={(e['period_id'],e['version']) for e in events()}
        records=[json.loads((PATHS.root/'analysis_runs/drafts'/period/(version+'.json')).read_bytes()) for period,version in sorted(identities)]
        rebuild_projection(records)
    print(json.dumps({'state':s['state'],'version':s['version'],'event_count':len(s['events'])}))


if __name__=='__main__': main()
