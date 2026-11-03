// frontend/src/app/page.tsx
'use client'

import { useEffect, useState, useCallback } from 'react'
import { JobCardSkeleton } from '@/components/JobCardSkeleton'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ErrorBanner } from '@/components/ErrorBanner'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { showToast } from '@/utils/toast'
import type { JobCard } from '@/types/api'
import { fetchJobs } from '@/services/jobsService'

function JobList() {
  const [jobCards, setJobCards] = useState<JobCard[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const loadJobs = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      setJobCards(await fetchJobs())
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to load jobs'
      setError(errorMessage)
      showToast.error(errorMessage)
      setJobCards([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    // shortcut: the mount fetch sets loading state synchronously (one extra render); #75 builds the full job queue here.
    // eslint-disable-next-line react-hooks/set-state-in-effect -- see shortcut above
    loadJobs()
  }, [loadJobs])

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
    return <ErrorBanner message={error} onRetry={loadJobs} />
  }

  if (jobCards.length === 0) {
    return (
      <div className="flex justify-center pt-10">
        <EmptyState message="No open jobs" actionLabel="Refresh jobs" onAction={loadJobs} />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6 p-6">
      {jobCards.map(({ job, sender, subject }) => (
        <Card key={job._id}>
          <CardHeader>
            <CardTitle>{job.title}</CardTitle>
            <CardDescription>
              {sender.name ?? sender.email} - {subject}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            {job.evidence[0] && <blockquote className="border-l-2 pl-3 text-muted-foreground">{job.evidence[0]}</blockquote>}
            {job.error && <p className="text-red-600">{job.error}</p>}
            {job.reminder && <p className="text-yellow-700">{job.reminder}</p>}
          </CardContent>
        </Card>
      ))}
    </div>
  )
}

export default function Page() {
  return (
    <ErrorBoundary>
      <div className="flex flex-col h-screen">
        <div className="overflow-auto flex-1">
          <JobList />
        </div>
      </div>
    </ErrorBoundary>
  )
}
