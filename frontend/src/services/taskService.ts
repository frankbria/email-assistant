// frontend/src/services/taskService.ts
import { AssistantTask } from '@/types/api'
import { showToast } from '@/utils/toast'

// Map actions to valid status values
export function actionToComplete(): string {
  // For now, all actions mark the task as done
  return 'done'
}

// Track the action type for future use
export function getActionType(action: string): string {
  const actionMap: Record<string, string> = {
    'archive': 'archived',
    'done': 'done',
    'hold': 'pending',
    'in progress': 'in_progress',
    'start': 'in_progress',
    'complete': 'done',
    'mark as done': 'done',
    'mark as complete': 'done',
    'mark as pending': 'pending',
    'mark as in progress': 'in_progress'
  }

  // Convert action to lowercase and remove any extra spaces
  const normalizedAction = action.toLowerCase().trim()
  
  // Check if we have a direct mapping
  if (actionMap[normalizedAction]) {
    return actionMap[normalizedAction]
  }

  // Default to 'done' for actions that imply completion
  if (normalizedAction.includes('done') || normalizedAction.includes('complete')) {
    return 'done'
  }

  // Default to 'in_progress' for actions that imply starting work
  if (normalizedAction.includes('start') || normalizedAction.includes('progress')) {
    return 'in_progress'
  }

  // Default to 'pending' for all other actions
  return 'pending'
}

export async function updateTaskStatus(taskId: string, action: string): Promise<void> {
  try {
    const status = actionToComplete()
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/api/v1/tasks/${taskId}`, {
      method: 'PATCH',
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      credentials: 'include',
      body: JSON.stringify({ 
        status,
        action_taken: action
      })
    })

    if (!response.ok) {
      throw new Error(`Failed to update task (${response.status})`)
    }

    showToast.success(`Task ${action.toLowerCase()} successfully`)
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Failed to update task'
    showToast.error(errorMessage)
    throw error
  }
}

export function getOptimisticUpdate(tasks: AssistantTask[], taskId: string, action: string): AssistantTask[] {
  const status = actionToComplete()
  console.log('Optimistic update:', { taskId, action, status }) // Debug log
  
  // First filter out tasks that are being marked as done
  const filteredTasks = tasks.filter(task => 
    task.id !== taskId || status !== 'done'
  )
  
  // Then update the status of the matching task if it's not being marked as done
  return filteredTasks.map(task => 
    task.id === taskId && status !== 'done'
      ? { ...task, status }
      : task
  )
}

export function getRevertUpdate(tasks: AssistantTask[], taskId: string): AssistantTask[] {
  return tasks.map(task => 
    task.id === taskId 
      ? { ...task, status: 'pending' }
      : task
  )
} 