export function getCategoryIcon(category?: string): string {
  switch ((category || '').toLowerCase()) {
    case 'scheduling':
      return '📅';
    case 'sales':
      return '💼';
    case 'support':
      return '🛠️';
    case 'partner':
      return '🤝';
    case 'personal':
      return '👤';
    case 'internal':
      return '🏢';
    case 'other':
      return '✉️';
    default:
      return '📧';
  }
} 