'use client';
import {AlertTriangle,ArrowUpRight,RefreshCw,LoaderCircle} from 'lucide-react';
import {color,label} from '@/lib/client';
export function Status({state}:{state:string}){return <span className="status" style={{'--status':color(state)} as React.CSSProperties}><i/>{label(state)}</span>;}
export function Loading(){return <div className="empty"><LoaderCircle className="spin" size={25}/><h3>Connecting the dots…</h3><p>Reading your infrastructure.</p></div>;}
export function Empty({title='Nothing here yet',children}:{title?:string;children?:React.ReactNode}){return <div className="empty"><div className="empty-symbol">⌁</div><h3>{title}</h3><p>{children}</p></div>;}
export function ErrorNotice({message,retry}:{message:string;retry?:()=>void}){return <div role="alert" className="notice error-notice"><AlertTriangle size={16}/><span>{message}</span>{retry&&<button onClick={retry}>Retry <RefreshCw size={13}/></button>}</div>;}
export function Heading({title,subtitle,children}:{title:string;subtitle:string;children?:React.ReactNode}){return <header className="page-heading"><div><h1>{title}</h1><p>{subtitle}</p></div><div className="heading-actions">{children}</div></header>;}
export function External({href,children}:{href:string;children:React.ReactNode}){let safe=false;try{safe=['https:','http:'].includes(new URL(href).protocol);}catch{}return safe?<a href={href} target="_blank" rel="noopener noreferrer" className="external">{children}<ArrowUpRight size={13}/></a>:<span>{children}</span>;}
