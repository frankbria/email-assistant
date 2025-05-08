import { AssistantTask } from '@/types/api'

export const mockTasks: AssistantTask[] = [
  {
    id: '1',
    email: {
      id: '1',
      subject: 'Project Update',
      sender: 'teammate@company.com',
      body: 'Here is the latest project update.',
      user_id: 'default',
      is_spam: false
    },
    context: 'Project Update',
    summary: 'Here is the latest project update.',
    actions: ['Reply', 'Forward', 'Archive'],
    status: 'pending',
    user_id: 'default',
    action_taken: null
  },
  {
    id: '2', 
    email: {
      id: '2',
      subject: 'Client Meeting',
      sender: 'client@example.com',
      body: 'Can we schedule a meeting to discuss the proposal?',
      user_id: 'default',
      is_spam: false
    },
    context: 'Client Meeting',
    summary: 'Can we schedule a meeting to discuss the proposal?',
    actions: ['Schedule', 'Reply', 'Hold for Later'],
    status: 'pending',
    user_id: 'default',
    action_taken: null
  }
]