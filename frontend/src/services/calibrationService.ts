// frontend/src/services/calibrationService.ts

import type { Job, JobCard, Verb } from '../types/api'
import { apiFetch } from './apiClient'
import { responseBody } from './jobsService'

// A dry run over recent mail: the server takes no action and its cards appear as they're made.
export async function startCalibration(): Promise<void> {
  const res = await apiFetch('/api/v1/calibration', { method: 'POST' })
  if (!res.ok) throw new Error('Failed to start calibration')
}

export async function fetchCalibration(): Promise<JobCard[]> {
  return responseBody(await apiFetch('/api/v1/calibration'), 'Failed to load calibration')
}

// The owner's 👍 (the proposed verb), fix (another verb) or noise: an example, a rule with `always`, a test set line.
export async function reactToCalibration(jobId: string, verb: Verb, always: boolean): Promise<Job> {
  const res = await apiFetch(`/api/v1/calibration/${encodeURIComponent(jobId)}/react`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ verb, always }),
  })
  return responseBody(res, 'Failed to save the reaction')
}
