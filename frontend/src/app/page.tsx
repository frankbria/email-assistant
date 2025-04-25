// frontend/app/page.tsx
'use client'

import { useEffect, useState } from 'react'
import { TaskCard } from '@/components/TaskCard'

interface Task {
  id: string
  email: {
    id: string
    subject: string
    sender: string
    body: string
  }
}

interface RawTask {
  id?: string
  _id?: string
  email: {
    id: string
    subject: string
    sender: string
    body: string
  }
}

export default function Page() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchTasks = async () => {
      try {
        const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/api/v1/tasks/`, {
          method: 'GET',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
          },
          credentials: 'include',
        })
        if (!response.ok) {
          throw new Error(`HTTP error! status: ${response.status}`)
        }
        const data = await response.json()
        // Ensure each task has a unique ID
        const tasksWithIds = data.map((task: RawTask) => ({
          ...task,
          id: task.id || task._id || `task-${Math.random().toString(36).substr(2, 9)}`
        }))
        setTasks(tasksWithIds)
      } catch (error) {
        console.error('Error fetching tasks:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchTasks()
  }, [])

  if (loading) {
    return <div className="text-center text-gray-500 pt-10">Loading tasks...</div>
  }

  if (tasks.length === 0) {
    return <div className="text-center text-gray-500 pt-10">No tasks found.</div>
  }

  return (
    <div className="space-y-4 flex flex-col items-center">
      {tasks.map((task) => (
        <TaskCard
          key={task.id}
          context={task.email.subject}
          summary={task.email.body}
          actions={['Reply', 'Forward', 'Archive']}
        />
      ))}
    </div>
  )
} 