// app/history/page.tsx
'use client'

import { useCallback, useEffect, useState } from 'react'
import { HugeiconsIcon } from '@hugeicons/react'
import { Undo02Icon } from '@hugeicons/core-free-icons'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBanner } from '@/components/ErrorBanner'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { TOUCH_TARGET } from '@/components/JobCard'
import { fetchHistory, undoEntry } from '@/services/historyService'
import { showToast } from '@/utils/toast'
import type { HistoryAction, HistoryCard } from '@/types/api'

const ACTION_LABELS: Record<HistoryAction, string> = {
  sent: 'Sent reply',
  archived: 'Archived',
  done: 'Done',
  snoozed: 'Snoozed',
  dismissed: 'Dismissed',
  restored: 'Restored',
}

// MongoDB hands the backend naive datetimes, so the API's UTC timestamps arrive without a zone.
function localTime(utcTimestamp: string): string {
  return new Date(/Z|[+-]\d\d:\d\d$/.test(utcTimestamp) ? utcTimestamp : `${utcTimestamp}Z`).toLocaleString()
}

function HistoryRow({ card, onUndone }: { card: HistoryCard; onUndone: (restore: HistoryCard) => void }) {
  const { entry, sender, subject } = card
  const [busy, setBusy] = useState(false)

  async function undo() {
    setBusy(true)
    try {
      const restore = await undoEntry(entry._id)
      if (restore.ok) onUndone({ entry: restore, sender, subject })
      else showToast.error(restore.error ?? 'Failed to undo')
    } catch (error) {
      showToast.error(error instanceof Error ? error.message : 'Failed to undo')
    }
    setBusy(false)
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-xl bg-white p-4 shadow-sm">
      <div className="min-w-0 flex-1 space-y-1 text-sm">
        <p className="font-medium">{ACTION_LABELS[entry.action]}</p>
        <p className="break-words">
          {sender.name ?? sender.email} - {subject}
        </p>
        <p className="text-muted-foreground">
          {entry.by === 'owner' ? 'You' : 'Assistant'} · {localTime(entry.created_at)}
        </p>
        {entry.error && <p className="text-red-600">{entry.error}</p>}
      </div>
      {entry.undone ? (
        <p className="text-sm text-muted-foreground">Undone</p>
      ) : entry.undoable ? (
        <Button variant="outline" className={TOUCH_TARGET} disabled={busy} onClick={undo}>
          <HugeiconsIcon icon={Undo02Icon} />
          Undo
        </Button>
      ) : (
        entry.action === 'sent' && <p className="text-sm text-muted-foreground">Can&apos;t be unsent</p>
      )}
    </li>
  )
}

function Timeline() {
  const [cards, setCards] = useState<HistoryCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const showHistory = useCallback((history: HistoryCard[]) => {
    setCards(history)
    setLoading(false)
  }, [])

  const showFailure = useCallback((failure: unknown) => {
    const errorMessage = failure instanceof Error ? failure.message : 'Failed to load history'
    setError(errorMessage)
    showToast.error(errorMessage)
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchHistory().then(showHistory, showFailure)
  }, [showHistory, showFailure])

  const loadHistory = useCallback(() => {
    setLoading(true)
    setError(null)
    fetchHistory().then(showHistory, showFailure)
  }, [showHistory, showFailure])

  const markUndone = useCallback((undoneId: string, restore: HistoryCard) => {
    setCards((current) => [
      restore,
      ...current.map((card) => (card.entry._id === undoneId ? { ...card, entry: { ...card.entry, undone: true } } : card)),
    ])
  }, [])

  if (loading) {
    return <p role="status" className="pt-10 text-center text-gray-500">Loading history…</p>
  }

  if (error) {
    return <ErrorBanner message={error} onRetry={loadHistory} />
  }

  if (cards.length === 0) {
    return (
      <div className="flex justify-center pt-10">
        <EmptyState message="Nothing has happened yet" actionLabel="Refresh history" onAction={loadHistory} />
      </div>
    )
  }

  return (
    <ol className="mx-auto max-w-2xl space-y-3" aria-label="History">
      {cards.map((card) => (
        <HistoryRow key={card.entry._id} card={card} onUndone={(restore) => markUndone(card.entry._id, restore)} />
      ))}
    </ol>
  )
}

export default function HistoryPage() {
  return (
    <ErrorBoundary>
      <Timeline />
    </ErrorBoundary>
  )
}
