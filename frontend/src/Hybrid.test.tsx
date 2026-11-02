import {cleanup,fireEvent,render,screen,waitFor} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {Hybrid} from './Hybrid'
vi.mock('./Chart',()=>({Chart:()=>null}))
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
it('explains the real training target and submits a separately selected held-out track',async()=>{
 const fetch=vi.fn(async(url:string)=>({ok:true,json:async()=>url.endsWith('/hybrid/tracks')?{tracks:['australian','austrian','italian','british','belgian'].map(t=>({id:t+'-grand-prix',label:t,available:true,laps:44,samples:30000}))}:{status:'not_run'}}))
 vi.stubGlobal('fetch',fetch)
 render(<Hybrid/> )
 await screen.findByText(/Status: not_run/)
 expect(screen.getByText(/We train next-sample acceleration/)).toBeInTheDocument()
 expect(screen.queryByText('Held-out regression metric')).not.toBeInTheDocument()
 fireEvent.change(screen.getByLabelText('Unseen hybrid test track'),{target:{value:'austrian-grand-prix'}})
 await screen.findByText(/Training uses 4 other downloaded circuits/)
 fireEvent.click(screen.getByRole('button',{name:'Train on other circuits & test unseen track'}))
 await waitFor(()=>expect(fetch).toHaveBeenCalledTimes(3))
 const call=fetch.mock.calls[2] as unknown as [string,RequestInit]
 expect(call[0]).toContain('/hybrid/train')
 expect(JSON.parse(call[1].body as string)).toEqual({test_track:'austrian-grand-prix'})
})
