// frontend/src/services/permissionsService.ts

import type { PermissionLevel, Permissions } from '../types/api'
import { apiFetch } from './apiClient'

async function permissionsFrom(res: Response, failure: string): Promise<Permissions> {
  if (res.status === 422) throw new Error((await res.json()).detail) // the server's reason, e.g. the verb's ceiling
  if (!res.ok) throw new Error(failure)
  return await res.json()
}

export async function fetchPermissions(): Promise<Permissions> {
  return permissionsFrom(await apiFetch('/api/v1/permissions'), 'Failed to load permissions')
}

export async function setPermission(verb: string, level: PermissionLevel): Promise<Permissions> {
  const res = await apiFetch(`/api/v1/permissions/${encodeURIComponent(verb)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ level }),
  })
  return permissionsFrom(res, 'Failed to save the permission')
}

export async function answerPromotion(verb: string, accept: boolean): Promise<Permissions> {
  const res = await apiFetch(`/api/v1/permissions/promotions/${encodeURIComponent(verb)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ accept }),
  })
  return permissionsFrom(res, 'Failed to answer the promotion offer')
}
