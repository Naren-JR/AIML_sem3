import {cleanup,render,screen} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {MLValidation} from './MLValidation'
vi.mock('./Chart',()=>({Chart:()=>null}))
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
it('does not fabricate metrics before training and explains the ERS boundary',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({status:'not_run',sources:[]})})))
  render(<MLValidation/>);
  await screen.findByText(/Status: not_run/)
  expect(screen.getByText(/do not measure ERS or SoC accuracy/)).toBeInTheDocument()
  expect(screen.queryByText('Held-out performance')).not.toBeInTheDocument()
  expect(screen.getByRole('button',{name:'Train & evaluate'})).toBeEnabled()
})
