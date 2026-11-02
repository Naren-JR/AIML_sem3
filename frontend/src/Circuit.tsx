import type { z } from 'zod'
import type { TrackSchema } from './contracts'
export function Circuit({track,sampleId,onSelect}:{track:z.infer<typeof TrackSchema>,sampleId:number,onSelect:(distance:number)=>void}){
  const p=track.points
  if(!p.length)return <p className="notice">Position channels unavailable. Use the distance slider.</p>
  const xmin=Math.min(...p.map(a=>a.x)),xmax=Math.max(...p.map(a=>a.x)),ymin=Math.min(...p.map(a=>a.y)),ymax=Math.max(...p.map(a=>a.y))
  const scale=Math.min(580/Math.max(xmax-xmin,1),290/Math.max(ymax-ymin,1))
  const xOffset=(720-(xmax-xmin)*scale)/2
  const project=(a:typeof p[number])=>({x:xOffset+(a.x-xmin)*scale,y:340-(a.y-ymin)*scale})
  const path=p.map((a,i)=>`${i?'L':'M'}${project(a).x.toFixed(2)},${project(a).y.toFixed(2)}`).join(' ')
  const selected=p.find(a=>a.sample_id===sampleId)
  const marker=selected?project(selected):null
  return <><svg className={`circuit ${track.click_selection_enabled?'selectable':''}`} viewBox="0 0 720 400" aria-label="Recorded lap trajectory" role="img" onClick={e=>{
    if(!track.click_selection_enabled)return
    const svg=e.currentTarget,pt=svg.createSVGPoint();pt.x=e.clientX;pt.y=e.clientY
    const matrix=svg.getScreenCTM();if(!matrix)return
    const point=pt.matrixTransform(matrix.inverse())
    const nearest=p.reduce((a,b)=>Math.hypot(project(a).x-point.x,project(a).y-point.y)<Math.hypot(project(b).x-point.x,project(b).y-point.y)?a:b)
    onSelect(nearest.distance_m)
  }}><defs><pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="#1b2530" strokeWidth=".5"/></pattern></defs><rect width="720" height="400" fill="url(#grid)"/><path d={path} fill="none" stroke="#242f3c" strokeWidth="17" strokeLinejoin="round"/><path d={path} fill="none" stroke="#6c8396" strokeWidth="3" strokeLinejoin="round"/>{marker&&<g><circle cx={marker.x} cy={marker.y} r="15" fill="#39d8cf" opacity=".12"/><circle cx={marker.x} cy={marker.y} r="6" fill="#39d8cf" stroke="#e5ffff" strokeWidth="2"/></g>}<text x="30" y="35" fill="#708294" fontSize="10" letterSpacing="2">RECORDED POSITION TRACE</text><text x="30" y="380" fill="#708294" fontSize="10">SOURCE COORDINATE FRAME · UNITS UNVERIFIED</text></svg><p className="map-caption">{track.click_selection_enabled?'Click trace to select a recorded sample':'Map selection disabled: mapping checks failed'}. Slider and chart cursors share this selection.</p></>
}
