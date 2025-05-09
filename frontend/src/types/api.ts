// Client-side representation of an email
export interface EmailMessage {
  id: string;
  subject?: string;
  sender?: string;
  body?: string;
  recipient?: string;
  context?: string | null;
  message_id?: string;
  signature?: string | null;
  user_id: string;
  is_spam?: boolean;
}

export interface AssistantTask {
  id: string;
  user_id: string;
  sender?: string;
  subject?: string;
  summary?: string;
  context?: string | null;
  actions: string[];
  status: string;
  action_taken: string | null;
  email?: EmailMessage;
}


// Server-side MongoDB representation of a task
export interface RawMongoTask {
  _id?: string;
  id?: string;
  user_id?: string;
  sender?: string;
  subject?: string;
  summary?: string;
  context?: string | null;
  actions?: string[];
  status?: string;
  action_taken?: string | null;
  email?: RawMongoEmail;
}

// Server-side MongoDB representation of an email
export interface RawMongoEmail {
  _id?: string;
  id?: string;
  subject?: string;
  sender?: string;
  body?: string;
  recipient?: string;
  context?: string | null;
  message_id?: string;
  signature?: string | null;
  user_id?: string;
  is_spam?: boolean;
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
  incoming_email_address?: string;
}

export interface WebhookSecurity {
  api_key: string;
  allowed_ips: string[];
  active: boolean;
}