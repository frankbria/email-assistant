// src/services/emailService.ts

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE;

export async function fetchSpamEmails() {
  try {
    const response = await fetch(`${API_BASE_URL}/api/v1/email/spam`);
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
        }))
      : [];
  } catch (error) {
    console.error("Error fetching spam emails:", error);
    return [];
  }
}


export async function markNotSpam(emailId: string) {
  const response = await fetch(`${API_BASE_URL}/api/v1/email/${emailId}/not-spam`, {
    method: 'PATCH',
  })
  if (!response.ok) {
    console.error("Failed to mark email as not spam:", response.statusText)
    throw new Error("Not spam update failed")
  }
}

export async function archiveSpam(emailId: string) {
  const response = await fetch(`${API_BASE_URL}/api/v1/email/${emailId}/archive`, {
    method: 'PATCH',
  })
  if (!response.ok) {
    console.error("Failed to archive spam email:", response.statusText)
    throw new Error("Archive spam failed")
  }
}