// frontend/src/services/taskService.ts
import { AssistantTask } from '@/types/api'
import { showToast } from '@/utils/toast'

// Helper to get current user_id from localStorage or default
function getCurrentUserId(): string {
  if (typeof window === 'undefined') return 'default';
  return localStorage.getItem('current_user_id') || 'default';
}

// Helper to normalize MongoDB document ID
interface MongoDocument {
  _id?: string;
  id?: string;
}

function normalizeMongoId(doc: MongoDocument): string {
  // MongoDB returns _id which we need to map to id for frontend consistency
  if (doc._id) {
    return doc._id;
  } else if (doc.id) {
    return doc.id;
  }
  // This should never happen with proper server responses
  console.error('Document missing both _id and id:', doc);
  return `generated-${Date.now()}-${Math.random().toString(36).substring(2, 7)}`;
}

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

export async function fetchTasks(status: string = 'active', spamFilter: boolean = false): Promise<AssistantTask[]> {
  const userId = getCurrentUserId();
  try {
    const response = await fetch(
      `${process.env.NEXT_PUBLIC_API_BASE}/api/v1/tasks/?status=${status}&spam=${spamFilter}&user_id=${userId}`,
      {cache: 'no-store'}
    );

    if (!response.ok) {
      throw new Error(`Failed to fetch tasks (${response.status})`);
    }
    
    const data = await response.json();
    return data.map((task: AssistantTask) => {
      // Normalize the MongoDB ID
      const normalizedId = normalizeMongoId(task);
      
      return {
        ...task,
        id: normalizedId,
        user_id: task.user_id || userId,
        // Ensure the email also has a normalized ID
        email: task.email ? {
          ...task.email,
          id: normalizeMongoId(task.email)
        } : task.email
      };
    });
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : 'Failed to fetch tasks';
    showToast.error(errorMessage);
    throw error;
  }
}

export async function updateTaskStatus(taskId: string, action: string): Promise<void> {
  try {
    const status = actionToComplete();
    const userId = getCurrentUserId();
    const response = await fetch(`${process.env.NEXT_PUBLIC_API_BASE}/api/v1/tasks/${taskId}?user_id=${userId}`, {
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