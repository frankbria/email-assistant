// frontend/app/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { TaskCard } from '@/components/TaskCard'
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
    return <div className="text-center text-gray-500 pt-10">Loading tasks...</div>
  }

  if (error) {
    return <ErrorBanner message={error} onRetry={handleRetry} />
  }

  if (tasks.length === 0) {
    return (
      <div className="text-center pt-10">
        <p className="text-gray-500 mb-4">No tasks found</p>
        <button
          onClick={() => {
            showToast.info('Refreshing tasks...')
            fetchTasks()
          }}
          className="px-4 py-2 text-sm bg-gray-100 text-gray-700 rounded-md hover:bg-gray-200"
        >
          Refresh
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-4 flex flex-col items-center">
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