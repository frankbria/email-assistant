'use client';

import { Button } from './ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { Avatar, AvatarFallback } from './ui/avatar';
import { authClient } from '@/lib/auth-client';

export default function AuthButton() {
  const { data: session } = authClient.useSession();
  if (!session) return null;

  async function handleSignOut() {
    await authClient.signOut();
    // Full page load drops all client state from the signed-out session.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination -- deliberate full reload
    window.location.assign('/sign-in');
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" className="relative h-8 w-8 rounded-full" aria-label="Account menu">
          <Avatar className="h-8 w-8">
            <AvatarFallback>{session.user.name.substring(0, 2).toUpperCase()}</AvatarFallback>
          </Avatar>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>{session.user.email}</DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem onClick={handleSignOut}>Sign out</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
