"""The route withdrawal gate protects unrelated analysis and source editions."""
from pathlib import Path
import subprocess

import pytest
from src.publish.official_routes import require_preserved_analysis_implementation, data_identities


def repo(tmp_path: Path):
    subprocess.run(['git','init','-q',str(tmp_path)],check=True)
    p=tmp_path/'web/src/views/analysis/reading.ts';p.parent.mkdir(parents=True);p.write_text('approved renderer')
    p=tmp_path/'data/gold/official.parquet';p.parent.mkdir(parents=True);p.write_bytes(b'official source edition')
    subprocess.run(['git','add','.'],cwd=tmp_path,check=True)
    subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','baseline'],cwd=tmp_path,check=True)
    return subprocess.check_output(['git','rev-parse','HEAD'],cwd=tmp_path,text=True).strip()


@pytest.mark.parametrize('path',[
    'web/src/views/analysis/reading.ts','web/src/main.ts','src/analysis_agent/lifecycle.py',
    'src/config.py','src/web_export/analysis.py','contracts/web/flights.schema.json',
])
def test_route_gate_refuses_changes_to_approval_analysis_or_shared_renderer_inputs(tmp_path,path):
    commit=repo(tmp_path)
    target=tmp_path/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text('modified')
    with pytest.raises(ValueError,match='protected analysis input'):
        require_preserved_analysis_implementation(tmp_path,commit)


def test_route_gate_allows_route_interface_but_refuses_refreshed_gold(tmp_path):
    commit=repo(tmp_path)
    p=tmp_path/'web/src/views/flights/table.ts';p.parent.mkdir(parents=True);p.write_text('official routes only')
    require_preserved_analysis_implementation(tmp_path,commit)
    (tmp_path/'data/gold/official.parquet').write_bytes(b'refreshed edition')
    with pytest.raises(ValueError,match='Gold source editions'):
        require_preserved_analysis_implementation(tmp_path,commit)


def test_data_comparison_binds_every_non_flight_payload_and_ignores_only_routes(tmp_path):
    data=tmp_path/'data/v1';(data/'flights').mkdir(parents=True)
    (data/'executive.json').write_text('{"passengers":10}')
    (data/'flights/quarters.json').write_text('{}')
    before=data_identities(tmp_path)
    (data/'flights/quarters.json').write_text('{"official":true}')
    assert data_identities(tmp_path)==before
    (data/'executive.json').write_text('{"passengers":11}')
    assert data_identities(tmp_path)!=before


@pytest.mark.parametrize("metric", ["passengers", "seats", "departures", "load_factor"])
def test_route_gate_rejects_changed_official_values_even_with_unchanged_aggregate_files(tmp_path, metric):
    import json
    from src.publish.official_routes import require_retained_official_metrics
    old = tmp_path / "old"; new = tmp_path / "new"
    route = {"market_key":"LAX<>MEX", "source_label":"Estados Unidos · BTS T-100",
             "operation_status":"operated_observed", "passengers":10,"seats":20,
             "departures":1,"load_factor":.5,"origin":{"iata":"MEX"},"destination":{"iata":"LAX"},"previous":{}}
    for root in (old,new):
        base = root / "data/v1/flights"; (base / "international").mkdir(parents=True)
        (base / "quarters.json").write_text(json.dumps({"quarters":[],"monthly_passengers":{},"route_network":{}}))
        (base / "international/2026Q2.json").write_text(json.dumps({"routes":[route]}))
    require_retained_official_metrics(old,new)
    route[metric] += 1
    (new / "data/v1/flights/international/2026Q2.json").write_text(json.dumps({"routes":[route]}))
    with pytest.raises(ValueError,match="changed retained"):
        require_retained_official_metrics(old,new)


