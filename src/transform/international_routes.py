"""Bronze -> validated Silver -> Gold for complementary route authorities.

Run explicitly with python -m src.transform.international_routes after ingestion.
Each normalized row retains its original artifact and array/CSV record locator.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import unicodedata
from pathlib import Path
import duckdb
import pandas as pd
from src.config import PATHS
from src.ingest.stage4_common import write_parquet_atomic
from src.ingest.international_routes import MANIFEST, anac_rows
from src.transform.stage9_lineage import (_make_artifact_id, make_record_id, build_dim_source,
    build_dim_source_artifact, build_bridge_record_lineage, LineageSpec)

TABLE = 'fact_international_route_observations'
VERSION = 'international_routes_v3'

AENA_MONTHS = {
    'ENERO': 1, 'FEBRERO': 2, 'MARZO': 3, 'ABRIL': 4,
    'MAYO': 5, 'JUNIO': 6, 'JULIO': 7, 'AGOSTO': 8,
    'SEPTIEMBRE': 9, 'OCTUBRE': 10, 'NOVIEMBRE': 11, 'DICIEMBRE': 12,
}
AENA_BASE_AIRPORTS = {
    'MADRID-BARAJAS': ('MAD', 'LEMD'),
    'BARCELONA-EL PRAT': ('BCN', 'LEBL'),
}
AENA_COUNTERPARTS = {
    'MEXICO CITY /JUAREZ INTERNACIO': ('MEX', 'MMMX'),
}

def folded(value):
    return ''.join(c for c in unicodedata.normalize('NFKD', str(value)) if not unicodedata.combining(c)).upper()

def number(value):
    if value is None or value == '': return None
    n = float(str(value).replace(',','.'))
    if n < 0 or not __import__('math').isfinite(n): raise ValueError('Invalid nonnegative metric')
    return n


def aena_number(value):
    """Aena uses periods as thousands separators in its Spanish CSV export."""
    text=str(value or '').strip().replace('.', '').replace(' ', '')
    if text=='': return None
    result=float(text.replace(',', '.'))
    if result < 0 or not __import__('math').isfinite(result): raise ValueError('Invalid Aena metric')
    return result


def aena_period(value):
    match=re.fullmatch(r'([A-Z]+)\s+DE\s+(\d{4})', folded(value).strip())
    if not match or match[1] not in AENA_MONTHS:
        raise ValueError(f'Unexpected Aena period: {value!r}')
    return int(match[2]), AENA_MONTHS[match[1]]


def aena_airport(value, mapping):
    label=folded(value)
    for fragment,codes in mapping.items():
        if fragment in label: return codes
    return None

def normalize(source, rows, artifact, airports):
    """Accept only regular, identified operators, keeping unsupported metrics null."""
    result=[]
    for index,r in enumerate(rows,1):
        passengers=seats=departures=operations=None
        observation_scope='carrier_route';airport_iata=None;metric_key='combined'
        if source.startswith('aena_'):
            values=list(r.values())
            if len(values)!=4: raise ValueError('Unexpected Aena export columns')
            if not str(values[2] or '').strip(): continue
            year,month=aena_period(values[2]);marketer=None
            metric=aena_number(values[3])
            if source.startswith('aena_company_'):
                if 'AEROVIAS DE MEXICO' not in folded(values[0]): continue
                base=aena_airport(values[1],AENA_BASE_AIRPORTS)
                if base is None: continue
                operator='AMX';airport_iata,airport_icao=base
                origin=dest=None;observation_scope='carrier_airport'
                definition='Aena carrier activity at Spanish airport; route counterpart unavailable'
            else:
                counterpart=aena_airport(values[0],AENA_COUNTERPARTS)
                base=aena_airport(values[1],AENA_BASE_AIRPORTS)
                if counterpart is None or base is None: continue
                operator=None;origin_iata,origin=counterpart;dest_iata,dest=base
                observation_scope='market_route';airport_icao=None
                definition='Aena all-carrier market between Mexican and Spanish airport; carrier unavailable'
            if source.endswith('_passengers'):
                passengers=metric;metric_key='passengers'
            else:
                operations=metric;metric_key='operations'
            if metric is None or metric<=0: continue
        elif source=='anac':
            name=folded(r.get('EMPRESA_NOME'))
            if not ('AEROVIAS DE MEXICO' in name or 'AEROLITORAL' in name): continue
            if r['GRUPO_DE_VOO']!='REGULAR': continue
            operator='SLI' if 'AEROLITORAL' in name else 'AMX'
            year,month=int(r['ANO']),int(r['MES'])
            origin,dest=r['AEROPORTO_DE_ORIGEM_SIGLA'],r['AEROPORTO_DE_DESTINO_SIGLA']
            passengers=number(r['PASSAGEIROS_PAGOS']);seats=number(r['ASSENTOS']);departures=number(r['DECOLAGENS'])
            definition='paid_passengers; seats and departures as reported by ANAC; load factor not harmonized'
            marketer=None
        elif source=='aerocivil':
            operator=r['explotador']
            if operator not in ('AMX','SLI') or r['tipo_vuelo']!='S' or r['trafico']!='I': continue
            year,month=int(r['anio']),int(r['mes']);origin,dest=r['origen'],r['destino']
            # The Colombian endpoint must be the recording airport. This excludes duplicated remote observations.
            local=origin if origin.startswith('SK') else dest
            if r['aeropuerto_operacion']!=local: raise ValueError('Unexpected reporting airport')
            expected='SALIDA' if local==origin else 'LLEGADA'
            if r['tipo_operacion']!=expected: raise ValueError('Direction/reporting mismatch')
            departures=number(r['totaloperaciones']);marketer=r.get('empresa')
            definition='recorded regular international operations; passengers/seats unavailable'
        elif source=='caa':
            if r['airline_name']!='AEROMEXICO' or r['scheduled_charter']!='S': continue
            if (r['reporting_airport'],r['origin_destination'])!=('HEATHROW','MEXICO CITY'):
                raise ValueError('New CAA endpoint requires explicit airport mapping review')
            operator='AMX';marketer=None
            period=str(r['reporting_period']);year,month=int(period[:4]),int(period[4:6])
            origin,dest=('MMMX','EGLL') if r['arrival_departure']=='A' else ('EGLL','MMMX')
            # Matched flights have reliable punctuality coverage; do not relabel unmatched counts silently.
            if number(r['actual_flights_unmatched'])!=0: raise ValueError('CAA unmatched flights require reconciliation')
            departures=number(r['number_flights_matched'])
            definition='CAA matched operated flights; cancellations excluded; passengers/seats unavailable'
        else: raise ValueError(source)
        if not 1<=month<=12: raise ValueError('Invalid calendar month')
        if observation_scope=='carrier_route':
            if not ((origin.startswith('MM') and not dest.startswith('MM')) or (dest.startswith('MM') and not origin.startswith('MM'))): continue
            if origin not in airports or dest not in airports: raise ValueError(f'Unmapped airport {origin}/{dest}')
            a,b=airports[origin],airports[dest]
            origin_iata,dest_iata=a['airport_iata'],b['airport_iata']
            if departures is None or departures<=0: continue
        elif observation_scope=='carrier_airport':
            origin_iata=dest_iata=None;origin=dest=None
        record_source='aena' if source.startswith('aena_') else source
        row=dict(source_system=record_source,observation_scope=observation_scope,metric_key=metric_key,
                 operator_icao=operator,marketing_carrier=marketer,period_id=f'{year}M{month:02}',
                 origin_iata=origin_iata,dest_iata=dest_iata,origin_icao=origin,dest_icao=dest,
                 airport_iata=airport_iata,
                 passengers=passengers,seats=seats,departures=departures,operations=operations,load_factor=None,
                 metric_definition=definition,source_file=artifact['file'],source_hash=artifact['sha256'],
                 source_url=artifact['url'],downloaded_at=artifact['downloaded_at'],published_at=None,
                 source_locator=f'record:{index}',parser_version=VERSION,agent_eligible=False)
        row['record_id']=make_record_id(TABLE,dict(source=source,sha256=artifact['sha256'],locator=index,parser=VERSION))
        row['artifact_id']=_make_artifact_id(artifact['file'],artifact['sha256'])
        result.append(row)
    return result

def validate(frame):
    if frame.empty: raise ValueError('No international observations')
    if frame.record_id.duplicated().any(): raise ValueError('Duplicate original locator')
    keys=['source_system','observation_scope','metric_key','operator_icao','marketing_carrier','period_id','origin_iata','dest_iata','airport_iata']
    # Aerocivil partitions operations by empresa and explotador. Preserve that
    # native grain; missing/misspelled empresa never replaces the known AOC.
    if frame.duplicated(keys).any(): raise ValueError('Duplicate route-month requires reconciliation')
    for key in ('passengers','seats','departures','operations'):
        if (frame[key].dropna()<0).any(): raise ValueError('Negative metric')
    if frame.agent_eligible.any(): raise ValueError('Historical eligibility not established')

def run():
    selection=json.loads(MANIFEST.read_text(encoding='utf-8'))
    with duckdb.connect(str(PATHS.warehouse),read_only=True) as conn:
        airport_rows=conn.execute('SELECT * FROM dim_airport').df().to_dict('records')
    airports={r['airport_icao']:r for r in airport_rows if r['airport_icao']}
    all_rows=[]
    for source,relative in selection['artifacts'].items():
        path=PATHS.bronze/relative;content=path.read_bytes();meta=json.loads(Path(str(path)+'.meta.json').read_text(encoding='utf-8'))
        sha=hashlib.sha256(content).hexdigest()
        if sha != meta['sha256']: raise ValueError('Bronze hash mismatch')
        artifact={'file':meta['source_file'],'sha256':sha,'url':meta['source_url'],'downloaded_at':meta['downloaded_at']}
        if source=='anac': rows=anac_rows(content)
        elif path.suffix=='.json': rows=json.loads(content)
        else:
            encoding='utf-16' if content.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'
            rows=list(csv.DictReader(io.StringIO(content.decode(encoding,errors='replace'))))
        all_rows.extend(normalize(source,rows,artifact,airports))
    frame=pd.DataFrame(all_rows)
    for key in ('passengers','seats','departures','operations','load_factor'): frame[key]=pd.to_numeric(frame[key],errors='raise').astype(float)
    validate(frame)
    silver=PATHS.silver/'international_routes';silver.mkdir(parents=True,exist_ok=True)
    write_parquet_atomic(frame,silver/'observations.parquet')
    # Gold is constructed by reading the validated persisted Silver, never the research extracts.
    gold=pd.read_parquet(silver/'observations.parquet');validate(gold)
    artifacts=build_dim_source_artifact()
    bridge=build_bridge_record_lineage([
        LineageSpec(record_id=r.record_id,table_name=TABLE,lineage_type='direct_artifact',artifact_ids=(r.artifact_id,))
        for r in gold.itertuples(index=False)],artifacts)
    outputs={TABLE:gold,'bridge_international_route_lineage':bridge,
             'dim_source':build_dim_source(),'dim_source_artifact':artifacts}
    with duckdb.connect(str(PATHS.warehouse)) as conn:
        conn.execute('BEGIN TRANSACTION')
        for name,output in outputs.items():
            write_parquet_atomic(output,PATHS.gold/f'{name}.parquet')
            conn.execute(f'CREATE OR REPLACE TABLE {name} AS SELECT * FROM read_parquet(?)',[str(PATHS.gold/f'{name}.parquet')])
        conn.execute('COMMIT')
    report={'rows':len(gold),'sources':gold.groupby('source_system').size().to_dict(),
            'periods':{s:sorted(g.period_id.unique()) for s,g in gold.groupby('source_system')},
            'silver':str(silver/'observations.parquet'),'gold':str(PATHS.gold/f'{TABLE}.parquet'),
            'checks':['hashes','locators','native-grain uniqueness','nonnegative metrics','operator identity','direction','carrier-airport kept separate from market-route','null unsupported metrics'],
            'historical_agent_eligible':False,'parser_version':VERSION}
    PATHS.quality.mkdir(parents=True,exist_ok=True)
    (PATHS.quality/'international_routes.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
    return report

if __name__=='__main__': run()
