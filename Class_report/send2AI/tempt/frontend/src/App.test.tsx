import {fireEvent,render,screen,waitFor,cleanup} from '@testing-library/react'
import {afterEach,describe,expect,it,vi} from 'vitest'
import {MemoryRouter} from 'react-router-dom'
import {App} from './App'
import {nearestSample} from './selection'
import {SampleSchema} from './contracts'

vi.mock('./Chart',()=>({Chart:({title,cursor,onSelect}:any)=><button aria-label={title} data-cursor={cursor} onClick={()=>onSelect?.(100)}>{title}</button>}))
vi.mock('./Circuit',()=>({Circuit:({sampleId,onSelect}:any)=><button aria-label="Circuit sample" data-sample={sampleId} onClick={()=>onSelect(100)}>map</button>}))
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
const samples=[0,100].map((distance,i)=>({sample_id:i,lap:1,recorded:{time:i*.2,distance,speed:i?200:null,rpm:10000,gear:5,throttle:50,brake:0},source_fields:{speed:i?'200':''},calculated:{speed_mps:i?200/3.6:null,acceleration_mps2:i?1:null},quality_flags:[]}))
const ers=samples.map((s,i)=>({sample_id:i,lap:1,time_s:i*.2,distance_m:s.recorded.distance,dt_s:i*.2,soc_pct:100-i,remaining_energy_mj:4-i*.04,deployment_kw:i?10:null,recovery_kw:i?0:null,cumulative_deployed_mj:0,cumulative_recovered_mj:0,cumulative_losses_mj:0,scenario_soc_min_pct:95,scenario_soc_max_pct:100,unknown_duration_s:0,valid_interval:true}))
const data:any={
  '/dataset':{driver:'Kimi Antonelli',session:'GP Race',event:'Australian Grand Prix',year:2026,samples:2,laps:1,sha256:'abc',units:{speed:'km/h'},quality:{invalid_timestamps:0,duplicate_timestamps:0,large_gaps:0,missing:{}},provenance:'Supplied',missing_context:[]},
  '/laps':[{lap:1,samples:2,start_time_s:0,end_time_s:.2,max_distance_m:100,numbering:'inferred'}],
  '/model/status':{status:'ready',kind:'physics',parameters:{},validation:'constraint-only',uncertainty:'scenario',max_conservation_residual_mj:0,unknown_duration_s:0,final_soc_pct:99},
  '/telemetry/lap/1':{samples},'/ers/lap/1':{samples:ers},'/track/1':{points:samples.map(s=>({sample_id:s.sample_id,distance_m:s.recorded.distance,x:s.sample_id,y:0})),click_selection_enabled:true,mapping:'same-row',geometry_source:'recorded',external_reference_status:'absent'}
}
function setup(){vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,json:async()=>data[url.replace('/api','')]})));render(<MemoryRouter><App/></MemoryRouter>)}
describe('one selection state',()=>{
  it('synchronizes map, slider, chart cursors and readouts',async()=>{
    setup();await screen.findByRole('button',{name:'Circuit sample'})
    fireEvent.change(screen.getByRole('slider'),{target:{value:100}})
    expect(screen.getByRole('button',{name:'Circuit sample'})).toHaveAttribute('data-sample','1')
    expect(screen.getByRole('button',{name:'Vehicle speed'})).toHaveAttribute('data-cursor','100')
    fireEvent.change(screen.getByRole('slider'),{target:{value:0}})
    fireEvent.click(screen.getByRole('button',{name:'Circuit sample'}))
    expect(screen.getByRole('slider')).toHaveValue('100')
    fireEvent.change(screen.getByRole('slider'),{target:{value:0}})
    fireEvent.click(screen.getByRole('button',{name:'Vehicle speed'}))
    expect(screen.getByRole('slider')).toHaveValue('100')
    expect(screen.getByText('200.0')).toBeInTheDocument()
  })
  it('preserves missing recorded speed as null',()=>{
    const source=SampleSchema.parse(samples[0]);expect(source.recorded.speed).toBeNull()
    expect(nearestSample(samples,90)?.sample_id).toBe(1)
    expect(nearestSample(samples,0)?.recorded.speed).toBeNull()
  })
  it('shows API errors instead of fabricated fallback data',async()=>{
    vi.stubGlobal('fetch',vi.fn(async()=>({ok:false,json:async()=>({detail:'Missing telemetry'})})))
    render(<MemoryRouter><App/></MemoryRouter>);await waitFor(()=>expect(screen.getByRole('alert')).toHaveTextContent('Missing telemetry'))
    expect(screen.queryByRole('slider')).not.toBeInTheDocument()
  })
})
