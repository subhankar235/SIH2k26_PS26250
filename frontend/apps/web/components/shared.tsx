'use client';
import {ArrowUpRight,ChevronRight} from 'lucide-react';
import Link from 'next/link';
export function Badge({children,tone='green'}:{children:React.ReactNode;tone?:string}){return <span className={`badge ${tone}`}><span className="status-dot"/>{children}</span>}
export function Panel({title,subtitle,action,children,className=''}:{title:string;subtitle?:string;action?:React.ReactNode;children:React.ReactNode;className?:string}){return <section className={`panel ${className}`}><div className="panel-head"><div><h2>{title}</h2>{subtitle&&<p>{subtitle}</p>}</div>{action}</div>{children}</section>}
export function Metric({label,value,note,tone='teal',href}:{label:string;value:string|number;note:string;tone?:string;href?:string}){const inner=<><div className="metric-label">{label}<ArrowUpRight size={15}/></div><div className="metric-value">{value}</div><div className={`metric-note ${tone}`}>{note}</div><svg className={`spark ${tone}`} viewBox="0 0 110 35" aria-hidden="true"><path d="M0 29 L10 23 L20 27 L30 14 L40 19 L50 16 L60 22 L70 9 L80 14 L90 5 L100 10 L110 2" fill="none" stroke="currentColor" strokeWidth="2"/></svg></>;return href?<Link className="metric" href={href}>{inner}</Link>:<div className="metric">{inner}</div>}
export function TextLink({href,children}:{href:string;children:React.ReactNode}){return <Link className="text-link" href={href}>{children}<ChevronRight size={14}/></Link>}
export function Empty({children}:{children:React.ReactNode}){return <div className="empty">{children}</div>}
export function download(name:string,data:unknown){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);}
