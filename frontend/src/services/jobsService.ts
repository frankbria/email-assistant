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

// `messageIds`: what the card showed; a digest gathers mail, so its tap covers only these.
export function approveJob(jobId: string, forwardTo?: string, messageIds?: string[]): Promise<Job> {
  return postJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/approve`, { forward_to: forwardTo, message_ids: messageIds }, 'Failed to approve the job')
}

// The List-Unsubscribe target from the mail: untrusted, so the owner sees it in full before acting on it.
export async function fetchUnsubscribeTarget(jobId: string): Promise<string> {
  const { target } = await responseBody<{ target: string }>(
    await apiFetch(`/api/v1/jobs/${encodeURIComponent(jobId)}/unsubscribe`),
    'Failed to read the unsubscribe target'
  )
  return target
}

// `target`: what the owner was shown; the server acts only if the mail still names exactly it.
export function approveUnsubscribe(jobId: string, target: string): Promise<Job> {
  return postJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/approve`, { unsubscribe_target: target }, 'Failed to unsubscribe')
}

export function chooseVerb(jobId: string, verb: Verb, always?: boolean): Promise<Job> {
  return postJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/choose`, { verb, always }, 'Failed to choose the action')
}

export function dismissJob(jobId: string, messageIds?: string[]): Promise<Job> {
  return postJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/dismiss`, messageIds && { message_ids: messageIds }, 'Failed to dismiss the job')
}

export type Correction = { kind: 'noise' } | { kind: 'not_noise' } | { kind: 'wrong_action'; verb: Verb }

export function correctJob(jobId: string, correction: Correction): Promise<Job> {
  return postJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/correct`, correction, 'Failed to correct the job')
}
