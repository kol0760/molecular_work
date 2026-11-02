import importlib.util
from pathlib import Path
import pytest
ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'tools'/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def test_native_windows_is_supported(monkeypatch):
    m=module('portable');monkeypatch.setattr(m.platform,'system',lambda:'Windows')
    m.validate_environment()

def test_blank_configs_are_private_and_never_overwritten(tmp_path,monkeypatch):
    m=module('init_config');monkeypatch.setattr(m,'ROOT',tmp_path)
    (tmp_path/'config').mkdir()
    for name in ('local','slurm'):(tmp_path/'config'/(name+'.example.json')).write_text('{}')
    m.initialize();p=tmp_path/'.private/slurm.json'
    if __import__('os').name!='nt':assert p.stat().st_mode&0o777==0o600
    p.write_text('{"enabled":false}');m.initialize();assert p.read_text()=='{"enabled":false}'

def test_local_engine_path_is_admin_only_and_checked(tmp_path,monkeypatch):
    m=module('portable');monkeypatch.setattr(m,'ROOT',tmp_path)
    (tmp_path/'.private').mkdir(mode=0o700)
    p=tmp_path/'.private/local.json';p.write_text('{"xtb_executable":"relative/path"}');p.chmod(0o600)
    with pytest.raises(ValueError,match='absolute'):m.local_engine()
    if __import__('os').name!='nt':
        p.chmod(0o644)
        with pytest.raises(ValueError,match='private0600'):m.local_engine()

def test_windows_wrapper_uses_native_python():
    text=(ROOT/'Start-Windows.cmd').read_text().lower()
    assert 'wsl' not in text and 'tools\\portable.py' in text and 'py -3' in text
    assert not any(x in text for x in ('powershell -enc','netsh','firewall','curl','password','token'))
