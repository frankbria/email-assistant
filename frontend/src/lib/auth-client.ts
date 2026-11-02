import { createAuthClient } from 'better-auth/react'
import { jwtClient } from 'better-auth/client/plugins'

// In the browser the auth API is same-origin; NEXT_PUBLIC_BETTER_AUTH_URL is for other callers.
export const authClient = createAuthClient({
  baseURL: process.env.NEXT_PUBLIC_BETTER_AUTH_URL,
  plugins: [jwtClient()],
})
