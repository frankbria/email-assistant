// frontend/src/components/PermissionsSection.tsx
'use client'

import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { answerPromotion, fetchPermissions, setPermission } from '@/services/permissionsService'
import type { PermissionLevel, Permissions, VerbPermission } from '@/types/api'

const LEVEL_LABELS: Record<PermissionLevel, string> = {
  autonomous: 'Autonomous',
  ask: 'Ask first',
  never_auto: 'Never automatic',
}
const LEVELS: PermissionLevel[] = ['autonomous', 'ask', 'never_auto']
const PROMOTION_AFTER = 10 // matches the backend's PROMOTION_AFTER (spec §9)

function VerbRow({ row, onChange, rejection, disabled }: { row: VerbPermission; onChange: (level: PermissionLevel) => void; rejection?: string; disabled: boolean }) {
  return (
    <fieldset role="radiogroup" aria-label={row.verb} disabled={disabled} data-slot="permission-row" className="rounded-xl border bg-white dark:bg-gray-800 p-4 text-left transition-all">
      <legend className="sr-only">{row.verb}</legend>
      <p className="font-medium">{row.verb}</p>
      <div className="mt-2 flex flex-wrap gap-3">
        {LEVELS.map((level) => (
          <label key={level} className="flex min-h-[44px] items-center gap-2">
            <input
              type="radio"
              name={`permission-${row.verb}`}
              value={level}
              checked={row.level === level}
              onChange={() => onChange(level)}
              className="focus-visible:ring-[3px] focus-visible:ring-blue-500/50"
            />
            {LEVEL_LABELS[level]}
          </label>
        ))}
      </div>
      <p className="mt-1 text-sm text-gray-500">
        Highest: {LEVEL_LABELS[row.ceiling].toLowerCase()} — {row.reason}
      </p>
      {rejection && (
        <p role="alert" className="mt-2 text-sm text-red-700 dark:text-red-300">
          {rejection}
        </p>
      )}
    </fieldset>
  )
}

export default function PermissionsSection() {
  const [permissions, setPermissions] = useState<Permissions | null>(null)
  const [rejections, setRejections] = useState<Record<string, string>>({})
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false) // one change at a time: each answer replaces all state, so an older one mustn't land last

  useEffect(() => {
    fetchPermissions().then(setPermissions, (failure: Error) => setError(failure.message))
  }, [])

  // A failure is shown under the verb's row: the server's reason for a rejection, else what couldn't be done.
  async function update(verb: string, request: Promise<Permissions>) {
    setSaving(true)
    try {
      setPermissions(await request)
      setRejections((current) => ({ ...current, [verb]: '' }))
    } catch (failure) {
      setRejections((current) => ({ ...current, [verb]: failure instanceof Error ? failure.message : String(failure) }))
    } finally {
      setSaving(false)
    }
  }

  const choose = (verb: string, level: PermissionLevel) => update(verb, setPermission(verb, level))
  const answer = (verb: string, accept: boolean) => update(verb, answerPromotion(verb, accept))

  if (error) return <p role="alert">{error}</p>
  if (!permissions) return <p>Loading permissions…</p>
  return (
    <section aria-labelledby="permissions-heading" className="mx-auto max-w-xl space-y-3 text-left">
      <h2 id="permissions-heading" className="text-lg font-semibold">
        What the assistant may do on its own
      </h2>
      {permissions.file_error && (
        <p role="alert" className="text-sm text-amber-800 dark:text-amber-300">
          permissions.yaml wasn&apos;t applied: {permissions.file_error}
        </p>
      )}
      {permissions.promotions.map((verb) => (
        <section key={verb} role="region" aria-label="Promotion offer" className="rounded-xl border border-blue-300 bg-blue-50 dark:bg-blue-950 p-4">
          <p>
            You approved {PROMOTION_AFTER} {verb} jobs in a row without changes. Let the assistant do these on its own?
          </p>
          <div className="mt-3 flex gap-2">
            <Button disabled={saving} onClick={() => answer(verb, true)}>Make {verb} autonomous</Button>
            <Button variant="outline" disabled={saving} onClick={() => answer(verb, false)}>
              Not now
            </Button>
          </div>
        </section>
      ))}
      {permissions.verbs.map((row) => (
        <VerbRow key={row.verb} row={row} rejection={rejections[row.verb]} disabled={saving} onChange={(level) => choose(row.verb, level)} />
      ))}
    </section>
  )
}
