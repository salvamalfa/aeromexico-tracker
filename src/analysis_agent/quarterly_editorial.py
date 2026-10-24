"""Replay the retained issuer PDFs supplementing the approved quarterly prose.

Only this fixed issuer/quarter is eligible. Capture receipts remain originals;
no approval is inferred from the review HTML or from these source files.
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path

from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.config import PATHS
from .evidence import compact, digest

FINANCIAL = 'https://ir.aeromexico.com/system/files-encrypted/nasdaq_kms/assets/2026/10/19/16-33-48/AERO%203Q26%20Results.pdf'
TRAFFIC = 'https://ir.aeromexico.com/system/files-encrypted/nasdaq_kms/news/2026/10/05/19-05-12/Sep_2026_Op_Stat_ENG_V3.pdf'


def supplement(sources):
    from .quarterly_release import sha
    if [(s['artifact_id'], s['source_url']) for s in sources] != [('financial_pdf', FINANCIAL), ('september_traffic', TRAFFIC)]:
        raise ValueError('Unexpected editorial sources')
    excerpts = []
    for s in sources:
        path = (PATHS.bronze / s['source_file']).resolve()
        if not path.is_relative_to(PATHS.bronze.resolve()):
            raise ValueError('Editorial source escapes Bronze')
        raw = path.read_bytes()
        proof_raw = Path(str(path) + '.meta.json').read_bytes()
        proof = json.loads(proof_raw)
        if sha(raw) != s['artifact_sha256'] or sha(proof_raw) != s['capture_proof_sha256']:
            raise ValueError('Editorial original or capture receipt changed')
        captured = proof.get('captured_at', proof.get('downloaded_at'))
        if (proof['url'] != s['source_url'] or proof.get('http_status', proof.get('status')) != 200
                or proof['sha256'] != sha(raw) or proof['bytes'] != len(raw) or captured != s['captured_at']):
            raise ValueError('Editorial capture proof disagrees')
        stamp = datetime.fromisoformat(captured)
        if stamp.tzinfo is None or stamp.astimezone(timezone.utc).date().isoformat() > '2026-10-24':
            raise ValueError('Editorial capture beyond cutoff')
        pages = PdfReader(io.BytesIO(raw)).pages
        if len(pages) != (13 if s['artifact_id'] == 'financial_pdf' else 2):
            raise ValueError('Unexpected issuer document length')
        for number, page in enumerate(pages, 1):
            item = dict(artifact_id=s['artifact_id'], locator=f'page={number}',
                        text=compact(page.extract_text() or ''), period_id='2026Q3',
                        source_content_is_untrusted=True)
            if s['artifact_id'] == 'september_traffic':
                item['period_id'] = '2026M09'
            if not item['text']:
                item.update(representation='image_page', visual_review_required=True,
                            text_unavailable_reason='PDF page has no extractable text; claims require independent pixel review and the separately replayed issuer HTML.')
            item['excerpt_id'] = 'exc_' + digest(item)
            excerpts.append(item)
        text = ' '.join(e['text'] for e in excerpts if e['artifact_id'] == s['artifact_id'])
        if s['artifact_id'] == 'september_traffic' and 'Aeroméxico September 2026 Traffic Results' not in text:
            raise ValueError('Wrong monthly context')
    return excerpts


def ytd_metric(base):
    from .quarterly_release import number
    source = next(s for s in base['sources'] if s['artifact_id'] == 'release')
    raw = (PATHS.bronze / source['source_file']).read_bytes()
    table = BeautifulSoup(raw, 'lxml').find_all('table')[1]
    if 'Three Months Ended September 30 Nine Months Ended September 30' not in compact(table.get_text(' ', strip=True)):
        raise ValueError('Quarter/YTD heading changed')
    rows = [[compact(c.get_text(' ', strip=True)) for c in tr.find_all(['td','th'], recursive=False)] for tr in table.find_all('tr')]
    matches = [(i,r) for i,r in enumerate(rows) if r and r[0] == 'Total revenue (USD millions)']
    if len(matches) != 1 or len(matches[0][1]) != 7:
        raise ValueError('Ambiguous revenue row')
    i, values = matches[0]
    excerpt = dict(artifact_id='release', locator=f'table[2]/tr[{i+1}]', text=' | '.join(values),
                   period_id='2026Q3', source_content_is_untrusted=True)
    excerpt['excerpt_id'] = 'exc_' + digest(excerpt)
    if excerpt not in base['excerpts']:
        raise ValueError('Revenue row not in verified base excerpts')
    metric = dict(period_id='2026YTD9', metric_key='revenue_ytd', value=number(values[4])*1e6, unit='USD',
                  excerpt_id=excerpt['excerpt_id'], artifact_id='release', definition='YTD_2026-01-01_2026-09-30',
                  scope='Grupo Aeroméxico consolidated', currency='USD')
    metric['metric_id'] = 'metric_' + digest(metric)
    return metric


def verify(package):
    from .quarterly_release import verify as base_verify
    base = package['editorial_extension']['base_package']
    base_verify(base)
    sources = package['sources'][len(base['sources']):]
    extra = supplement(sources)
    expected = dict(base, sources=base['sources'] + sources, excerpts=base['excerpts'] + extra,
                    metrics=base['metrics'] + [ytd_metric(base)], cutoff_date='2026-10-24',
                    editorial_extension=package['editorial_extension'])
    expected.pop('package_id'); expected.pop('evidence_fingerprint')
    if package['editorial_extension']['implementation_sha256'] != __import__('hashlib').sha256(Path(__file__).read_bytes()).hexdigest():
        raise ValueError('Editorial replay changed')
    if {k:v for k,v in package.items() if k not in ('package_id','evidence_fingerprint')} != expected:
        raise ValueError('Editorial package replay differs')
    if digest(expected) != package['evidence_fingerprint'] or package['package_id'] != '2026Q3_' + digest(expected):
        raise ValueError('Editorial package identity differs')
    return {'status':'passed','package_id':package['package_id'],'metrics':len(package['metrics'])}