@pytest.mark.parametrize("runtime_change", [False, True])
def test_shared_domain_exception_accepts_only_type_erased_changes(tmp_path, runtime_change):
    import shutil
    from src.config import PATHS
    from src.publish.official_routes import require_type_only_domain_change
    compiler = PATHS.root / "web/node_modules"
    if not (compiler / "typescript").is_dir() or not shutil.which("node"):
        pytest.skip("Locked web TypeScript dependencies are not installed in the Python-only runner")
    repo(tmp_path)
    domain = tmp_path / "web/src/types/domain.ts";domain.parent.mkdir(parents=True,exist_ok=True)
    domain.write_text("export interface Metric { value: number; }\n")
    subprocess.run(['git','add','.'],cwd=tmp_path,check=True)
    subprocess.run(['git','-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','types'],cwd=tmp_path,check=True)
    commit = subprocess.check_output(['git','rev-parse','HEAD'],cwd=tmp_path,text=True).strip()
    (tmp_path / "web/node_modules").symlink_to(compiler,target_is_directory=True)
    domain.write_text("export interface Metric { value: number; source?: string; }\n"+
                      ("export const sideEffect = 1;\n" if runtime_change else ""))
    if runtime_change:
        with pytest.raises(ValueError,match="runtime code"):
            require_type_only_domain_change(tmp_path,commit)
    else:
        require_type_only_domain_change(tmp_path,commit)


def test_restored_directions_require_exact_trusted_gold_and_aena_stays_unchanged(tmp_path, monkeypatch):
    import json
    from types import SimpleNamespace
    import pandas as pd
    from src.publish import official_routes as module
    old=tmp_path/'old';new=tmp_path/'new';gold=tmp_path/'gold';gold.mkdir()
    monkeypatch.setattr(module,'PATHS',SimpleNamespace(gold=gold))
    pd.DataFrame([
        {'period_id':'2026M04','origin_iata':origin,'dest_iata':dest,
         'observation_status':'assigned_slot_not_flown','scheduled_movements':91}
        for origin,dest in [('AMS','MEX'),('MEX','AMS')]
    ]).to_parquet(gold/'fact_aicm_international_scheduled_route_movements.parquet',index=False)
    route={'market_key':'AMS<>MEX','source_label':'AICM · vuelos AM programados',
           'operation_status':'assigned_slot_not_flown','passengers':1000,'seats':2000,
           'departures':182,'load_factor':.5,'origin':{'iata':'AMS'},'destination':{'iata':'MEX'},
           'passengers_estimated':True,'capacity_estimated':True,'directions':[],'previous':{}}
    for root in (old,new):
        base=root/'data/v1/flights';(base/'international').mkdir(parents=True)
        (base/'quarters.json').write_text(json.dumps({'quarters':[],'monthly_passengers':{},'route_network':{}}))
    before={'expected_months':['2026M04'],'aena_airport_activity':[],'routes':[route]}
    (old/'data/v1/flights/international/2026Q2.json').write_text(json.dumps(before))
    actual=dict(route,passengers=None,seats=None,load_factor=None,passengers_estimated=False,capacity_estimated=False)
    actual['directions']=[{'origin_iata':a,'destination_iata':b,'departures':91}
                          for a,b in [('AMS','MEX'),('MEX','AMS')]]
    document=dict(before,routes=[actual])
    target=new/'data/v1/flights/international/2026Q2.json'
    target.write_text(json.dumps(document))
    module.require_retained_official_metrics(old,new)
    actual['directions'][0]['departures']=90
    actual['directions'][1]['departures']=92
    target.write_text(json.dumps(document))
    with pytest.raises(ValueError,match='direction details'):
        module.require_retained_official_metrics(old,new)
    actual['directions'][0]['departures']=actual['directions'][1]['departures']=91
    document['aena_airport_activity']=[{'airport_iata':'MAD','operations':1}]
    target.write_text(json.dumps(document))
    with pytest.raises(ValueError,match='aena_airport_activity'):
        module.require_retained_official_metrics(old,new)
