'use client';

import { useState } from 'react';
import { Button } from './ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from './ui/avatar';
import { useAuthentication, setCurrentUserId, clearCurrentUserId, getDemoUsers } from '@/services/userService';

/**
 * AuthButton - A placeholder component for login/logout functionality
 * 
 * This component will be replaced with Clerk's <UserButton /> and <SignInButton />
 * when Clerk authentication is integrated.
 */
export default function AuthButton() {
  const { isAuthenticated, userId } = useAuthentication();
  const [isOpen, setIsOpen] = useState(false);
  
  // Demo users for development/testing
  const demoUsers = getDemoUsers();
  
  // This will be replaced with Clerk's actual authentication
  const handleSignIn = (selectedUserId: string) => {
    setCurrentUserId(selectedUserId);
    window.location.reload(); // Reload to update state across the app
  };
  
  // This will be replaced with Clerk's sign out
  const handleSignOut = () => {
    clearCurrentUserId();
    window.location.reload(); // Reload to update state across the app
  };
  
  // If not authenticated, show sign-in button
  if (!isAuthenticated) {
    return (
      <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
        <DropdownMenuTrigger asChild>
          <Button variant="outline">Sign In</Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuLabel>Select a demo user</DropdownMenuLabel>
          <DropdownMenuSeparator />
          {demoUsers.filter(user => user !== 'default').map((user) => (
            <DropdownMenuItem key={user} onClick={() => handleSignIn(user)}>
              {user}
            </DropdownMenuItem>
          ))}
          <DropdownMenuSeparator />
          <DropdownMenuLabel className="text-xs text-muted-foreground">
            This will be replaced with Clerk
          </DropdownMenuLabel>
        </DropdownMenuContent>
      </DropdownMenu>
    );
  }
  
  // If authenticated, show user button with sign out option
  return (
    <DropdownMenu open={isOpen} onOpenChange={setIsOpen}>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="relative h-8 w-8 rounded-full">
          <Avatar className="h-8 w-8">
            <AvatarImage src={`https://avatar.vercel.sh/${userId}.png`} alt={userId} />
            <AvatarFallback>{userId.substring(0, 2).toUpperCase()}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{userId}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleSignOut}>
          Sign out
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuLabel className="text-xs text-muted-foreground">
          This will be replaced with Clerk
        </DropdownMenuLabel>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}