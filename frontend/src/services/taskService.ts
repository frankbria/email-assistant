// frontend/src/services/taskService.ts
import { AssistantTask, RawMongoTask } from '@/types/api'
import { ObjectId } from 'mongodb'
import { showToast } from '@/utils/toast'
import { getCurrentUserId } from './userService'

// Helper to normalize MongoDB document ID
function normalizeMongoId(doc: { _id?: string | ObjectId; id?: string }): string {
  if (doc._id) {
    // make sure it's a plain string
    return typeof doc._id === "string" ? doc._id : doc._id.toString();
  }
  if (doc.id) {
    return doc.id;
  }
  console.error("Document missing both _id and id:", doc);
  // fallback synthetic ID
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
    // console.log('Raw JSON:', data); // Debug log
    
    return data.map((task: RawMongoTask) => {
      // Get the MongoDB ID directly
      const taskId = task._id || task.id || normalizeMongoId(task);
      
      // Handle email separately - it needs special treatment
      let emailWithId = task.email;
      if (emailWithId) {
        // If email exists, ensure it has an ID
        // First check if it already has an _id or id
        if (emailWithId._id || emailWithId.id) {
          emailWithId = {
            ...emailWithId,
            id: normalizeMongoId(emailWithId)
          };
        } else {
          // If the email doesn't have its own ID, generate one
          emailWithId = {
            ...emailWithId,
            id: `email-${taskId}`
          };
        }
      }
      
      return {
        ...task,
        id: taskId,
        _id: undefined, // Remove the MongoDB _id to avoid duplication
        user_id: task.user_id || userId,
        email: emailWithId
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