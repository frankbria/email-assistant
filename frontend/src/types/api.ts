export interface EmailMessage {
  id: string
  subject: string
  body: string
  sender: string
  recipient?: string
  context?: string
}

export interface AssistantTask {
  id: string
  email: EmailMessage
  context: string | null
  summary: string | null
  actions: string[]
  status: string
}

export type APIResponse<T> = {
  data: T
  error?: string
}

export type TasksResponse = APIResponse<AssistantTask[]>

// Helper type for MongoDB _id handling
export interface MongoDocument {
  _id?: string
  id?: string
} 