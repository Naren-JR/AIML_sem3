import type {Sample} from './contracts'
export function nearestSample(samples:Sample[],distance:number):Sample|undefined{
  return samples.filter(s=>s.recorded.distance!==null).reduce<Sample|undefined>((best,s)=>!best||Math.abs(s.recorded.distance!-distance)<Math.abs(best.recorded.distance!-distance)?s:best,undefined)
}
