import {fireEvent,render,screen,cleanup} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {Circuit} from './Circuit'
afterEach(cleanup)
it('disables map selection explicitly when mapping has not passed checks',()=>{
  const onSelect=vi.fn()
  render(<Circuit track={{points:[{sample_id:1,distance_m:1,x:2,y:3}],click_selection_enabled:false,mapping:'invalid',geometry_source:'recorded',external_reference_status:'absent'}} sampleId={1} onSelect={onSelect}/>)
  fireEvent.click(screen.getByRole('img',{name:'Recorded lap trajectory'}))
  expect(onSelect).not.toHaveBeenCalled()
  expect(screen.getByText(/Map selection disabled/)).toBeInTheDocument()
})
it('retains a missing-position message instead of inventing geometry',()=>{
  render(<Circuit track={{points:[],click_selection_enabled:false,mapping:'missing',geometry_source:'recorded',external_reference_status:'absent'}} sampleId={1} onSelect={vi.fn()}/>)
  expect(screen.getByText(/Position channels unavailable/)).toBeInTheDocument()
  expect(screen.queryByRole('img')).not.toBeInTheDocument()
})
