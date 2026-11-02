// frontend/src/services/apiClient.ts
import { authClient } from '@/lib/auth-client'

export class NotSignedInError extends Error {
  constructor() {
    super('Not signed in')
  }
}

// Every FastAPI call goes through here: it carries the owner's Better Auth JWT, and the
// API derives the user from it. Never send a user id from the client.
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const { data, error } = await authClient.token()
  if (error || !data?.token) throw new NotSignedInError()
  const headers = new Headers(init.headers)
  headers.set('Authorization', `Bearer ${data.token}`)
  return fetch(`${process.env.NEXT_PUBLIC_API_BASE}${path}`, { ...init, headers })
}
