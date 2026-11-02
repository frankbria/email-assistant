// frontend/src/services/connectionsService.ts

import type { Connection } from '../types/api'
import { apiFetch } from './apiClient'

export async function fetchConnections(): Promise<Connection[]> {
  const res = await apiFetch('/api/v1/connections')
  if (!res.ok) throw new Error('Failed to load connections')
  return await res.json()
}
