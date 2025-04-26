// components/TaskCard.tsx
import { useState } from 'react';

interface TaskCardProps {
  context: string
  summary: string
  actions: string[]
  onAction?: (action: string) => void
}


export function TaskCard({ context, summary, actions, onAction }: TaskCardProps) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className="w-full max-w-md rounded-2xl bg-white shadow-sm hover:shadow-md hover:bg-gray-50 hover:border
       hover:border-gray-300 p-4 space-y-2 flex flex-col transition-all duration-200 cursor-pointer"
      title={typeof window !== 'undefined' && window.innerWidth > 640 ? `From: ${context}` : undefined}
      onClick={() => {
        if (typeof window !== 'undefined' && window.innerWidth <= 640) {
          setExpanded(!expanded);
        }
      }}
    >
      <div className="text-base text-gray-800">{summary}</div>

      {expanded && (
        <div className="text-xs text-gray-500 pt-2">
          {context}
        </div>
      )}

      <div className="flex flex-wrap gap-2 pt-2">
        {actions.map((action, idx) => (
          <button
            key={idx}
            onClick={(e) => {
              e.stopPropagation(); // Prevent expanding if user clicks a button
              onAction?.(action);
            }}
            className="px-3 py-1 rounded-full bg-muted text-sm text-gray-700 hover:bg-gray-200"
          >
            {action}
          </button>
        ))}
      </div>
    </div>
  )
}

