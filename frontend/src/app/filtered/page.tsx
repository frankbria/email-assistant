// app/filtered/page.tsx
'use client'

import { useCallback, useEffect, useState } from 'react'
import { HugeiconsIcon } from '@hugeicons/react'
import { InboxUploadIcon } from '@hugeicons/core-free-icons'
import { Button } from '@/components/ui/button'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBanner } from '@/components/ErrorBanner'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { TOUCH_TARGET } from '@/components/JobCard'
import { fetchFiltered, undoEntry } from '@/services/historyService'
import { showToast } from '@/utils/toast'
import type { FilteredCard } from '@/types/api'

function FilteredRow({ card, onRestored }: { card: FilteredCard; onRestored: () => void }) {
  const { entry, sender, subject, rationale, restorable } = card
  const [busy, setBusy] = useState(false)

  async function restore() {
    setBusy(true)
    try {
      const restored = await undoEntry(entry._id)
      if (restored.ok) onRestored()
      else showToast.error(restored.error ?? 'Failed to restore')
    } catch (error) {
      showToast.error(error instanceof Error ? error.message : 'Failed to restore')
    }
    setBusy(false)
  }

  return (
    <li className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 rounded-xl bg-white p-4 shadow-sm">
      <div className="min-w-0 flex-1 space-y-1 text-sm">
        <p className="break-words font-medium">
          {sender.name ?? sender.email} - {subject}
        </p>
        {rationale && <p className="text-muted-foreground">{rationale}</p>}
        <p className="text-muted-foreground">{new Date(entry.created_at).toLocaleString()}</p>
      </div>
      {restorable ? (
        <Button variant="outline" className={TOUCH_TARGET} disabled={busy} onClick={restore}>
          <HugeiconsIcon icon={InboxUploadIcon} />
          Restore
        </Button>
      ) : (
        entry.undone && <p className="text-sm text-muted-foreground">Restored</p>
      )}
    </li>
  )
}

function FilteredList() {
  const [cards, setCards] = useState<FilteredCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const showFiltered = useCallback((filtered: FilteredCard[]) => {
    setCards(filtered)
    setLoading(false)
  }, [])

  const showFailure = useCallback((failure: unknown) => {
    const errorMessage = failure instanceof Error ? failure.message : 'Failed to load filtered mail'
    setError(errorMessage)
    showToast.error(errorMessage)
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchFiltered().then(showFiltered, showFailure)
  }, [showFiltered, showFailure])

  const loadFiltered = useCallback(() => {
    setLoading(true)
    setError(null)
    fetchFiltered().then(showFiltered, showFailure)
  }, [showFiltered, showFailure])

  const markRestored = useCallback((restoredId: string) => {
    setCards((current) =>
      current.map((card) =>
        card.entry._id === restoredId ? { ...card, restorable: false, entry: { ...card.entry, undone: true } } : card
      )
    )
  }, [])

  if (loading) {
    return <p role="status" className="pt-10 text-center text-gray-500">Loading filtered mail…</p>
  }

  if (error) {
    return <ErrorBanner message={error} onRetry={loadFiltered} />
  }

  if (cards.length === 0) {
    return (
      <div className="flex justify-center pt-10">
        <EmptyState message="Nothing filtered in the last 30 days" actionLabel="Refresh filtered mail" onAction={loadFiltered} />
      </div>
    )
  }

  return (
    <ol className="mx-auto max-w-2xl space-y-3" aria-label="Filtered">
      {cards.map((card) => (
        <FilteredRow key={card.entry._id} card={card} onRestored={() => markRestored(card.entry._id)} />
      ))}
    </ol>
  )
}

export default function FilteredPage() {
  return (
    <ErrorBoundary>
      <FilteredList />
    </ErrorBoundary>
  )
}
