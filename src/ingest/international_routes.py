"""Explicit, bounded downloads for the international route increment."""
from __future__ import annotations

import json
import csv
import io
import re
from datetime import datetime, timezone
from pathlib import Path
import httpx
from src.common.storage import save_bronze
from src.config import PATHS

ANAC_URL = ('https://sistemas.anac.gov.br/dadosabertos/Voos%20e%20opera%C3%A7%C3%B5es%20a%C3%A9reas/'
            'Dados%20Estat%C3%ADsticos%20do%20Transporte%20A%C3%A9reo/Dados_Estatisticos_2021_a_2030.json')
CO_URL = 'https://www.datos.gov.co/resource/jh8x-n6h6.json'
CAA_URL = 'https://www.caa.co.uk/Documents/Download/26825/de96ee2c-f138-4043-b7d5-08a1edf7a5c8/1744'
MANIFEST = PATHS.bronze / 'international_routes' / 'selection.json'
AENA_URL = 'https://www.aena.es/es/estadisticas/consultas-personalizadas.html'

def anac_content(client):
    """Assemble the full original using HTTP ranges bound to one Last-Modified/ETag."""
    import re
    first=client.get(ANAC_URL,headers={'Range':'bytes=0-4194303','Accept-Encoding':'identity'})
    first.raise_for_status()
    if first.status_code==200: return first.content, first.headers
    match=re.fullmatch(r'bytes 0-(\d+)/(\d+)',first.headers.get('content-range',''))
    if not match or len(first.content)!=int(match[1])+1: raise ValueError('Invalid initial range')
    size=int(match[2]); validator=first.headers.get('etag') or first.headers.get('last-modified')
    if not validator: raise ValueError('Cannot bind ranged download to a version')
    from concurrent.futures import ThreadPoolExecutor
    import hashlib
    cache=PATHS.root/'tmp'/'international_route_download'/hashlib.sha256(validator.encode()).hexdigest()
    cache.mkdir(parents=True,exist_ok=True)
    def block(offset):
        end=min(offset+4194303,size-1);path=cache/f'{offset}-{end}.part'
        if path.exists() and path.stat().st_size==end-offset+1:return path.read_bytes()
        for attempt in range(3):
            try:
                r=client.get(ANAC_URL,headers={'Range':f'bytes={offset}-{end}','If-Range':validator,'Accept-Encoding':'identity'})
                r.raise_for_status()
                if r.status_code!=206 or r.headers.get('content-range')!=f'bytes {offset}-{end}/{size}': raise ValueError('Range/version changed')
                if (r.headers.get('etag') or r.headers.get('last-modified'))!=validator or len(r.content)!=end-offset+1: raise ValueError('Inconsistent range')
                path.write_bytes(r.content);return r.content
            except httpx.HTTPError:
                if attempt==2: raise
    chunks=[first.content]
    with ThreadPoolExecutor(max_workers=3) as pool:
        for content in pool.map(block,range(len(first.content),size,4194304)):
            chunks.append(content)
            if len(chunks)%10==0: print('ANAC bytes',sum(map(len,chunks)),'/',size,flush=True)
    return b''.join(chunks),first.headers

def anac_rows(content):
    """The official file can contain consecutive JSON arrays; consume every byte."""
    text=content.decode('utf-8-sig');decoder=json.JSONDecoder();offset=0;rows=[]
    while offset<len(text):
        while offset<len(text) and text[offset].isspace():offset+=1
        if offset==len(text):break
        value,end=decoder.raw_decode(text,offset)
        if not isinstance(value,list): raise ValueError('Expected ANAC array block')
        rows.extend(value);offset=end
    return rows

