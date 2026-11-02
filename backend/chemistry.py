"""Strict XYZ validation and conservative, version-specific xTB result acceptance."""
import math
import re

ELEMENTS = 'H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn'.split()
MAX_XYZ = 131072

def parse_xyz(text):
    if not isinstance(text,str) or len(text.encode()) > MAX_XYZ:
        raise ValueError('XYZ must be text no larger than 128 KiB.')
    lines=text.strip('\n\r').splitlines()
    if len(lines)<3 or not re.fullmatch(r'[0-9]+',lines[0].strip()):
        raise ValueError('XYZ requires an atom count, comment line and coordinates.')
    n=int(lines[0])
    if not 1<=n<=300 or len(lines)!=n+2:
        raise ValueError('XYZ must contain exactly 1–300 declared atoms, one frame only.')
    atoms=[]
    for i,line in enumerate(lines[2:]):
        fields=line.split()
        if len(fields)!=4 or fields[0] not in ELEMENTS:
            raise ValueError(f'Atom {i+1}: use a valid element (H–Rn) and three coordinates.')
        try: xyz=[float(x) for x in fields[1:]]
        except ValueError: raise ValueError(f'Atom {i+1}: invalid coordinate.')
        if not all(math.isfinite(x) and abs(x)<=10000 for x in xyz):
            raise ValueError('Coordinates must be finite and within ±10000 Å.')
        if any(math.dist(xyz,a['xyz'])<0.2 for a in atoms):
            raise ValueError('Atoms must be at least 0.2 Å apart.')
        atoms.append({'element':fields[0],'xyz':xyz})
    return atoms

def normalized_xyz(atoms):
    return f'{len(atoms)}\nWorkbench snapshot; coordinates in Angstrom\n'+''.join(a['element']+' '+' '.join(f'{x:.12f}' for x in a['xyz'])+'\n' for a in atoms)

def validate_request(xyz,charge,uhf):
    atoms=parse_xyz(xyz)
    if type(charge) is not int or not -20<=charge<=20 or type(uhf) is not int or not 0<=uhf<=20:
        raise ValueError('Charge must be an integer ±20; unpaired electrons an integer 0–20.')
    electrons=sum(ELEMENTS.index(a['element'])+1 for a in atoms)-charge
    if electrons<1 or uhf>electrons or (electrons-uhf)%2:
        raise ValueError('Electron count and unpaired electrons have incompatible parity or range.')
    return {'atoms':atoms,'electrons':electrons,'normalized_xyz':normalized_xyz(atoms)}

def parse_result(log,mode,version,output, input_atoms):
    actual=re.search(r'xtb version\s+(\d+\.\d+\.\d+)',log)
    supported=version=='6.6.1' and actual is not None and actual[1]==version
    energies=re.findall(r'TOTAL ENERGY\s+([-+\d.eEdD]+)\s+Eh',log)
    try: energy=float(energies[-1].replace('D','E')) if energies else None
    except ValueError: energy=None
    if energy is not None and not math.isfinite(energy): energy=None
    failed=bool(re.search(r'(?:SCC|SCF).*?(?:NOT CONVERGED|FAILED)|convergence criteria cannot be satisfied',log,re.I))
    markers=list(re.finditer(r'\*\*\* convergence criteria satisfied after \d+ iterations \*\*\*',log))
    geometry_mark=re.search(r'GEOMETRY OPTIMIZATION CONVERGED AFTER\s+\d+\s+ITERATIONS',log)
    confirmed=bool(markers) and (mode=='sp' or (geometry_mark is not None and markers[-1].start()>geometry_mark.end()))
    scc=False if failed else (True if confirmed else None)
    geometry=None
    if mode=='opt':
        geometry=False if re.search(r'FAILED TO CONVERGE GEOMETRY|GEOMETRY OPTIMIZATION FAILED',log,re.I) else (True if re.search(r'GEOMETRY OPTIMIZATION CONVERGED AFTER\s+\d+\s+ITERATIONS',log) else None)
    final=None
    reason='Validated convergence and final energy.'
    if mode=='opt' and output:
        try:
            atoms=parse_xyz(output)
            if [a['element'] for a in atoms]!=[a['element'] for a in input_atoms]: raise ValueError('Final atom order or composition differs.')
            m=re.search(r'energy:\s*([-+\d.eE]+)',output.splitlines()[1])
            if not m or energy is None or abs(float(m[1])-energy)>1e-8: raise ValueError('Final structure energy does not match log.')
            final=output
        except ValueError as e: reason=str(e)
    valid=supported and scc is True and energy is not None and (mode=='sp' or (geometry is True and final is not None))
    if not valid and reason.startswith('Validated'): reason='Unconfirmed convergence, energy, engine version or final structure; inspect log.'
    return {'valid':valid,'scc_converged':scc,'geometry_converged':geometry,'energy_hartree':energy,'energy_unit':'Eh','final_xyz':final if valid else None,'reason':reason,'parser_version':'xtb-6.6.1-v1'}
