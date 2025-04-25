// frontend/app/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { TaskCard } from '@/components/TaskCard'
import { TaskCardSkeleton } from '@/components/TaskCardSkeleton'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ErrorBanner } from '@/components/ErrorBanner'
import { showToast } from '@/utils/toast'
import { AssistantTask, MongoDocument } from '@/types/api'

function TaskList() {
  const [tasks, setTasks] = useState<AssistantTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchTasks = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/api/v1/tasks/`, {
        method: 'GET',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'application/json',
        },
        credentials: 'include',
      })
      
      if (!response.ok) {
        throw new Error(`Failed to fetch tasks (${response.status})`)
      }
      
      const data = await response.json()
      console.log('Raw task data from API:', data) // Debug log
      
      const tasksWithIds = data.map((task: AssistantTask & MongoDocument) => {
        console.log('Processing task:', task) // Debug individual task
        return {
          ...task,
          id: task.id || task._id || `task-${Math.random().toString(36).substring(2, 11)}`
        }
      })
      console.log('Processed tasks:', tasksWithIds) // Debug processed tasks
      setTasks(tasksWithIds)
      showToast.success('Tasks loaded successfully')
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to load tasks'
      setError(errorMessage)
      showToast.error(errorMessage)
      // Clear tasks on error
      setTasks([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchTasks()
  }, [])

  const handleRetry = async () => {
    showToast.info('Retrying task fetch...')
    await fetchTasks()
  }

  if (loading) {
    return (
      <div 
        className="space-y-4 flex flex-col items-center"
        role="region"
        aria-label="Loading tasks"
      >
        <TaskCardSkeleton />
        <TaskCardSkeleton />
        <TaskCardSkeleton />
      </div>
    )
  }

  if (error) {
    return <ErrorBanner message={error} onRetry={handleRetry} />
  }

  if (tasks.length === 0) {
    return (
      <div className="flex justify-center pt-10">
        <EmptyState
          message="No tasks found"
          actionLabel="Refresh tasks"
          onAction={() => {
            showToast.info('Refreshing tasks...')
            fetchTasks()
          }}
        />
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
      {tasks.map((task) => {
        console.log('Rendering task:', task) // Debug task being rendered
        return (
          <TaskCard
            key={task.id}
            context={task.email.subject}
            summary={task.email.body}
            actions={task.actions || []} // Ensure actions is never undefined
          />
        )
      })}
    </div>
  )
}

export default function Page() {
  return (
    <ErrorBoundary>
      <TaskList />
    </ErrorBoundary>
  )
} 