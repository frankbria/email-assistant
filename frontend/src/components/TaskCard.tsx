// components/TaskCard.tsx

interface TaskCardProps {
  context: string
  summary: string
  actions: string[]
  onAction?: (action: string) => void
}

const DEFAULT_ACTIONS = ['Reply', 'Forward', 'Archive']

export function TaskCard({ context, summary, actions, onAction }: TaskCardProps) {
  // Use default actions if none are provided
  const displayActions = actions.length > 0 ? actions : DEFAULT_ACTIONS

  return (
    <div className="rounded-2xl shadow-sm bg-white p-4 space-y-2 w-96 flex flex-col">
      <div className="text-sm text-gray-500 font-medium">🗂️ {context}</div>
      <div className="text-base text-gray-800">{summary}</div>
      <div className="flex flex-wrap gap-2 pt-2">
        {displayActions.map((action, idx) => (
          <button
            key={idx}
            onClick={() => onAction?.(action)}
            className="px-3 py-1 rounded-full bg-muted text-sm text-gray-700 hover:bg-gray-200"
          >
            {action}
          </button>
        ))}
      </div>
    </div>
  )
}
