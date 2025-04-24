// app/demo.tsx

'use client'

import { TaskCard } from '@/components/TaskCard'

export default function Demo() {
  const tasks = [
    {
      context: 'Scheduling Request',
      summary: 'Greg is trying to schedule lunch after your meeting.',
      actions: ['Approve', 'Modify Time', 'Hold']
    },
    {
      context: 'Sales Outreach',
      summary: 'Nosto AI wants to demo their analytics platform.',
      actions: ['Ignore', 'Mark as Interested', 'Forward to Ops']
    },
    {
      context: 'Invoice Received',
      summary: 'Invoice from Spark Design for March consulting.',
      actions: ['Forward to Finance', 'Archive']
    }
  ]

  return (
    <div className="space-y-4">
      {tasks.map((task, idx) => (
        <TaskCard key={idx} {...task} />
      ))}
    </div>
  )
}
