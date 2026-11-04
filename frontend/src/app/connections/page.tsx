// frontend/src/app/connections/page.tsx
'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { HugeiconsIcon } from '@hugeicons/react'
import { Alert02Icon, CheckmarkCircle01Icon, Loading03Icon } from '@hugeicons/core-free-icons'
import { fetchConnections } from '@/services/connectionsService'
import type { Connection, DiagnosisKind } from '@/types/api'

const REFRESH_MS = 30_000 // the server re-diagnoses every 60 s; this keeps a repair visible as it happens
const SETUP_KINDS = new Set(['proton', 'gmail']) // plugins with a setup checklist

const KIND_LABELS: Record<DiagnosisKind, string> = {
  ok: 'Connected',
  bridge_restarted: 'Connected',
  bridge_restarting: 'Repairing',
  plugin_restarting: 'Repairing',
  plugin_failed: 'Not working',
  owner_action: 'Needs you',
  waiting_for_login: 'Needs you',
  machine_offline: 'Offline',
}

function headline(connection: Connection): { label: string; healthy: boolean } {
  if (connection.status === 'refused') return { label: 'Refused', healthy: false }
  if (connection.status === 'disabled') return { label: 'Disabled', healthy: false }
  if (!connection.diagnosis) return { label: 'Checking…', healthy: false }
  const label = KIND_LABELS[connection.diagnosis.kind]
  return { label, healthy: label === 'Connected' }
}

function ConnectionRow({ connection }: { connection: Connection }) {
  const { label, healthy } = headline(connection)
  const detail = connection.status === 'refused' ? connection.reason : connection.diagnosis?.message ?? connection.reason
  const layer = connection.diagnosis?.first_failing_layer
  return (
    <li
      data-slot="connection-row"
      className="rounded-xl border bg-white dark:bg-gray-800 p-4 text-left transition-all"
    >
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold text-gray-900 dark:text-gray-100">{connection.plugin_id}</p>
          {connection.account && <p className="break-all text-sm text-gray-500 dark:text-gray-400">{connection.account}</p>}
        </div>
        <span
          className={`flex shrink-0 items-center gap-1 rounded-full px-2.5 py-1 text-sm font-medium ${
            healthy ? 'bg-green-100 text-green-800' : 'bg-amber-100 text-amber-900'
          }`}
        >
          <HugeiconsIcon
            icon={connection.repairing ? Loading03Icon : healthy ? CheckmarkCircle01Icon : Alert02Icon}
            className={`h-4 w-4 ${connection.repairing ? 'animate-spin' : ''}`}
            aria-hidden="true"
          />
          {label}
        </span>
      </div>
      {detail && <p className="mt-2 text-sm text-gray-700 dark:text-gray-300">{detail}</p>}
      {layer && <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">First failing layer: {layer}</p>}
      {connection.repairing && <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Repair in progress.</p>}
      {/* A plugin that hasn't connected yet can't say what it is; the server gives it the Proton checklist. */}
      {connection.status !== 'disabled' && (connection.plugin_name === null || SETUP_KINDS.has(connection.plugin_name)) && (
        <Link
          href={`/connections/${encodeURIComponent(connection.plugin_id)}/setup`}
          className="mt-2 inline-block text-sm font-medium text-blue-700 underline underline-offset-4 dark:text-blue-300"
        >
          Setup checklist
        </Link>
      )}
      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        Last sync: {connection.last_synced_at ? new Date(connection.last_synced_at).toLocaleString() : 'not yet'}
      </p>
    </li>
  )
}

export default function ConnectionsPage() {
  const [connections, setConnections] = useState<Connection[] | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    const load = () =>
      fetchConnections().then(
        (rows) => {
          if (!active) return
          setConnections(rows)
          setError(null)
        },
        (failure: Error) => active && setError(failure.message),
      )
    load()
    const timer = setInterval(load, REFRESH_MS)
    return () => {
      active = false
      clearInterval(timer)
    }
  }, [])

  return (
    <div className="mx-auto max-w-2xl px-4 pt-6">
      <h1 className="mb-4 text-xl font-semibold text-gray-900 dark:text-gray-100">Connections</h1>
      {error && (
        <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
      <div aria-live="polite">
        {connections === null && !error && <p className="text-gray-500 dark:text-gray-400">Checking connections…</p>}
        {connections?.length === 0 && (
          <p className="text-gray-500 dark:text-gray-400">No mailboxes are configured. Add one to plugins.yaml and restart the app.</p>
        )}
        {connections && connections.length > 0 && (
          <ul className="flex flex-col gap-3" aria-label="Mailbox connections">
            {connections.map((connection) => (
              <ConnectionRow key={connection.plugin_id} connection={connection} />
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
