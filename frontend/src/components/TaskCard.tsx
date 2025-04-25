// components/TaskCard.tsx

interface TaskCardProps {
  context: string
  summary: string
  actions: string[]
  onAction?: (action: string) => void
}

export function TaskCard({ context, summary, actions, onAction }: TaskCardProps) {
  return (
    <div className="w-full max-w-md rounded-2xl shadow-sm bg-white p-4 space-y-2 flex flex-col">
      <div className="text-sm text-gray-500 font-medium">🗂️ {context}</div>
      <div className="text-base text-gray-800">{summary}</div>
      <div className="flex flex-wrap gap-2 pt-2">
        {actions.map((action, idx) => (
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
