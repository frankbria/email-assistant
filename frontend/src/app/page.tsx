// frontend/src/app/page.tsx
'use client'

import { useEffect, useState, useCallback } from 'react'
import { JobCardSkeleton } from '@/components/JobCardSkeleton'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ErrorBanner } from '@/components/ErrorBanner'
import { JobCard } from '@/components/JobCard'
import { showToast } from '@/utils/toast'
import type { Job, JobCard as QueuedJob } from '@/types/api'
import { fetchJobs } from '@/services/jobsService'

function JobQueue() {
  const [jobCards, setJobCards] = useState<QueuedJob[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const showQueue = useCallback((cards: QueuedJob[]) => {
    setJobCards(cards)
    setError(null)
    setLoading(false)
  }, [])

  const showFailure = useCallback((error: unknown) => {
    const errorMessage = error instanceof Error ? error.message : 'Failed to load jobs'
    setError(errorMessage)
    showToast.error(errorMessage)
    setJobCards([])
    setLoading(false)
  }, [])

  useEffect(() => {
    fetchJobs().then(showQueue, showFailure)
  }, [showQueue, showFailure])

  const reloadQueue = useCallback(() => {
    setLoading(true)
    setError(null)
    fetchJobs().then(showQueue, showFailure)
  }, [showQueue, showFailure])

  const replaceJob = useCallback((job: Job) => {
    setJobCards((cards) => cards.map((card) => (card.job._id === job._id ? { ...card, job } : card)))
  }, [])

  const removeJob = useCallback((jobId: string) => {
    setJobCards((cards) => cards.filter((card) => card.job._id !== jobId))
  }, [])

  if (loading) {
    return (
      <div
        className="space-y-4 flex flex-col items-center"
        role="region"
        aria-label="loading jobs"
      >
        <JobCardSkeleton />
        <JobCardSkeleton />
        <JobCardSkeleton />
      </div>
    )
  }

  if (error) {
    return <ErrorBanner message={error} onRetry={reloadQueue} />
  }

  if (jobCards.length === 0) {
    return (
      <div className="flex justify-center pt-10">
        <EmptyState message="No open jobs" actionLabel="Refresh jobs" onAction={reloadQueue} />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {jobCards.map((card) => (
        <JobCard key={card.job._id} card={card} onReplaced={replaceJob} onRemoved={removeJob} />
      ))}
    </div>
  )
}

export default function Page() {
  return (
    <ErrorBoundary>
      <JobQueue />
    </ErrorBoundary>
  )
}
