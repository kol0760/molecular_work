export type Atom={element:string;xyz:[number,number,number]};
export type Snapshot={atoms:Atom[];xyz:string};
export type History={past:Snapshot[];present:Snapshot;future:Snapshot[]};
export const WATER='3\nWater; Angstrom\nO 0 0 -0.3893611\nH 0.7629844 0 0.1946806\nH -0.7629844 0 0.1946806\n';
export const ELEMENTS='H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn'.split(' ');
export function parseXYZ(text:string):Atom[]{
  if(new TextEncoder().encode(text).length>131072)throw Error('XYZ exceeds 128 KiB.');
  const lines=text.replace(/^[\r\n]+|[\r\n]+$/g,'').split(/\r?\n/);const n=Number(lines[0]);
  if(!/^\d+$/.test(lines[0]?.trim()||'')||n<1||n>300||lines.length!==n+2)throw Error('Use one XYZ frame: 1–300 atoms, a comment line, then exactly one element and three coordinates per atom.');
  const atoms:Atom[]=[];
  for(const [i,line] of lines.slice(2).entries()){
    const f=line.trim().split(/\s+/);const xyz=f.slice(1).map(Number) as [number,number,number];
    if(f.length!==4||!ELEMENTS.includes(f[0])||xyz.some(x=>!Number.isFinite(x)||Math.abs(x)>10000))throw Error(`Atom ${i+1}: use a supported element and finite coordinates within ±10000 Å.`);
    if(atoms.some(a=>Math.hypot(...a.xyz.map((x,k)=>x-xyz[k]))<.2))throw Error('Atoms must be at least 0.2 Å apart.');
    atoms.push({element:f[0],xyz});
  }
  return atoms;
}
export function formatXYZ(atoms:Atom[],name='Edited structure'):string{return `${atoms.length}\n${name.replace(/[\r\n]/g,' ')}; Angstrom\n`+atoms.map(a=>`${a.element} ${a.xyz.map(x=>Number(x.toFixed(10))).join(' ')}`).join('\n')+'\n';}
export function makeHistory(atoms:Atom[],xyz=formatXYZ(atoms)):History{return {past:[],present:{atoms,xyz},future:[]};}
export function commit(h:History,atoms:Atom[],raw=formatXYZ(atoms)):History{
  const canonical=parseXYZ(raw);
  if(raw===h.present.xyz)return h;
  return {past:[...h.past.slice(-49),h.present],present:{atoms:canonical,xyz:raw},future:[]};
}
export function undo(h:History):History{return h.past.length?{past:h.past.slice(0,-1),present:h.past.at(-1)!,future:[h.present,...h.future].slice(0,50)}:h;}
export function redo(h:History):History{return h.future.length?{past:[...h.past,h.present].slice(-50),present:h.future[0],future:h.future.slice(1)}:h;}
export function translate(atoms:Atom[],selected:number[],delta:number[]):Atom[]{return atoms.map((a,i)=>({element:a.element,xyz:a.xyz.map((x,k)=>x+(selected.includes(i)?delta[k]:0)) as Atom['xyz']}));}
export function rotate(atoms:Atom[],selected:number[],axis:'x'|'y'|'z',degrees:number):Atom[]{
  if(!selected.length)return atoms;
  const center=[0,1,2].map(k=>selected.reduce((s,i)=>s+atoms[i].xyz[k],0)/selected.length);const angle=degrees*Math.PI/180,c=Math.cos(angle),s=Math.sin(angle),d=axis==='x'?0:axis==='y'?1:2;
  return atoms.map((a,i)=>{if(!selected.includes(i))return a;const p=a.xyz.map((x,k)=>x-center[k]);const u=(d+1)%3,v=(d+2)%3;const q=[...p];q[u]=p[u]*c-p[v]*s;q[v]=p[u]*s+p[v]*c;return {element:a.element,xyz:q.map((x,k)=>x+center[k]) as Atom['xyz']};});
}
const sub=(a:number[],b:number[])=>a.map((x,i)=>x-b[i]);
const dot=(a:number[],b:number[])=>a.reduce((s,x,i)=>s+x*b[i],0);
const cross=(a:number[],b:number[])=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
export function measurement(atoms:Atom[],selected:number[]):{kind:string;value:number|null;unit:string}{
  const p=selected.map(i=>atoms[i]?.xyz);if(p.some(x=>!x)||p.length<2||p.length>4)return {kind:'Select 2–4 atoms',value:null,unit:''};
  if(p.length===2)return {kind:'Distance',value:Math.hypot(...sub(p[0],p[1])),unit:'Å'};
  if(p.length===3){const a=sub(p[0],p[1]),b=sub(p[2],p[1]);const divisor=Math.hypot(...a)*Math.hypot(...b);return {kind:'Angle',value:divisor?Math.acos(Math.max(-1,Math.min(1,dot(a,b)/divisor)))*180/Math.PI:null,unit:'°'};}
  const b0=sub(p[0],p[1]),b1=sub(p[2],p[1]),b2=sub(p[3],p[2]);const norm=Math.hypot(...b1);if(!norm)return {kind:'Dihedral',value:null,unit:'°'};
  const u=b1.map(x=>x/norm),v=b0.map((x,i)=>x-dot(b0,u)*u[i]),w=b2.map((x,i)=>x-dot(b2,u)*u[i]);return {kind:'Dihedral',value:Math.hypot(...v)*Math.hypot(...w)>1e-12?Math.atan2(dot(cross(u,v),w),dot(v,w))*180/Math.PI:null,unit:'°'};
}
