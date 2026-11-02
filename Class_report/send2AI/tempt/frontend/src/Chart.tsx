import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-basic-dist-min'
export type Trace={name:string,x:(number|null)[],y:(number|null)[],color:string,fill?:string}
export function Chart({title,unit,traces,cursor,onSelect,height=160,xLabel='Distance · m'}:{title:string,unit:string,traces:Trace[],cursor?:number,onSelect?:(distance:number)=>void,height?:number,xLabel?:string}){
  const ref=useRef<HTMLDivElement>(null)
  const callback=useRef(onSelect)
  useEffect(()=>{callback.current=onSelect},[onSelect])
  useEffect(()=>{
    const element=ref.current
    if(!element)return
    const data=traces.map(t=>({type:'scatter',mode:'lines',name:t.name,x:t.x,y:t.y,connectgaps:false,line:{color:t.color,width:1.6},fill:t.fill,hovertemplate:`%{y:.2f} ${unit}<extra>${t.name}</extra>`}))
    let disposed=false
    Plotly.react(element,data,{height,margin:{l:48,r:16,t:12,b:32},paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'Consolas, monospace',size:10,color:'#8995a6'},xaxis:{title:{text:xLabel,standoff:4},gridcolor:'#202732',zeroline:false},yaxis:{gridcolor:'#202732',zeroline:false},showlegend:traces.length>1,legend:{orientation:'h',y:1.25,font:{size:10}},hovermode:'x',shapes:cursor===undefined?[]:[{type:'line',x0:cursor,x1:cursor,y0:0,y1:1,yref:'paper',line:{color:'#f2f6fb',width:1,dash:'dot'}}],uirevision:title},{responsive:true,displayModeBar:false}).then(()=>{
      if(disposed)return
      const el=element as any
      el.removeAllListeners('plotly_click');el.removeAllListeners('plotly_hover')
      const select=(event:any)=>{const x=event.points?.[0]?.x;if(typeof x==='number')callback.current?.(x)}
      el.on('plotly_click',select);el.on('plotly_hover',select)
    })
    return()=>{disposed=true}
  },[traces,cursor,height,title,unit,xLabel])
  useEffect(()=>{const el=ref.current;return()=>{if(el)Plotly.purge(el)}},[])
  return <section className="panel chart"><div className="panel-title"><h3>{title}</h3><span>{unit}</span></div><div ref={ref} role="img" aria-label={`${title} chart`} /></section>
}
