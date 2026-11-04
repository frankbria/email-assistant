// frontend/src/services/historyService.ts

import type { ActionLogEntry, HistoryCard } from '../types/api'
import { apiFetch } from './apiClient'
import { responseBody } from './jobsService'

export async function fetchHistory(): Promise<HistoryCard[]> {
  return responseBody(await apiFetch('/api/v1/history'), 'Failed to load history')
}

// The restore's own entry: a 200 with ok false is a restore that failed, not a refused undo.
export async function undoEntry(entryId: string): Promise<ActionLogEntry> {
  const res = await apiFetch(`/api/v1/history/${encodeURIComponent(entryId)}/undo`, { method: 'POST' })
  return responseBody(res, 'Failed to undo')
}
