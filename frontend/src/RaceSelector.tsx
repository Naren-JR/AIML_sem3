import {useEffect,useState} from 'react'
import {z} from 'zod'
import {api} from './contracts'
export const tracksSchema=z.object({tracks:z.array(z.object({id:z.string(),event:z.string(),year:z.number()}))})
export function RaceSelector({value,onChange}:{value:string,onChange:(id:string)=>void}){
 const [tracks,setTracks]=useState<z.infer<typeof tracksSchema>['tracks']>([]);const [error,setError]=useState('')
 useEffect(()=>{api('/ml/tracks',tracksSchema).then(r=>setTracks(r.tracks)).catch(e=>setError(String(e)))},[])
 return <section className="panel saved-runs" style={{marginTop:16}}><label>RECORDED GP RACE <select aria-label="Track" value={value} onChange={e=>onChange(e.target.value)}>{tracks.length?tracks.map(t=><option key={t.id} value={t.id}>{t.event} · {t.year}</option>):<option value={value}>{value}</option>}</select></label><span>{error||'KIMI ANTONELLI · REAL RECORDED TELEMETRY'}</span></section>
}
