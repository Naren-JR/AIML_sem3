import {cleanup,render,screen,fireEvent,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {MLValidation} from './MLValidation'
vi.mock('./Chart',()=>({Chart:()=>null}))
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
it('does not fabricate metrics before training and explains the ERS boundary',async()=>{
  vi.stubGlobal('fetch',vi.fn(async(url:string)=>({ok:true,json:async()=>url.endsWith('/ml/tracks')?{tracks:[{id:'australian-grand-prix',event:'Australian Grand Prix',year:2026}]}:{status:'not_run',sources:[]}})))
  render(<MLValidation/>);
  await screen.findByText(/Status: not_run/)
  expect(screen.getByText(/do not measure ERS or SoC accuracy/)).toBeInTheDocument()
  expect(screen.queryByText('Held-out performance')).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Train & evaluate'})).toBeEnabled()
})

it('submits disjoint tracks for cross-track evaluation',async()=>{
 const tracks=[{id:'australian-grand-prix',event:'Australia',year:2026},{id:'austrian-grand-prix',event:'Austria',year:2026},{id:'italian-grand-prix',event:'Italy',year:2026}]
 const fetcher=vi.fn(async(url:string)=>({ok:true,json:async()=>url.endsWith('/ml/tracks')?{tracks}:{status:'not_run',sources:[]}}))
 vi.stubGlobal('fetch',fetcher)
 render(<MLValidation/>);
 await screen.findByRole('option',{name:'Austria'})
 fireEvent.change(screen.getByRole('combobox',{name:'Evaluation mode'}),{target:{value:'cross_track'}})
 fireEvent.change(screen.getByRole('combobox',{name:'Training track'}),{target:{value:'austrian-grand-prix'}})
 fireEvent.click(screen.getByRole('button',{name:'Train & evaluate'}))
 await waitFor(()=>expect(fetcher).toHaveBeenCalledWith('/api/ml/experiments/run',expect.objectContaining({method:'POST',body:JSON.stringify({mode:'cross_track',train_track:'austrian-grand-prix',test_track:'italian-grand-prix'})})))
})
