'use client'

import { useState, type FormEvent } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { authClient } from '@/lib/auth-client'

type Mode = 'sign-in' | 'sign-up'

const passwordAutoComplete: Record<Mode, string> = {
  'sign-up': 'new-password',
  'sign-in': 'current-password',
}

export function OwnerAuthForm({ mode }: { mode: Mode }) {
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    const { error: authError } =
      mode === 'sign-up'
        ? await authClient.signUp.email({ name, email, password })
        : await authClient.signIn.email({ email, password })
    setSubmitting(false)
    if (authError) {
      setError(authError.message ?? 'Something went wrong. Try again.')
      return
    }
    // Full page load: start the signed-in app from scratch, with the new session cookie.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- deliberate full reload
    window.location.assign('/')
  }

  return (
    <main className="mx-auto flex max-w-sm flex-col gap-6 px-4 pt-16">
      <div className="space-y-1">
        <h1 className="text-2xl font-semibold">
          {mode === 'sign-up' ? 'Create the owner account' : 'Sign in'}
        </h1>
        {mode === 'sign-up' && (
          <p className="text-sm text-muted-foreground">
            This app has one owner. Once you create this account, sign-up closes.
          </p>
        )}
      </div>
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        {mode === 'sign-up' && (
          <label className="flex flex-col gap-1 text-sm font-medium">
            Name
            <Input
              name="name"
              autoComplete="name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
            />
          </label>
        )}
        <label className="flex flex-col gap-1 text-sm font-medium">
          Email
          <Input
            name="email"
            type="email"
            autoComplete="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            required
          />
        </label>
        <label className="flex flex-col gap-1 text-sm font-medium">
          Password
          <Input
            name="password"
            type="password"
            autoComplete={passwordAutoComplete[mode]}
            minLength={8}
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            required
          />
        </label>
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {error}
          </p>
        )}
        <Button type="submit" disabled={submitting}>
          {mode === 'sign-up' ? 'Create account' : 'Sign in'}
        </Button>
      </form>
    </main>
  )
}
