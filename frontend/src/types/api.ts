export interface EmailMessage {
  id: string
  subject: string
  body: string
  sender: string
  recipient?: string
  context?: string
  user_id: string
}

export interface AssistantTask {
  id: string
  email: EmailMessage
  context: string | null
  summary: string | null
  actions: string[]
  status: string
  suggested_actions?: string[]
  user_id: string
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

export interface UserSettings {
  user_id: string;
  enable_spam_filtering: boolean;
  enable_auto_categorization: boolean;
  skip_low_priority_emails: boolean;
}

export interface WebhookSecurity {
  api_key: string;
  allowed_ips: string[];
  active: boolean;
}