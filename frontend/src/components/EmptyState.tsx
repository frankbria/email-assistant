import { Inbox } from 'lucide-react'

interface EmptyStateProps {
  message?: string
  actionLabel?: string
  onAction?: () => void
}

export function EmptyState({ 
  message = 'No tasks found', 
  actionLabel = 'Refresh',
  onAction
}: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center p-8 bg-white rounded-2xl shadow-sm w-96">
      <div className="bg-gray-100 p-4 rounded-full mb-4">
        <Inbox className="w-8 h-8 text-gray-500" />
      </div>
      <h3 className="text-lg font-medium text-gray-900 mb-2">
        {message}
      </h3>
      <p className="text-sm text-gray-500 text-center mb-4">
        No tasks are currently available. Check back later or refresh to see new tasks.
      </p>
      {onAction && (
        <button
          onClick={onAction}
          className="px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        >
          {actionLabel}
        </button>
      )}
    </div>
  )
} 