import copy
import pandas as pd
import pytest
from src.transform.international_routes import aena_period,normalize,validate

AIRPORTS={'MMMX':{'airport_iata':'MEX'},'SKBO':{'airport_iata':'BOG'},'EGLL':{'airport_iata':'LHR'}}
ARTIFACT={'file':'test.json','sha256':'a'*64,'url':'https://example.org','downloaded_at':'2026-09-08'}
CO={'anio':'2026','mes':'06','origen':'MMMX','destino':'SKBO','empresa':'DIFFERENT','explotador':'AMX','tipo_vuelo':'S','trafico':'I','aeropuerto_operacion':'SKBO','tipo_operacion':'LLEGADA','totaloperaciones':'30'}

def test_anac_consecutive_arrays_and_truncated_block():
    from src.ingest.international_routes import anac_rows
    assert anac_rows(b'[{"ANO":"2025"}]\n[{"ANO":"2026"}]')==[{'ANO':'2025'},{'ANO':'2026'}]
    with pytest.raises(ValueError): anac_rows(b'[{"ANO":"2025"}]\n[{"ANO":')

def test_extension_survives_warehouse_rebuild(tmp_path,monkeypatch):
    from types import SimpleNamespace
    import duckdb
    from src.transform import stage6_warehouse as warehouse
    gold=tmp_path/'gold';gold.mkdir();sql=tmp_path/'sql';sql.mkdir()
    for name in ('fact_international_route_observations','bridge_international_route_lineage'):
        pd.DataFrame({'record_id':['rec_test']}).to_parquet(gold/f'{name}.parquet',index=False)
    monkeypatch.setattr(warehouse,'PATHS',SimpleNamespace(data=tmp_path,gold=gold,warehouse=tmp_path/'warehouse.duckdb'))
    monkeypatch.setattr(warehouse,'SQL_DIR',sql)
    monkeypatch.setattr(warehouse,'table_definitions',lambda **kwargs:{})
    warehouse.build_warehouse(max_stage=9)
    with duckdb.connect(str(tmp_path/'warehouse.duckdb')) as c:
        assert c.execute('select count(*) from fact_international_route_observations').fetchone()[0]==1
        assert c.execute('select count(*) from bridge_international_route_lineage').fetchone()[0]==1

def test_actual_operator_and_unsupported_metrics():
    row=normalize('aerocivil',[CO],ARTIFACT,AIRPORTS)[0]
    assert row['operator_icao']=='AMX' and row['marketing_carrier']=='DIFFERENT'
    assert row['passengers'] is None and row['seats'] is None and row['load_factor'] is None
    assert row['departures']==30 and row['source_locator']=='record:1'
    other={**CO,'empresa':'AMX','explotador':'OTHER'}
    assert normalize('aerocivil',[other],ARTIFACT,AIRPORTS)==[]
    assert normalize('aerocivil',[{**CO,'tipo_vuelo':'N'}],ARTIFACT,AIRPORTS)==[]

def test_direction_and_duplicate_fail_closed():
    with pytest.raises(ValueError,match='Direction'): normalize('aerocivil',[{**CO,'tipo_operacion':'SALIDA'}],ARTIFACT,AIRPORTS)
    rows=normalize('aerocivil',[CO,CO],ARTIFACT,AIRPORTS)
    with pytest.raises(ValueError,match='Duplicate route'): validate(pd.DataFrame(rows))

def test_caa_excludes_cancelled_and_rejects_unmatched():
    r={'airline_name':'AEROMEXICO','scheduled_charter':'S','reporting_airport':'HEATHROW','origin_destination':'MEXICO CITY','reporting_period':'202606','arrival_departure':'A','actual_flights_unmatched':'0','number_flights_matched':'30','number_flights_cancelled':'2'}
    row=normalize('caa',[r],ARTIFACT,AIRPORTS)[0]
    assert row['departures']==30 and row['origin_iata']=='MEX'
    assert row['passengers'] is None
    with pytest.raises(ValueError,match='unmatched'):normalize('caa',[{**r,'actual_flights_unmatched':'1'}],ARTIFACT,AIRPORTS)

