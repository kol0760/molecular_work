import type {History} from './model';
export type Structure={id:string;name:string;xyz:string;charge:number;uhf:number;revision:number;created:number;updated:number};
export type Document={record:Structure;baseRevision:number;name:string;charge:number;uhf:number;history:History;selection:number[]};
export type Job={id:string;status:string;mode:'sp'|'opt';charge:number;uhf:number;xyz?:string;created:number;started:number|null;finished:number|null;version:string;error:string|null;log?:string;log_truncated?:boolean;structure_id?:string;structure_name?:string;structure_revision?:number;result?:{energy_hartree:number|null;scc_converged:boolean|null;geometry_converged:boolean|null;final_xyz?:string|null;valid:boolean;reason:string}};
export const dirty=(d:Document)=>d.baseRevision!==d.record.revision||d.name!==d.record.name||d.history.present.xyz!==d.record.xyz||d.charge!==d.record.charge||d.uhf!==d.record.uhf;
export async function api(path:string,data?:unknown){const r=await fetch('/api'+path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Workbench':'1'},body:JSON.stringify(data)});const body=await r.json();if(!r.ok)throw Error(typeof body.detail==='string'?body.detail:'Request rejected.');return body;}
export const isActive=(status:string)=>['queued','running'].includes(status);
