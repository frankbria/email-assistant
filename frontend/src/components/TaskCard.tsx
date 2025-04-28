// components/TaskCard.tsx
import { useState, useRef, useLayoutEffect } from 'react';
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger,
  DropdownMenuItem,
} from "@/components/ui/dropdown-menu";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ChevronDown, Loader2, Check } from "lucide-react";
import { showToast } from '@/utils/toast'

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

export function TaskCard({
  summary,
  categoryIcon,
  contextCategory,
  suggestedActions,
  onAction,
  subject,
  sender,
  body,
}: TaskCardProps) {
  const [mobileExpanded, setMobileExpanded] = useState(false);
  const [hovered, setHovered] = useState(false);
  const [showBelow, setShowBelow] = useState(false);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [selectedAction, setSelectedAction] = useState<string | null>(null);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const isMobile = useIsMobile();
  const hoverTimeout = useRef<NodeJS.Timeout | null>(null);
  //const { toast } = useToast();

  useLayoutEffect(() => {
    if (!(hovered && !isMobile)) return;
    const rect = cardRef.current?.getBoundingClientRect();
    if (rect) {
      setShowBelow(rect.top < 140);
    }
  }, [hovered, isMobile]);

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

  const handleActionSelect = (action: string) => {
    setSelectedAction(action);
    setIsConfirmOpen(true);
  };

  const handleActionConfirm = async () => {
    if (!selectedAction || pendingAction) return;
    
    setIsConfirmOpen(false);
    setPendingAction(selectedAction);
    try {
      await onAction?.(selectedAction);
      showToast.success(`Successfully executed: ${selectedAction}`);
    } catch {
      showToast.error(`Failed to execute: ${selectedAction}`);
    } finally {
      setPendingAction(null);
      setSelectedAction(null);
    }
  };

  const handleActionCancel = () => {
    setIsConfirmOpen(false);
    setSelectedAction(null);
  };

  const expanded = isMobile ? mobileExpanded : hovered;

  return (
    <div
      ref={cardRef}
      className="w-full max-w-md rounded-2xl bg-white shadow-sm hover:shadow-md hover:bg-slate-50 hover:border hover:border-slate-300 p-4 space-y-2 flex flex-col transition-all duration-200 cursor-pointer relative"
      title={isMobile ? contextCategory : undefined}
      onClick={handleClick}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
    >
      {/* Card Header */}
      <div className="flex flex-col gap-1 text-slate-800">
        <div className="flex items-center gap-2">
          {categoryIcon && (
            <span className="inline-block w-5 h-5 align-middle shrink-0">
              {categoryIcon}
            </span>
          )}
          <span className="font-medium text-lg truncate" style={{ maxWidth: 'calc(100% - 2rem)' }}>
            {typeof summary === 'string' ? summary.split(':')[0] : ''}    {/* Title part before ":" */}
          </span>
        </div>

        {/* Second line */}
        {summary.includes(':') && (
          <span className="text-sm text-slate-600">
            {summary.split(':').slice(1).join(':').trim()}
          </span>
        )}
      </div>


      {/* ACTION BUTTON (Dropdown) */}
      <div className="pt-2">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button 
              variant="outline" 
              size="sm" 
              className="flex items-center gap-1"
              disabled={!!pendingAction}
            >
              {pendingAction ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
              {pendingAction ? "Processing..." : "Actions"}
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="start">
            {suggestedActions.map((action, idx) => (
              <DropdownMenuItem
                key={idx}
                onClick={() => handleActionSelect(action)}
                disabled={!!pendingAction}
                className="flex items-center gap-2"
              >
                {pendingAction === action ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Check className="h-4 w-4 opacity-0 group-hover:opacity-100" />
                )}
                {action}
              </DropdownMenuItem>
            ))}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* CONFIRMATION DIALOG */}
      <Dialog open={isConfirmOpen} onOpenChange={setIsConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Confirm Action</DialogTitle>
            <DialogDescription>
              Are you sure you want to {selectedAction?.toLowerCase()} this task?
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={handleActionCancel}>
              Cancel
            </Button>
            <Button onClick={handleActionConfirm} disabled={!!pendingAction}>
              {pendingAction ? (
                <>
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                  Processing...
                </>
              ) : (
                'Confirm'
              )}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* EXPANDED CONTENT AREA */}
      {expanded && (
        isMobile ? (
          <div className="mt-3 w-full rounded-xl border border-blue-200 bg-blue-50 p-4 space-y-2 text-sm text-blue-900 shadow-inner animate-fade-in">
            {contextCategory && (
              <div className="font-semibold flex items-center gap-1">
                {categoryIcon && <span>{categoryIcon}</span>}
                <span>{contextCategory.charAt(0).toUpperCase() + contextCategory.slice(1)}</span>
              </div>
            )}
            {subject && (
              <div><span className="font-semibold">Subject:</span> {subject}</div>
            )}
            {sender && (
              <div><span className="font-semibold">Sender:</span> {sender}</div>
            )}
            {body && (
              <div className="whitespace-pre-line"><span className="font-semibold">Summary:</span> {body}</div>
            )}
          </div>
        ) : (
          <div
            className={`absolute left-1/2 z-30 -translate-x-1/2 min-w-[260px] max-w-xs bg-slate-900 text-white text-xs rounded-lg shadow-xl p-4 border border-slate-700 animate-fade-in
            ${showBelow ? 'top-full mt-2' : '-top-2 -translate-y-full'}`}
          >
            {/* Pointer arrow */}
            <div
              className={`absolute left-1/2 ${showBelow ? '-top-2 translate-y-0' : 'bottom-0 translate-y-full'} translate-x-[-50%] w-0 h-0 border-x-8 border-x-transparent ${showBelow ? 'border-b-8 border-b-slate-900' : 'border-t-8 border-t-slate-900'}`}
            />
            {contextCategory && (
              <div className="font-semibold flex items-center gap-1 text-blue-200 mb-1">
                {categoryIcon && <span>{categoryIcon}</span>}
                <span>{contextCategory.charAt(0).toUpperCase() + contextCategory.slice(1)}</span>
              </div>
            )}
            {subject && (
              <div><span className="font-semibold">Subject:</span> {subject}</div>
            )}
            {sender && (
              <div><span className="font-semibold">Sender:</span> {sender}</div>
            )}
            {body && (
              <div className="whitespace-pre-line"><span className="font-semibold">Summary:</span> {body}</div>
            )}
          </div>
        )
      )}
    </div>
  );
}
