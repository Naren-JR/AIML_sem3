import { z } from 'zod'
const nullable = z.number().nullable()
export const SampleSchema = z.object({sample_id:z.number(),lap:z.number(),recorded:z.record(z.string(),nullable),source_fields:z.record(z.string(),z.string()),calculated:z.object({speed_mps:nullable,acceleration_mps2:nullable}),quality_flags:z.array(z.string())})
export const ERSSchema = z.object({sample_id:z.number(),lap:z.number(),time_s:z.number(),distance_m:nullable,dt_s:z.number(),soc_pct:z.number(),remaining_energy_mj:z.number(),deployment_kw:nullable,recovery_kw:nullable,cumulative_deployed_mj:z.number(),cumulative_recovered_mj:z.number(),cumulative_losses_mj:z.number(),scenario_soc_min_pct:z.number(),scenario_soc_max_pct:z.number(),unknown_duration_s:z.number(),valid_interval:z.boolean()}).passthrough()
export const LapSchema = z.object({lap:z.number(),samples:z.number(),start_time_s:z.number(),end_time_s:z.number(),max_distance_m:z.number(),numbering:z.string()})
export const DatasetSchema=z.object({driver:z.string(),session:z.string(),event:z.string(),year:z.number(),samples:z.number(),laps:z.number(),sha256:z.string(),units:z.record(z.string(),z.string()),quality:z.object({invalid_timestamps:z.number(),duplicate_timestamps:z.number(),large_gaps:z.number(),missing:z.record(z.string(),z.number())}),provenance:z.string(),missing_context:z.array(z.string())}).passthrough()
export const ModelSchema=z.object({status:z.string(),kind:z.string(),parameters:z.record(z.string(),z.unknown()),validation:z.string(),uncertainty:z.string(),max_conservation_residual_mj:z.number(),unknown_duration_s:z.number(),final_soc_pct:z.number()}).passthrough()
export const TrackSchema=z.object({points:z.array(z.object({sample_id:z.number(),distance_m:z.number(),x:z.number(),y:z.number()})),click_selection_enabled:z.boolean(),mapping:z.string(),geometry_source:z.string(),external_reference_status:z.string()}).passthrough()
export const RunSchema=z.object({run_id:z.string(),status:z.string(),metadata:z.object({optimizer:z.object({lap:z.number()}).passthrough()}).passthrough(),objective:z.string(),horizon:z.string(),solver_message:z.string(),iterations:z.number(),baseline_objective:z.number(),optimized_objective:z.number(),baseline_deployed_mj:z.number(),optimized_deployed_mj:z.number(),baseline_final_energy_mj:z.number(),optimized_final_energy_mj:z.number(),feasible:z.boolean(),max_constraint_violation:z.number(),history:z.array(z.object({iteration:z.number(),objective:z.number(),max_constraint_violation:z.number()})),strategy:z.array(z.object({sample_id:z.number(),distance_m:nullable,baseline_kw:z.number(),optimized_kw:z.number(),recovery_kw:nullable,optimized_energy_mj:z.number(),baseline_energy_mj:z.number()}))}).passthrough()
export type Sample=z.infer<typeof SampleSchema>
export type ERS=z.infer<typeof ERSSchema>
export type Run=z.infer<typeof RunSchema>
export async function api<T>(path:string,schema:z.ZodType<T>,options?:RequestInit):Promise<T>{
  const response=await fetch(`${import.meta.env.VITE_API_BASE_URL ?? ''}/api${path}`,options)
  const body=await response.json()
  if(!response.ok)throw new Error(typeof body.detail==='string'?body.detail:JSON.stringify(body.detail??body))
  return schema.parse(body)
}
