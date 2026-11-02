// src/services/emailService.ts

import { apiFetch } from './apiClient';

export async function fetchSpamEmails() {
  try {
    const response = await apiFetch('/api/v1/email/spam');
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
          user_id: email.user_id,
        }))
      : [];
  } catch (error) {
    console.error("Error fetching spam emails:", error);
    return [];
  }
}


export async function markNotSpam(emailId: string) {
  const response = await apiFetch(`/api/v1/email/${emailId}/not-spam`, {
    method: 'PATCH',
  })
  if (!response.ok) {
    console.error("Failed to mark email as not spam:", response.statusText)
    throw new Error("Not spam update failed")
  }
}

export async function archiveSpam(emailId: string) {
  const response = await apiFetch(`/api/v1/email/${emailId}/archive`, {
    method: 'PATCH',
  })
  if (!response.ok) {
    console.error("Failed to archive spam email:", response.statusText)
    throw new Error("Archive spam failed")
  }
}

// Add a function to create a new email (for testing or direct email creation)
export async function createEmail(email: { subject: string; sender: string; body: string }) {
  const response = await apiFetch('/api/v1/email', {
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