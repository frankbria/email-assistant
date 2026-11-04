// frontend/src/app/connections/[pluginId]/setup/page.tsx
'use client'

import { useCallback, useEffect, useState } from 'react'
import { useParams } from 'next/navigation'
import Link from 'next/link'
import { HugeiconsIcon } from '@hugeicons/react'
import { Alert02Icon, CheckmarkCircle01Icon, CircleIcon, Loading03Icon } from '@hugeicons/core-free-icons'
import { checkConnection } from '@/services/connectionsService'
import type { Checklist, SetupStep } from '@/types/api'

const STEP_LOOK = {
  done: { icon: CheckmarkCircle01Icon, color: 'text-green-700 dark:text-green-400', label: 'Done' },
  failing: { icon: Alert02Icon, color: 'text-red-700 dark:text-red-400', label: 'Needs fixing' },
  waiting: { icon: CircleIcon, color: 'text-gray-400', label: 'Waiting on an earlier step' },
} as const

function StepRow({ step, number }: { step: SetupStep; number: number }) {
  const look = STEP_LOOK[step.status]
  return (
    <li data-slot="setup-step" data-status={step.status} className="flex gap-3 rounded-xl border bg-white p-4 text-left dark:bg-gray-800">
      <HugeiconsIcon icon={look.icon} className={`mt-0.5 h-5 w-5 shrink-0 ${look.color}`} aria-hidden="true" />
      <div className="min-w-0">
        <p className="font-medium text-gray-900 dark:text-gray-100">
          {number}. {step.title}
          <span className="sr-only">: {look.label}</span>
        </p>
        {step.detail && <p className="mt-1 text-sm text-red-700 dark:text-red-300">{step.detail}</p>}
      </div>
    </li>
  )
}

export default function SetupChecklistPage() {
  const { pluginId } = useParams<{ pluginId: string }>()
  const [checklist, setChecklist] = useState<Checklist | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [checking, setChecking] = useState(true)

  const settle = useCallback(
    (pending: Promise<Checklist>) =>
      pending
        .then(
          (result) => {
            setChecklist(result)
            setError(null)
          },
          (failure: Error) => {
            setChecklist(null)
            setError(failure.message)
          },
        )
        .finally(() => setChecking(false)),
    [],
  )

  useEffect(() => {
    settle(checkConnection(pluginId))
  }, [pluginId, settle])

  const checkAgain = () => {
    setChecking(true)
    settle(checkConnection(pluginId))
  }

  const allDone = checklist?.steps.every((step) => step.status === 'done')
  return (
    <div className="mx-auto max-w-2xl px-4 pt-6">
      <Link href="/connections" className="text-sm text-blue-700 underline underline-offset-4 dark:text-blue-300">
        Connections
      </Link>
      <h1 className="mb-1 mt-2 text-xl font-semibold text-gray-900 dark:text-gray-100">{checklist?.title ?? 'Setup checklist'}</h1>
      <p className="mb-4 text-sm text-gray-500 dark:text-gray-400">Plugin: {pluginId}</p>
      {error && (
        <p role="alert" className="mb-4 rounded-lg bg-red-50 p-3 text-sm text-red-700">
          {error}
        </p>
      )}
      <div aria-live="polite">
        {checklist && (
          <ol className="flex flex-col gap-3" aria-label="Setup steps">
            {checklist.steps.map((step, index) => (
              <StepRow key={step.title} step={step} number={index + 1} />
            ))}
          </ol>
        )}
        {allDone && <p className="mt-4 font-medium text-green-700 dark:text-green-400">Everything works. Mail can flow.</p>}
        {checklist && checklist.warnings.length > 0 && (
          <section aria-label="Warnings" className="mt-4 flex flex-col gap-2">
            {checklist.warnings.map((warning) => (
              <p key={warning} data-slot="setup-warning" className="flex gap-2 rounded-lg bg-amber-50 p-3 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
                <HugeiconsIcon icon={Alert02Icon} className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                {warning}
              </p>
            ))}
          </section>
        )}
      </div>
      <button
        type="button"
        onClick={checkAgain}
        disabled={checking}
        className="mt-4 flex min-h-[44px] items-center gap-2 rounded-lg bg-blue-600 px-4 py-2.5 font-medium text-white transition-all hover:bg-blue-700 focus-visible:outline-none focus-visible:ring-[3px] focus-visible:ring-blue-500/50 disabled:opacity-60"
      >
        {checking && <HugeiconsIcon icon={Loading03Icon} className="h-4 w-4 animate-spin" aria-hidden="true" />}
        {checking ? 'Checking…' : 'Check again'}
      </button>
    </div>
  )
}
