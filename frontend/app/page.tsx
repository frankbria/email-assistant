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

export default function Page() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const fetchTasks = async () => {
      try {
        const response = await fetch('/api/v1/tasks')
        const data = await response.json()
        setTasks(data)
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
    <div className="space-y-4">
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