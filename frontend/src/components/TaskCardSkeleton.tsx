export function TaskCardSkeleton() {
  return (
    <div 
      role="article"
      className="rounded-2xl shadow-sm bg-white p-4 space-y-2 w-96 flex flex-col animate-pulse"
    >
      {/* Context skeleton */}
      <div className="h-5 bg-gray-200 rounded w-2/3" />
      
      {/* Summary skeleton - two lines */}
      <div className="space-y-2">
        <div className="h-4 bg-gray-200 rounded w-full" />
        <div className="h-4 bg-gray-200 rounded w-4/5" />
      </div>
      
      {/* Action buttons skeleton */}
      <div className="flex flex-wrap gap-2 pt-2">
        <div className="h-7 bg-gray-200 rounded-full w-20" />
        <div className="h-7 bg-gray-200 rounded-full w-24" />
        <div className="h-7 bg-gray-200 rounded-full w-16" />
      </div>
    </div>
  )
} 