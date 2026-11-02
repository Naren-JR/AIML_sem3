import {render,screen,cleanup,fireEvent} from '@testing-library/react'
import {afterEach,expect,it,vi} from 'vitest'
import {TrackQuality} from './TrackReference'
afterEach(()=>{cleanup();vi.unstubAllGlobals()})
it('shows source warnings without treating image candidates as activation zones',async()=>{
  vi.stubGlobal('fetch',vi.fn(async()=>({ok:true,json:async()=>({available:true,warning:'Historical snapshot',warnings:[{id:'TRACK-001',event:'Australian Grand Prix',warning:'Reference distances differ',category:'distance_anchor_conflict',action:'Do not align these anchors'}],candidates:[{annotation_id:'MAP-01',event:'Australian Grand Prix',verification:'unverified_image_space_only'}]})})))
  render(<TrackQuality/>);
  const summary=await screen.findByText(/Track processing evidence/)
  fireEvent.click(summary)
  expect(screen.getByText('Reference distances differ')).toBeInTheDocument()
  expect(screen.getByText('Do not align these anchors')).toBeInTheDocument()
  expect(screen.getByText(/No candidate is used as an activation zone/)).toBeInTheDocument()
  expect(screen.getByRole('link',{name:/Open supplied visual review sheet/})).toHaveAttribute('href','/api/track-report/review-sheet')
})
