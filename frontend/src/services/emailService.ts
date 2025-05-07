// src/services/emailService.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE;

// Helper to get current user_id from localStorage or default
function getCurrentUserId(): string {
  if (typeof window === 'undefined') return 'default';
  return localStorage.getItem('current_user_id') || 'default';
}

export async function fetchSpamEmails() {
  try {
    const userId = getCurrentUserId();
    const response = await fetch(`${API_BASE_URL}/api/v1/email/spam?user_id=${userId}`);
    if (!response.ok) {
      console.error("Error fetching spam emails:", response.statusText);
      return [];
    }
    const data = await response.json();

    // Normalize _id to id if necessary
    return Array.isArray(data)
      ? data.map((email) => ({
          id: email.id ?? email._id, // <-- this ensures every email has a usable ID
          sender: email.sender,
          subject: email.subject,
          user_id: email.user_id || userId,
        }))
      : [];
  } catch (error) {
    console.error("Error fetching spam emails:", error);
    return [];
  }
}


export async function markNotSpam(emailId: string) {
  const userId = getCurrentUserId();
  const response = await fetch(`${API_BASE_URL}/api/v1/email/${emailId}/not-spam?user_id=${userId}`, {
    method: 'PATCH',
  })
  if (!response.ok) {
    console.error("Failed to mark email as not spam:", response.statusText)
    throw new Error("Not spam update failed")
  }
}

export async function archiveSpam(emailId: string) {
  const userId = getCurrentUserId();
  const response = await fetch(`${API_BASE_URL}/api/v1/email/${emailId}/archive?user_id=${userId}`, {
    method: 'PATCH',
  })
  if (!response.ok) {
    console.error("Failed to archive spam email:", response.statusText)
    throw new Error("Archive spam failed")
  }
}

// Add a function to create a new email (for testing or direct email creation)
export async function createEmail(email: { subject: string; sender: string; body: string }) {
  const userId = getCurrentUserId();
  const response = await fetch(`${API_BASE_URL}/api/v1/email?user_id=${userId}`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      ...email,
    }),
  });
  
  if (!response.ok) {
    console.error("Failed to create email:", response.statusText);
    throw new Error("Email creation failed");
  }
  
  return await response.json();
}