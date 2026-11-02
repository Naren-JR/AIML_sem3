import {useEffect,useState} from 'react'
import {z} from 'zod'
import {api} from './contracts'
const schema=z.object({available:z.boolean(),warning:z.string().optional(),source:z.string().optional(),geometry:z.array(z.object({x:z.number(),y:z.number()})).optional(),corners:z.array(z.object({number:z.string().nullable()})).optional(),sections:z.array(z.object({category:z.string(),start_percent:z.number(),end_percent:z.number()})).optional(),aero_zone_rows:z.number().optional()})
const qualitySchema=z.object({available:z.boolean(),warning:z.string().optional(),warnings:z.array(z.object({id:z.string(),event:z.string().optional(),warning:z.string(),category:z.string(),action:z.string()})),candidates:z.array(z.object({annotation_id:z.string(),event:z.string(),verification:z.string()}))})
export function TrackQuality(){
  const [quality,setQuality]=useState<z.infer<typeof qualitySchema>>();const [error,setError]=useState('')
  useEffect(()=>{api('/track-report',qualitySchema).then(setQuality).catch(e=>setError(String(e)))},[])
  if(error)return <p className="map-caption">Track processing evidence unavailable: {error}</p>
  if(!quality?.available)return null
  const local=quality.warnings.filter(w=>w.event==='Australian Grand Prix')
  return <section className="panel"><details><summary style={{padding:16,cursor:'pointer'}}>Track processing evidence · {quality.warnings.length} warnings · {local.length} Australian warnings</summary><p className="map-caption">{quality.warning}</p><p className="map-caption">Imported Australian metadata selects Practice 1 fallback; this report selects Race. Neither historical corner distances nor image annotations control race selection. Original source files are required to reconcile versions.</p><div className="table-scroll"><table><thead><tr><th>Australian warning</th><th>Applied safeguard / next evidence</th></tr></thead><tbody>{local.map(w=><tr key={w.id}><td>{w.warning}</td><td>{w.action}</td></tr>)}</tbody></table></div><p className="map-caption">{quality.candidates.filter(c=>c.event==='Australian Grand Prix').length} Australian image candidates remain unverified. No candidate is used as an activation zone. <a className="cyan" href={`${import.meta.env.VITE_API_BASE_URL??''}/api/track-report/review-sheet`} target="_blank" rel="noreferrer">Open supplied visual review sheet ↗</a></p></details></section>
}
export function TrackReference(){
  const [data,setData]=useState<z.infer<typeof schema>>();const [error,setError]=useState('')
  useEffect(()=>{api('/track-reference',schema).then(setData).catch(e=>setError(String(e)))},[])
  if(error)return <p className="map-caption">Static reference unavailable: {error}</p>
  if(!data?.available)return null
  const points=data.geometry??[]
  const xmin=Math.min(...points.map(p=>p.x)),xmax=Math.max(...points.map(p=>p.x)),ymin=Math.min(...points.map(p=>p.y)),ymax=Math.max(...points.map(p=>p.y))
  const scale=Math.min(600/Math.max(1,xmax-xmin),230/Math.max(1,ymax-ymin))
  const path=points.map((p,i)=>`${i?'L':'M'}${(360-(xmax-xmin)*scale/2+(p.x-xmin)*scale).toFixed(2)},${(270-(p.y-ymin)*scale).toFixed(2)}`).join(' ')
  return <section className="panel"><details><summary style={{padding:16,cursor:'pointer'}}>Supplied Australian circuit reference · alignment unverified</summary><p className="map-caption">{data.warning}</p><svg viewBox="0 0 720 310" style={{width:'100%',maxHeight:280}} role="img" aria-label="Unaligned static circuit reference"><path d={path} fill="none" stroke="#889caf" strokeWidth="3"/></svg><p className="map-caption">{points.length} geometry points · {data.corners?.length} corner references · {data.sections?.length} sections · {data.aero_zone_rows} aero-zone rows. This view does not control race selection.</p><div className="table-scroll"><table><thead><tr><th>Section category</th><th>Start · %</th><th>End · %</th></tr></thead><tbody>{data.sections?.map((s,i)=><tr key={i}><td>{s.category}</td><td>{s.start_percent}</td><td>{s.end_percent}</td></tr>)}</tbody></table></div><p className="map-caption">Source: {data.source}</p></details></section>
}
