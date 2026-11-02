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
}

export type DiagnosisKind =
  | 'ok'
  | 'bridge_restarted'
  | 'bridge_restarting'
  | 'plugin_restarting'
  | 'plugin_failed'
  | 'owner_action'
  | 'machine_offline'
  | 'waiting_for_login'

export interface Connection {
  plugin_id: string
  status: 'connected' | 'refused' | 'failed' | 'disabled'
  plugin_name: string | null
  account: string | null
  reason: string | null
  diagnosis: {
    kind: DiagnosisKind
    message: string
    first_failing_layer: string | null
    checked_at: string
  } | null
  repairing: boolean
  last_synced_at: string | null
}

export interface SetupStep {
  title: string
  status: 'done' | 'failing' | 'waiting'
  detail: string | null
}

export interface Checklist {
  plugin_id: string
  steps: SetupStep[]
}
