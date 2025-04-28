// frontend/src/app/page.tsx
'use client'

import { useEffect, useState, useCallback } from 'react'
import { TaskCard } from '@/components/TaskCard'
import { TaskCardSkeleton } from '@/components/TaskCardSkeleton'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ErrorBanner } from '@/components/ErrorBanner'
import { showToast } from '@/utils/toast'
import { AssistantTask, MongoDocument } from '@/types/api'
import { getCategoryIcon } from '@/utils/categoryIcon'
import { updateTaskStatus, getOptimisticUpdate, getRevertUpdate, actionToComplete } from '@/services/taskService'

const TASKS_CACHE_KEY = 'cached_tasks_v1';

function TaskList() {
  const [tasks, setTasks] = useState<AssistantTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [readOnly, setReadOnly] = useState(false)

  // Helper to check online status
  const isOnline = typeof navigator !== 'undefined' ? navigator.onLine : true;

  // Fetch tasks from API or cache
  const fetchTasks = useCallback(async () => {
    if (!isOnline) {
      // Offline: load from cache
      const cached = localStorage.getItem(TASKS_CACHE_KEY)
      if (cached) {
        setTasks(JSON.parse(cached))
        setReadOnly(true)
        showToast.info('Offline mode: showing cached tasks (read-only)')
      } else {
        setTasks([])
        setReadOnly(true)
        showToast.warning('Offline mode: no cached tasks available')
      }
      setLoading(false)
      return
    }
    try {
      setLoading(true)
      setError(null)
      setReadOnly(false)
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/api/v1/tasks/?status=active`,
        {cache: 'no-store'}
      )
      if (!response.ok) {
        throw new Error(`Failed to fetch tasks (${response.status})`)
      }
      const data = await response.json()
      const tasksWithIds = data.map((task: AssistantTask & MongoDocument) => ({
        ...task,
        id: task.id || task._id || `task-${Math.random().toString(36).substring(2, 11)}`
      }))
      setTasks(tasksWithIds)
      // Cache tasks for offline use
      localStorage.setItem(TASKS_CACHE_KEY, JSON.stringify(tasksWithIds))
      showToast.success('Tasks loaded successfully')
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to load tasks'
      setError(errorMessage)
      showToast.error(errorMessage)
      setTasks([])
    } finally {
      setLoading(false)
    }
  }, [isOnline])

  useEffect(() => {
    fetchTasks()
    // Listen for online/offline events to update readOnly state
    function handleOnline() {
      setReadOnly(false)
      fetchTasks()
    }
    function handleOffline() {
      setReadOnly(true)
      fetchTasks()
    }
    window.addEventListener('online', handleOnline)
    window.addEventListener('offline', handleOffline)
    return () => {
      window.removeEventListener('online', handleOnline)
      window.removeEventListener('offline', handleOffline)
    }
  }, [fetchTasks])

  const handleRetry = async () => {
    showToast.info('Retrying task fetch...')
    await fetchTasks()
  }

  const handleTaskAction = async (taskId: string, action: string) => {
    if (readOnly || !isOnline) {
      showToast.warning('Offline mode: actions are disabled in read-only mode.')
      return
    }
    try {
      // Optimistically update the task list
      setTasks(prevTasks => getOptimisticUpdate(prevTasks, taskId, action))
      await updateTaskStatus(taskId, action)
      const status = actionToComplete()
      if (status !== 'done') {
        await fetchTasks()
      }
    } catch {
      setTasks(prevTasks => getRevertUpdate(prevTasks, taskId))
      showToast.error('Failed to update task status')
    }
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
        const contextCategory = typeof task.context === 'string' ? task.context : undefined;
        return (
          <TaskCard
            key={task.id}
            summary={task.summary || 'Task from incoming email'}
            contextCategory={contextCategory}
            categoryIcon={getCategoryIcon(contextCategory)}
            suggestedActions={task.suggested_actions || task.actions || []}
            subject={task.email?.subject}
            sender={task.email?.sender}
            body={task.email?.body}
            onAction={(action) => handleTaskAction(task.id, action)}
            readOnly={readOnly}
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