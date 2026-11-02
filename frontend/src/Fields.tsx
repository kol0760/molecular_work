import {useEffect,useState,useRef} from 'react';
import Icon from './Icon';
export function NumberCell({value,label,onCommit,onValidity}:{value:number;label:string;onCommit:(n:number)=>boolean;onValidity:(valid:boolean)=>void}){
 const display=(n:number)=>String(Number(n.toFixed(10)));
 const [text,setText]=useState(display(value)),[invalid,setInvalid]=useState(false);const cancelled=useRef(false);
 useEffect(()=>{setText(display(value));setInvalid(false);onValidity(true);},[value]);
 return <input aria-label={label} aria-invalid={invalid} type="text" inputMode="decimal" value={text} onChange={e=>{setText(e.target.value);const ok=e.target.value.trim()!==''&&Number.isFinite(Number(e.target.value))&&Math.abs(Number(e.target.value))<=10000;setInvalid(!ok);onValidity(ok);}} onBlur={()=>{if(cancelled.current){cancelled.current=false;return;}const ok=text.trim()!==''&&Number.isFinite(Number(text))&&Math.abs(Number(text))<=10000&&onCommit(Number(text));setInvalid(!ok);onValidity(ok);}} onKeyDown={e=>{if(e.key==='Enter')e.currentTarget.blur();if(e.key==='Escape'){cancelled.current=true;setText(display(value));setInvalid(false);onValidity(true);e.currentTarget.blur();}}}/>;
}
export function Modal({title,onClose,children,wide=false}:{title:string;onClose:()=>void;children:React.ReactNode;wide?:boolean}){return <div className="modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget)onClose();}}><section role="dialog" aria-modal="true" aria-label={title} className={'dialog '+(wide?'dialog-wide':'')}><header className="dialog-title"><h2>{title}</h2><button className="icon-button" aria-label="Close dialog" onClick={onClose}><Icon name="close"/></button></header>{children}</section></div>;}