def download():
    selection = {}
    with httpx.Client(follow_redirects=True, timeout=120) as client:
        for source, url, ext in [('anac', ANAC_URL, 'json'), ('aerocivil', CO_URL, 'json'), ('caa', CAA_URL, 'csv')]:
            params = None
            if source == 'aerocivil':
                where = "anio >= '2025' AND anio <= '2026' AND (explotador='AMX' OR explotador='SLI')"
                count = client.get(url, params={'$where': where, '$select':'count(*)'}); count.raise_for_status()
                expected = int(count.json()[0]['count'])
                if expected > 50000: raise ValueError('Increase explicit bounded pagination before downloading')
                params = {'$where':where, '$limit':50000, '$order':'anio,mes,aeropuerto_operacion,origen,destino,empresa,explotador,tipo_vuelo,tipo_operacion'}
            print('Downloading', source, flush=True)
            if source=='anac':
                content,headers=anac_content(client)
                path=save_bronze(content,'international_routes',source,'20260908',ext,url,'httpx',
                    notes='Complete original assembled from contiguous HTTP ranges; same version validator and exact byte count. Historical publication unverified.',content_type=headers.get('content-type',''))
                rows=anac_rows(content)
                selection[source]=str(path.relative_to(PATHS.bronze))
                print(source,len(content),path.name,flush=True)
                continue
            with client.stream('GET', url, params=params) as response:
                response.raise_for_status()
                if response.status_code != 200: raise ValueError('Partial responses cannot enter this increment')
                chunks = []; size = 0
                for chunk in response.iter_bytes():
                    chunks.append(chunk); size += len(chunk)
                content = b''.join(chunks)
                if response.headers.get('content-length') and not response.headers.get('content-encoding'):
                    if size != int(response.headers['content-length']): raise ValueError('Truncated download')
                if ext == 'json':
                    rows = json.loads(content)
                    if not isinstance(rows,list): raise ValueError('Expected original record array')
                    if source == 'aerocivil' and len(rows) != expected: raise ValueError('Query count mismatch')
                path = save_bronze(content,'international_routes',source,'20260908',ext,str(response.url),'httpx',
                    notes='Full response. Aerocivil filtered 2025-2026 AMX/SLI; ANAC entire 2021-2030 block; CAA June 2026. Historical publication unverified.',
                    content_type=response.headers.get('content-type',''))
                selection[source] = str(path.relative_to(PATHS.bronze))
                print(source, size, path.name, flush=True)
    # Only promote a complete selection after every source is downloaded.
    MANIFEST.parent.mkdir(parents=True,exist_ok=True)
    receipt={'selected_at':datetime.now(timezone.utc).isoformat(),'artifacts':selection}
    version=MANIFEST.with_name('selection-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
    version.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    MANIFEST.write_text(json.dumps(receipt,indent=2),encoding='utf-8')


def import_aena_exports(exports: dict[str, Path]) -> dict[str, str]:
    """Preserve four user-exported Aena tables and add them to the active selection.

    The Aena application exports UTF-16 CSV files.  The four required keys keep
    carrier-at-airport observations separate from all-carrier route markets.
    """

    required = {
        'aena_company_operations',
        'aena_company_passengers',
        'aena_market_operations',
        'aena_market_passengers',
    }
    if set(exports) != required:
        raise ValueError(f'Aena export keys must be exactly {sorted(required)}')
    selection = json.loads(MANIFEST.read_text(encoding='utf-8')) if MANIFEST.exists() else {'artifacts': {}}
    selected = dict(selection.get('artifacts', {}))
    for key, input_path in exports.items():
        content = Path(input_path).read_bytes()
        # Decode now only to fail before registering an unusable original.
        text = content.decode('utf-16')
        if '\n' not in text or ',' not in text.splitlines()[0]:
            raise ValueError(f'Unexpected Aena CSV structure: {input_path}')
        rows = list(csv.DictReader(io.StringIO(text)))
        periods = {str(row.get('Mes', '')).strip() for row in rows if str(row.get('Mes', '')).strip()}
        expected_months = {'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio'}
        observed_months = set()
        for period in periods:
            match = re.fullmatch(r'([A-Za-z]+)\s+de\s+(\d{4})', period)
            if not match or match[2] != '2026' or match[1] not in expected_months:
                raise ValueError(f'Unexpected Aena export period: {period!r}')
            observed_months.add(match[1])
        if observed_months != expected_months:
            raise ValueError(f'Aena export months are incomplete: {sorted(observed_months)}')
        path = save_bronze(
            content, 'aena', key.removeprefix('aena_'), '2026M01-2026M07', 'csv',
            AENA_URL, 'computer_use',
            notes=(
                'Aena authenticated custom-query export for 2026, downloaded through Chrome. '
                'Carrier and market route tables are separate and must not be joined to assign '
                'market traffic to Aeromexico. Historical availability at 2026-07-13 unverified.'
            ),
            content_type='text/csv; charset=utf-16',
            relative_dir='international_routes',
            http_status=0,  # Browser export: response status was not independently captured.
        )
        selected[key] = str(path.relative_to(PATHS.bronze))
    receipt = {'selected_at': datetime.now(timezone.utc).isoformat(), 'artifacts': selected}
    version = MANIFEST.with_name('selection-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'.json')
    version.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    MANIFEST.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    return {key: selected[key] for key in sorted(required)}

if __name__ == '__main__': download()
