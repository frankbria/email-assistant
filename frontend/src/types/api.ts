export type APIResponse<T> = {
  data: T
  error?: string
}

// Helper type for MongoDB _id handling
export interface MongoDocument {
  _id?: string
  id?: string
}

export type AIProviderName = 'anthropic' // matches the backend's AIProviderName
export type PrivacyMode = 'full_cloud' | 'redacted_cloud' // matches the backend's PrivacyMode

// The settings screen's choices; until the owner saves, each is the server's env default.
export interface AssistantSettings {
  ai_provider: AIProviderName
  ai_model: string
  poll_seconds: number
  first_connect_days: number
  privacy_mode: PrivacyMode
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
  title: string
  steps: SetupStep[]
  warnings: string[]
}

export type PermissionLevel = 'autonomous' | 'ask' | 'never_auto'

export interface VerbPermission {
  verb: string
  level: PermissionLevel
  default: PermissionLevel
  ceiling: PermissionLevel
  reason: string
}

export interface Permissions {
  verbs: VerbPermission[]
  file_error: string | null
  promotions: string[]
}

export type Verb =
  | 'reply'
  | 'forward'
  | 'digest'
  | 'snooze'
  | 'follow_up'
  | 'todo'
  | 'archive_noise'
  | 'unsubscribe'

export type JobState =
  | 'open'
  | 'sending'
  | 'snoozed'
  | 'done'
  | 'dismissed'
  | 'failed'
  | 'handled_elsewhere'

export interface JobArtifacts {
  draft: string | null
  forward_to: string | null
  options: string[]
  link: string | null
  digest: string | null
  noise_rationale: string | null
}

export interface Job {
  _id: string
  owner_id: string
  verb: Verb
  title: string
  evidence: string[]
  artifacts: JobArtifacts
  due: string | null
  state: JobState
  message_ids: string[]
  permission_level: PermissionLevel | null
  ask_owner: boolean
  suggested_verbs: Verb[]
  problems: string[]
  requires_approval: boolean
  edited: boolean
  error: string | null
  sending_since: string | null
  sent_at: string | null
  reminder: string | null
  created_at: string
}

export interface JobCard {
  job: Job
  sender: { name: string | null; email: string }
  subject: string
  list_id: string | null // the raw List-Id header
}

export interface JobEdit {
  draft?: string
  forward_to?: string
  options?: string[]
  link?: string
  due?: string | null
}

export type HistoryAction = 'sent' | 'archived' | 'done' | 'snoozed' | 'dismissed' | 'restored'

export interface ActionLogEntry {
  _id: string
  owner_id: string
  action: HistoryAction
  job_id: string
  message_ids: string[]
  by: 'app' | 'owner'
  permission_level: PermissionLevel | null
  ok: boolean
  error: string | null
  undoable: boolean
  undone: boolean
  created_at: string
}

export interface HistoryCard {
  entry: ActionLogEntry
  sender: { name: string | null; email: string }
  subject: string
}

export interface FilteredCard extends HistoryCard {
  rationale: string | null
  restorable: boolean
}
