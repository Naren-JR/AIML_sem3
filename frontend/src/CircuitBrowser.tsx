import {useEffect,useState} from 'react'
import {z} from 'zod'
import {api} from './contracts'
const circuit=z.object({id:z.string(),event:z.string(),name:z.string(),participation_years:z.array(z.number()),participation_source:z.string(),verified_on:z.string(),race_telemetry_available:z.boolean(),geometry_points:z.number()})
export function CircuitSelector({value,onChange}:{value:string,onChange:(value:string)=>void}){
 const [entries,setEntries]=useState<z.infer<typeof circuit>[]>([]);const [error,setError]=useState('')
 useEffect(()=>{api('/circuits',z.object({circuits:z.array(circuit)})).then(r=>setEntries(r.circuits)).catch(e=>setError(String(e)))},[])
 return <section className="panel saved-runs" style={{marginTop:16}}><label>TRACK <select aria-label="Track" value={value} onChange={e=>onChange(e.target.value)}>{entries.length?entries.map(c=><option key={c.id} value={c.id}>{c.name} · {c.race_telemetry_available?'race telemetry':'reference only'}</option>):<option value="australian-grand-prix">Albert Park</option>}</select></label>{error&&<span>{error}</span>}</section>
}
const detail=z.object({circuit,reference:z.object({available:z.boolean(),geometry:z.array(z.object({x:z.number(),y:z.number()})).optional(),warning:z.string().optional()}).passthrough(),section_percentages:z.array(z.tuple([z.string(),z.number(),z.number()]))})
export function CircuitBrowser({id}:{id:string}){
 const [data,setData]=useState<z.infer<typeof detail>>();const [error,setError]=useState('')
 useEffect(()=>{let active=true;setData(undefined);setError('');api(`/circuits/${encodeURIComponent(id)}`,detail).then(r=>{if(active)setData(r)}).catch(e=>{if(active)setError(String(e))});return()=>{active=false}},[id])
 if(error)return <p role="alert" className="error">{error}</p>
 if(!data)return <p className="loading">Loading circuit reference…</p>
 const c=data.circuit,p=data.reference.geometry??[]
 const xmin=Math.min(...p.map(a=>a.x)),xmax=Math.max(...p.map(a=>a.x)),ymin=Math.min(...p.map(a=>a.y)),ymax=Math.max(...p.map(a=>a.y))
 const scale=Math.min(600/Math.max(1,xmax-xmin),300/Math.max(1,ymax-ymin))
 const path=p.map((a,i)=>`${i?'L':'M'}${360-(xmax-xmin)*scale/2+(a.x-xmin)*scale},${350-(a.y-ymin)*scale}`).join(' ')
 return <><div className="page-heading"><div><div className="eyebrow">KIMI ANTONELLI · CIRCUIT LIBRARY</div><h1>{c.name}</h1><p>{c.event} · Static reference data</p></div></div><div className="research-note">No local GP Race telemetry is installed for this track. Vehicle readouts, SoC, optimizer and ML predictions are unavailable. Select Albert Park to return to recorded race analysis.</div><section className="panel prose"><h3>Participation & provenance</h3><p>Official race-result entry in {c.participation_years.join(', ')}; a DNF counts as participation. Past participation does not verify layout compatibility.</p><p><a className="cyan" href={c.participation_source} target="_blank" rel="noreferrer">Official F1 results ↗</a> · checked {c.verified_on}</p><p>{data.reference.warning}</p></section><section className="panel"><div className="panel-title"><h3>Static circuit reference</h3><span>{p.length} POINTS · NOT TELEMETRY-ALIGNED</span></div>{p.length?<svg role="img" aria-label={`${c.name} reference`} viewBox="0 0 720 400" style={{width:'100%',maxHeight:430}}><path d={path} fill="none" stroke="#47d9cf" strokeWidth="3"/></svg>:<p className="notice">Coordinate geometry is unavailable. Section percentages remain available; no circuit layout is fabricated.</p>}</section><section className="panel"><div className="panel-title"><h3>Section references</h3><span>NOT ACTIVATION ZONES</span></div><table><thead><tr><th>Category</th><th>Start · %</th><th>End · %</th></tr></thead><tbody>{data.section_percentages.map(([name,start,end],i)=><tr key={i}><td>{name}</td><td>{start}</td><td>{end}</td></tr>)}</tbody></table></section></>
}
