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
