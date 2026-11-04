// app/train/page.tsx
'use client'

import { useCallback, useEffect, useState } from 'react'
import { HugeiconsIcon } from '@hugeicons/react'
import { AiBrain01Icon } from '@hugeicons/core-free-icons'
import { AskOwnerCard } from '@/components/AskOwnerCard'
import { ErrorBanner } from '@/components/ErrorBanner'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { TOUCH_TARGET } from '@/components/JobCard'
import { Button } from '@/components/ui/button'
import { fetchCalibration, startCalibration } from '@/services/calibrationService'
import { showToast } from '@/utils/toast'
import type { JobCard } from '@/types/api'

const POLL_MS = 5000

// Calibration (spec §10.7): the app proposes for recent mail without acting; each reaction teaches it.
function Calibration() {
  const [cards, setCards] = useState<JobCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [running, setRunning] = useState(false)

  const load = useCallback(() => {
    fetchCalibration().then(
      (loaded) => {
        setCards(loaded)
        setError(null)
        setLoading(false)
      },
      (failure: unknown) => {
        setError(failure instanceof Error ? failure.message : 'Failed to load calibration')
        setLoading(false)
      }
    )
  }, [])

  useEffect(load, [load])

  // The run proposes one message at a time, so its cards are picked up while the page is open.
  useEffect(() => {
    if (!running) return
    const timer = setInterval(load, POLL_MS)
    return () => clearInterval(timer)
  }, [running, load])

  async function calibrate() {
    try {
      await startCalibration()
      setRunning(true)
      load()
    } catch (failure) {
      showToast.error(failure instanceof Error ? failure.message : 'Failed to start calibration')
    }
  }

  const removeCard = useCallback((jobId: string) => {
    setCards((current) => current.filter((card) => card.job._id !== jobId))
  }, [])

  return (
    <div className="mx-auto max-w-5xl space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-white p-4 shadow-sm">
        <p className="min-w-0 flex-1 text-sm text-muted-foreground">
          Calibrate runs the assistant over your 100 newest messages without touching them. Tap the action it got right, pick a
          better one, or mark the mail as noise: each answer teaches it and joins your local test set.
        </p>
        <Button className={TOUCH_TARGET} onClick={calibrate}>
          <HugeiconsIcon icon={AiBrain01Icon} />
          {running ? 'Calibrate again' : 'Calibrate'}
        </Button>
      </div>
      {loading ? (
        <p role="status" className="pt-10 text-center text-gray-500">Loading calibration…</p>
      ) : error ? (
        <ErrorBanner message={error} onRetry={load} />
      ) : cards.length === 0 ? (
        <p className="pt-10 text-center text-gray-500">{running ? 'Proposals will appear here as they are made…' : 'Nothing to react to yet'}</p>
      ) : (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {cards.map((card) => (
            <AskOwnerCard key={card.job._id} card={card} calibrating onReplaced={() => removeCard(card.job._id)} onRemoved={removeCard} />
          ))}
        </div>
      )}
    </div>
  )
}

export default function TrainPage() {
  return (
    <ErrorBoundary>
      <Calibration />
    </ErrorBoundary>
  )
}
