// frontend/src/services/historyService.ts

import type { ActionLogEntry, FilteredCard, HistoryCard } from '../types/api'
import { apiFetch } from './apiClient'
import { responseBody } from './jobsService'

export async function fetchHistory(): Promise<HistoryCard[]> {
  return responseBody(await apiFetch('/api/v1/history'), 'Failed to load history')
}

// Noise archived in the last 30 days; restoring one is undoEntry on its archive.
export async function fetchFiltered(): Promise<FilteredCard[]> {
  return responseBody(await apiFetch('/api/v1/filtered'), 'Failed to load filtered mail')
}

// The restore's own entry: a 200 with ok false is a restore that failed, not a refused undo.
export async function undoEntry(entryId: string): Promise<ActionLogEntry> {
  const res = await apiFetch(`/api/v1/history/${encodeURIComponent(entryId)}/undo`, { method: 'POST' })
  return responseBody(res, 'Failed to undo')
}
