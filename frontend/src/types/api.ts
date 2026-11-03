export type APIResponse<T> = {
  data: T
  error?: string
}

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
}

export interface JobEdit {
  draft?: string
  forward_to?: string
  options?: string[]
  link?: string
  due?: string
}