@pytest.mark.local_data
def test_gold_consumption_and_month_windows(flight_payload):
    payload=flight_payload
    network=payload['international_networks']['2026Q2']
    assert network['totals']==dict(passengers=None,seats=None,departures=None)
    assert network['agent_eligible'] is False
    additions=[r for r in network['routes'] if r['source_label'] in {'Brasil · ANAC','Colombia · Aerocivil','Reino Unido · CAA'}]
    assert {r['source_label'] for r in additions}=={'Brasil · ANAC','Colombia · Aerocivil','Reino Unido · CAA'}
    for route in additions:
        assert set(route['observed_months'])<=set(network['expected_months'])
        if route.get('passengers_estimated'):
            # AFAC + AeroDataBox capacity fills load_factor only for a route
            # whose own months are all capacity-usable, and only with a
            # plausible (0-100%) value; otherwise it stays N/D, same as
            # domestic. It is never hardcoded None just because the
            # passengers themselves came from the estimate.
            assert route['load_factor'] is None or 0<=route['load_factor']<=1
        else:
            # A route ANAC/Aerocivil/CAA measured with real passengers of its
            # own never gets Aeroméxico's estimated occupancy grafted on.
            assert route['load_factor'] is None
        for metric in ('passengers','seats','departures'):
            if route[metric] is not None:
                assert sum(d[metric] for d in route['directions'])==pytest.approx(route[metric])
    uk=next(r for r in additions if 'CAA' in r['source_label'])
    assert uk['observed_months']==['2026M06'] and uk['departures']==60
    assert uk['previous']['departures'] is None
    # CAA publishes flights, not passengers. When the private estimate is
    # present it fills passengers for June alone, the month CAA covers.
    if uk['passengers'] is not None:
        assert uk['passengers_estimated'] is True and uk['months_covered']==1
        assert {m['period_id'] for m in uk['monthly']}=={'2026M06'}
        # Seats and occupancy come from the AFAC + AeroDataBox + flota seat
        # estimate, gated by the same completeness rule as domestic: usable
        # for every direction of the one month CAA covers, so the route
        # shows a number instead of N/D.
        if uk['capacity_estimated']:
            assert uk['seats']==pytest.approx(sum(m['seats'] for m in uk['monthly']))
            assert uk['load_factor'] is None or 0<=uk['load_factor']<=1
            assert all(item['capacity_estimated'] for item in uk['monthly'])
            for direction in uk['directions']:
                assert direction['seats'] is None or direction['seats']>0
        else:
            assert uk['seats'] is None and uk['load_factor'] is None
            assert uk['load_factor_status']=='capacity_incomplete'
    assert payload['route_network']['route_count']==40  # Original BTS scope preserved.
    assert {r['market_key'] for r in network['routes'] if r['source_label']=='AICM · vuelos AM programados'} >= {'MAD<>MEX','BCN<>MEX'}
    assert not any(r.get('operation_status')=='carrier_presence_and_market_observed' for r in network['routes'])
    activity={item['airport_iata']:item for item in network['aena_airport_activity']}
    assert {airport:(item['passengers'],item['operations']) for airport,item in activity.items()}=={
        'MAD':(188_234,780),'BCN':(31_808,156)}
    assert all(item['coverage_status']=='complete' for item in activity.values())
    assert all(item['observed_months']==['2026M04','2026M05','2026M06'] for item in activity.values())
    assert not any(item['origin_iata'] for item in activity.values() if 'origin_iata' in item)
    from src.dashboard.flights_html import integration_flight_payload
    consumer=integration_flight_payload(payload)['route_networks']['2026Q2']
    assert {item['airport_iata'] for item in consumer['aena_airport_activity']}=={'MAD','BCN'}
    assert all(next(route for route in consumer['routes'] if route['market_key']==market)['operation_status']=='assigned_slot_not_flown' for market in ('MAD<>MEX','BCN<>MEX'))
    first_quarter={item['airport_iata']:item for item in payload['international_networks']['2026Q1']['aena_airport_activity']}
    assert first_quarter['MAD']['coverage_status']=='complete'
    assert first_quarter['BCN']['coverage_status']=='partial'
    assert first_quarter['BCN']['observed_months']==['2026M03']


def test_aena_scopes_do_not_assign_market_totals_to_aeromexico():
    airports={}
    company={'Compa��a':'AEROVIAS DE MEXICO, S.A. DE C.','Aeropuerto Base':'ADOLFO SU�REZ MADRID-BARAJAS','Mes':'Abril de 2026','Pasajeros Totales':'63.373'}
    market={'Aeropuerto Escala':'MEXICO CITY /JUAREZ INTERNACIO','Aeropuerto Base':'ADOLFO SU�REZ MADRID-BARAJAS','Mes':'Abril de 2026','Pasajeros Totales':'93.861'}
    own=normalize('aena_company_passengers',[company],ARTIFACT,airports)[0]
    total=normalize('aena_market_passengers',[market],ARTIFACT,airports)[0]
    assert own['observation_scope']=='carrier_airport' and own['operator_icao']=='AMX'
    assert own['airport_iata']=='MAD' and own['origin_iata'] is None
    assert total['observation_scope']=='market_route' and total['operator_icao'] is None
    assert (total['origin_iata'],total['dest_iata'])==('MEX','MAD')
    assert own['passengers']==63_373 and total['passengers']==93_861
    company_ops={'Compañía':'AEROVIAS DE MEXICO, S.A. DE C.','Aeropuerto Base':'ADOLFO SUÁREZ MADRID-BARAJAS','Mes':'Abril de 2026','Operaciones Totales':'258'}
    own_ops=normalize('aena_company_operations',[company_ops],ARTIFACT,airports)[0]
    assert own_ops['metric_key']=='operations' and own_ops['operations']==258
    assert own_ops['departures'] is None and own_ops['origin_iata'] is None


def test_aena_period_comes_from_export_and_rejects_invalid_labels():
    assert aena_period('Abril de 2026')==(2026,4)
    assert aena_period('Julio de 2025')==(2025,7)
    with pytest.raises(ValueError,match='Unexpected Aena period'):
        aena_period('Abril 2026')
