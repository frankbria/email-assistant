// frontend/src/app/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { TaskCard } from '@/components/TaskCard'
import { TaskCardSkeleton } from '@/components/TaskCardSkeleton'
import { EmptyState } from '@/components/EmptyState'
import { ErrorBoundary } from '@/components/ErrorBoundary'
import { ErrorBanner } from '@/components/ErrorBanner'
import { showToast } from '@/utils/toast'
import { AssistantTask, MongoDocument } from '@/types/api'
import { getCategoryIcon } from '@/utils/categoryIcon'
import { updateTaskStatus, getOptimisticUpdate, getRevertUpdate, actionToComplete } from '@/services/taskService'

function TaskList() {
  const [tasks, setTasks] = useState<AssistantTask[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchTasks = async () => {
    try {
      setLoading(true)
      setError(null)
      const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/api/v1/tasks/?status=active`, {
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

  const handleTaskAction = async (taskId: string, action: string) => {
    try {
      console.log('Starting task action:', { taskId, action }) // Debug log
      
      // Optimistically update the task list
      setTasks(prevTasks => {
        const updatedTasks = getOptimisticUpdate(prevTasks, taskId, action)
        console.log('Optimistically updated tasks:', updatedTasks) // Debug log
        return updatedTasks
      })
      
      // Update the task status in the backend
      await updateTaskStatus(taskId, action)
      console.log('Backend update successful') // Debug log
      
      // Only refresh the task list if the task wasn't marked as done
      const status = actionToComplete()
      if (status !== 'done') {
        await fetchTasks()
        console.log('Task list refreshed') // Debug log
      }
    } catch (error) {
      console.error('Error in handleTaskAction:', error) // Debug log
      // Revert optimistic update on error
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
        console.log('Rendering task:', task) // Debug task being rendered
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