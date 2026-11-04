// frontend/src/services/jobsService.ts

import type { Job, JobCard, JobEdit, Verb } from '../types/api'
import { apiFetch } from './apiClient'

export async function responseBody<T>(res: Response, failure: string): Promise<T> {
  if (res.status === 404 || res.status === 409 || res.status === 422) {
    const { detail } = await res.json()
    // FastAPI validation errors carry an array here, which is not a reason the owner can read
    throw new Error(typeof detail === 'string' ? detail : failure)
  }
  if (!res.ok) throw new Error(failure)
  return await res.json()
}

async function postJson(path: string, body: object | undefined, failure: string): Promise<Job> {
  const res = await apiFetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body && JSON.stringify(body),
  })
  return responseBody(res, failure)
}

export async function fetchJobs(): Promise<JobCard[]> {
  return responseBody(await apiFetch('/api/v1/jobs'), 'Failed to load jobs')
}

export async function editJob(jobId: string, edit: JobEdit): Promise<Job> {
  const res = await apiFetch(`/api/v1/jobs/${encodeURIComponent(jobId)}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(edit),
  })
  return responseBody(res, 'Failed to save the job')
}

export function approveJob(jobId: string, forwardTo?: string): Promise<Job> {
  return postJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/approve`, { forward_to: forwardTo }, 'Failed to approve the job')
}

export function chooseVerb(jobId: string, verb: Verb, always?: boolean): Promise<Job> {
  return postJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/choose`, { verb, always }, 'Failed to choose the action')
}

export function dismissJob(jobId: string): Promise<Job> {
  return postJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/dismiss`, undefined, 'Failed to dismiss the job')
}

export type Correction = { kind: 'noise' } | { kind: 'not_noise' } | { kind: 'wrong_action'; verb: Verb }

export function correctJob(jobId: string, correction: Correction): Promise<Job> {
  return postJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/correct`, correction, 'Failed to correct the job')
}
