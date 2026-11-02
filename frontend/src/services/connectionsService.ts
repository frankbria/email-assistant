// frontend/src/services/connectionsService.ts

import type { Checklist, Connection } from '../types/api'
import { apiFetch } from './apiClient'

export async function fetchConnections(): Promise<Connection[]> {
  const res = await apiFetch('/api/v1/connections')
  if (!res.ok) throw new Error('Failed to load connections')
  return await res.json()
}

export async function checkConnection(pluginId: string): Promise<Checklist> {
  const res = await apiFetch(`/api/v1/connections/${encodeURIComponent(pluginId)}/check`, { method: 'POST' })
  if (!res.ok) throw new Error('Failed to check the connection')
  return await res.json()
}
