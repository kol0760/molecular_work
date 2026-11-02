from pathlib import Path
import pytest
from backend.chemistry import parse_xyz, validate_request, parse_result
WATER = '3\nwater\nO 0 0 0\nH 0.76 0 0.59\nH -0.76 0 0.59\n'

def test_xyz_and_parity():
    assert len(parse_xyz(WATER)) == 3
    assert validate_request(WATER, 0, 0)['electrons'] == 10
    for text in ['', '1\nx\nXx 0 0 0', '1\nx\nH nan 0 0', WATER+'H 1 2 3', '2\nx\nH 0 0 0\nH 0 0 0']:
        with pytest.raises(ValueError): parse_xyz(text)
    for charge, uhf in [(0,1),(0.5,0),(False,0),(0,-1),(20,0)]:
        with pytest.raises(ValueError): validate_request(WATER,charge,uhf)

@pytest.mark.skip(reason='Recorded runtime logs intentionally excluded from source release; run real CLI comparison tests instead.')
def test_real_parser():
    root=Path(__file__).resolve().parents[1]/'evidence'
    sp=(root/'direct-sp/output.log').read_text()
    opt=(root/'direct-opt/output.log').read_text()
    out=(root/'direct-opt/xtbopt.xyz').read_text()
    atoms=parse_xyz(WATER)
    assert parse_result(sp,'sp','6.6.1',None,atoms)['valid']
    r=parse_result(opt,'opt','6.6.1',out,atoms)
    assert r['valid'] and r['geometry_converged'] is True
    assert r['energy_hartree']==pytest.approx(-5.070544443465)
    assert not parse_result(opt,'opt','6.6.1',None,atoms)['valid']
    assert not parse_result(sp.replace('convergence criteria satisfied','not converged'),'sp','6.6.1',None,atoms)['valid']
    assert not parse_result(sp,'sp','7.0',None,atoms)['valid']
    assert not parse_result(opt,'opt','6.6.1',out.replace('-5.070544443465','-9.0'),atoms)['valid']

def test_unknown_and_explicit_failure():
    r=parse_result('TOTAL ENERGY -1.0 Eh','sp','6.6.1',None,parse_xyz(WATER))
    assert r['scc_converged'] is None and not r['valid']
    r=parse_result('SCC NOT CONVERGED\nTOTAL ENERGY -1.0 Eh','sp','6.6.1',None,parse_xyz(WATER))
    assert r['scc_converged'] is False

@pytest.mark.skip(reason='Recorded runtime logs intentionally excluded from source release; run real CLI comparison tests instead.')
def test_parser_requires_actual_version_and_final_scc_confirmation():
    root=Path(__file__).resolve().parents[1]/'evidence'
    sp=(root/'direct-sp/output.log').read_text()
    opt=(root/'direct-opt/output.log').read_text()
    out=(root/'direct-opt/xtbopt.xyz').read_text()
    assert not parse_result(sp.replace('xtb version 6.6.1','xtb version 6.7.0'),'sp','6.6.1',None,parse_xyz(WATER))['valid']
    start=opt.index('GEOMETRY OPTIMIZATION CONVERGED')
    import re
    altered=opt[:start]+re.sub(r'\*\*\* convergence criteria satisfied after \d+ iterations \*\*\*','(marker missing)',opt[start:])
    assert not parse_result(altered,'opt','6.6.1',out,parse_xyz(WATER))['valid']
