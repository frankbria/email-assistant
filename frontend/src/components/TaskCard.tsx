// components/TaskCard.tsx
import { useState, useRef, useLayoutEffect } from 'react';

function useIsMobile() {
  if (typeof window === 'undefined') return false;
  return window.matchMedia('(max-width: 640px)').matches;
}

interface TaskCardProps {
  summary: string;
  categoryIcon?: string;
  contextCategory?: string;
  suggestedActions: string[];
  onAction?: (action: string) => void;
  subject?: string;
  sender?: string;
  body?: string;
}

export function TaskCard({ summary, categoryIcon, contextCategory, suggestedActions, onAction, subject, sender, body }: TaskCardProps) {
  const [mobileExpanded, setMobileExpanded] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [showBelow, setShowBelow] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const isMobile = useIsMobile();
  const hoverTimeout = useRef<NodeJS.Timeout | null>(null);

  useLayoutEffect(() => {
    if (!(hovered && !isMobile)) return;
    const rect = cardRef.current?.getBoundingClientRect();
    if (rect) {
      setShowBelow(rect.top < 140);
    }
  }, [hovered, isMobile]);

  // Only allow expand/collapse on click for mobile, and only on hover for desktop
  const handleClick = () => {
    if (isMobile) {
      setMobileExpanded((prev) => !prev);
    }
  };
  const handleMouseEnter = () => {
    if (!isMobile) {
      hoverTimeout.current = setTimeout(() => setHovered(true), 120);
    }
  };
  const handleMouseLeave = () => {
    if (!isMobile) {
      if (hoverTimeout.current) {
        clearTimeout(hoverTimeout.current);
        hoverTimeout.current = null;
      }
      setHovered(false);
    }
  };

  const expanded = isMobile ? mobileExpanded : hovered;

  return (
    <div
      ref={cardRef}
      className="w-full max-w-md rounded-2xl bg-white shadow-sm hover:shadow-md hover:bg-gray-50 hover:border
       hover:border-gray-300 p-4 space-y-2 flex flex-col transition-all duration-200 cursor-pointer relative"
      title={isMobile ? contextCategory : undefined}
      onClick={handleClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      <div className="flex items-center gap-2 text-base text-gray-800">
        {categoryIcon && (
          <span className="inline-block w-5 h-5 align-middle shrink-0">{categoryIcon}</span>
        )}
        <span className="truncate font-medium text-lg" style={{ maxWidth: 'calc(100% - 2rem)' }}>
          {summary}
        </span>
      </div>

      <div className="flex flex-wrap gap-2 pt-2">
        {suggestedActions.map((action, idx) => (
          <button
            key={idx}
            onClick={e => {
              e.stopPropagation();
              onAction?.(action);
            }}
            className="px-3 py-2 rounded-full bg-muted text-sm text-gray-700 hover:bg-gray-200 min-w-[44px] min-h-[44px] focus:outline-none focus:ring-2 focus:ring-blue-400"
            style={{ lineHeight: '1.2' }}
          >
            {action}
          </button>
        ))}
      </div>

      {expanded && (
        isMobile ? (
          <div className="mt-3 w-full rounded-xl border border-blue-200 bg-blue-50 p-4 space-y-2 text-sm text-blue-900 shadow-inner animate-fade-in">
            {contextCategory && (
              <div className="font-semibold flex items-center gap-1">
                {categoryIcon && <span>{categoryIcon}</span>}
                <span>{contextCategory}</span>
              </div>
            )}
            {subject && (
              <div><span className="font-semibold">Subject:</span> {subject}</div>
            )}
            {sender && (
              <div><span className="font-semibold">Sender:</span> {sender}</div>
            )}
            {body && (
              <div className="whitespace-pre-line"><span className="font-semibold">Body:</span> {body}</div>
            )}
          </div>
        ) : (
          <div
            className={`absolute left-1/2 z-30 -translate-x-1/2 min-w-[260px] max-w-xs bg-gray-900 text-white text-xs rounded-lg shadow-xl p-4 border border-gray-700 animate-fade-in
              ${showBelow ? 'top-full mt-2' : '-top-2 -translate-y-full'}`}
          >
            {/* Pointer arrow */}
            <div
              className={`absolute left-1/2 ${showBelow ? '-top-2 translate-y-0' : 'bottom-0 translate-y-full'} translate-x-[-50%] w-0 h-0 border-x-8 border-x-transparent ${showBelow ? 'border-b-8 border-b-gray-900' : 'border-t-8 border-t-gray-900'}`}
            />
            {contextCategory && (
              <div className="font-semibold flex items-center gap-1 text-blue-200 mb-1">
                {categoryIcon && <span>{categoryIcon}</span>}
                <span>{contextCategory}</span>
              </div>
            )}
            {subject && (
              <div><span className="font-semibold">Subject:</span> {subject}</div>
            )}
            {sender && (
              <div><span className="font-semibold">Sender:</span> {sender}</div>
            )}
            {body && (
              <div className="whitespace-pre-line"><span className="font-semibold">Body:</span> {body}</div>
            )}
          </div>
        )
      )}
    </div>
  );
}

