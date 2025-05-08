// frontend/src/services/userService.ts

/**
 * User Service - Handles user identification and authentication
 * 
 * This service abstracts the logic for retrieving the current user ID from various sources:
 * 1. Clerk authentication (when implemented)
 * 2. URL query parameters (for demo/testing)
 * 3. localStorage (for demo/persistent user selection)
 * 
 * It provides a consistent interface for the rest of the application to get
 * the current user ID without needing to know the source.
 */

// When Clerk is integrated, uncomment these imports
// import { useAuth, useUser } from '@clerk/nextjs';
// import { auth } from '@clerk/nextjs/server';

// Constants
const DEFAULT_USER_ID = 'default';
const USER_ID_STORAGE_KEY = 'current_user_id';

// Flag to determine if we're in development mode
const IS_DEV_MODE = process.env.NODE_ENV === 'development';

/**
 * Get the current user ID from available sources, with priority:
 * 1. Clerk authentication (when implemented)
 * 2. URL query parameters (only in dev mode)
 * 3. localStorage (only in dev mode)
 * 4. Default value
 * 
 * @returns The current user ID string
 */
export function getCurrentUserId(): string {
  // Handle server-side rendering
  if (typeof window === 'undefined') {
    // In the future with Clerk SSR:
    // const { userId } = auth();
    // return userId || DEFAULT_USER_ID;
    return DEFAULT_USER_ID;
  }

  // PRIORITY 1: Clerk Authentication (when implemented)
  // Uncomment when Clerk is integrated
  // const { user } = useUser();
  // if (user) {
  //   return user.id;
  // }

  // The following options are only available in development mode
  if (IS_DEV_MODE) {
    // PRIORITY 2: Check URL query parameters (useful for testing and demo)
    const params = new URLSearchParams(window.location.search);
    const queryParamUserId = params.get('user_id');
    if (queryParamUserId) {
      // Save to localStorage for persistence across pages
      localStorage.setItem(USER_ID_STORAGE_KEY, queryParamUserId);
      return queryParamUserId;
    }

    // PRIORITY 3: Check localStorage
    const storedUserId = localStorage.getItem(USER_ID_STORAGE_KEY);
    if (storedUserId) {
      return storedUserId;
    }
  }

  // Fallback to default
  return DEFAULT_USER_ID;
}

/**
 * Set the current user ID in localStorage (dev mode only)
 * 
 * @param userId The user ID to set
 */
export function setCurrentUserId(userId: string): void {
  if (typeof window === 'undefined' || !IS_DEV_MODE) return;
  localStorage.setItem(USER_ID_STORAGE_KEY, userId);
}

/**
 * Clear the current user ID from localStorage
 */
export function clearCurrentUserId(): void {
  if (typeof window === 'undefined' || !IS_DEV_MODE) return;
  localStorage.removeItem(USER_ID_STORAGE_KEY);
}

/**
 * Check if the current user is authenticated
 * 
 * @returns boolean indicating if user is authenticated
 */
export function isAuthenticated(): boolean {
  // When Clerk is integrated, this will use Clerk's authentication check
  // const { isSignedIn } = useAuth();
  // return isSignedIn;

  // For now in development mode, we consider non-default users as "authenticated"
  return IS_DEV_MODE ? getCurrentUserId() !== DEFAULT_USER_ID : false;
}

/**
 * Get the current user's profile information
 * 
 * @returns User profile object or null if not authenticated
 */
export function getCurrentUserProfile(): { id: string; email?: string; name?: string } | null {
  // When Clerk is integrated, this will return the user's profile
  // const { user } = useUser();
  // if (!user) return null;
  // return {
  //   id: user.id,
  //   email: user.primaryEmailAddress?.emailAddress,
  //   name: user.fullName || user.firstName,
  // };
  
  // For development mode only
  if (IS_DEV_MODE) {
    const userId = getCurrentUserId();
    if (userId === DEFAULT_USER_ID) return null;
    
    // Mock user profile for development
    return {
      id: userId,
      email: `${userId}@example.com`,
      name: userId.charAt(0).toUpperCase() + userId.slice(1),
    };
  }
  
  return null;
}

/**
 * Get all available demo users (dev mode only)
 * 
 * @returns Array of demo user IDs
 */
export function getDemoUsers(): string[] {
  return IS_DEV_MODE ? ['default', 'demo1', 'demo2'] : [];
}

/**
 * Client-side authentication check wrapper for components
 * Can be used in components that need to respond to auth state
 */
export function useAuthentication() {
  // When Clerk is integrated:
  // const { isSignedIn, isLoaded } = useAuth();
  // return { 
  //   isAuthenticated: isSignedIn,
  //   isLoading: !isLoaded,
  //   userId: getCurrentUserId()
  // };
  
  return {
    isAuthenticated: isAuthenticated(),
    isLoading: false,
    userId: getCurrentUserId()
  };
}