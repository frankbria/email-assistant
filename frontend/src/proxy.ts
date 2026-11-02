import { NextResponse, type NextRequest } from 'next/server'
import { auth } from '@/lib/auth'

// Every page needs the owner's session; sign-in and the auth API stay public.
export async function proxy(request: NextRequest) {
  const session = await auth.api.getSession({ headers: request.headers })
  if (session) return NextResponse.next()
  return NextResponse.redirect(new URL('/sign-in', request.url))
}

export const config = {
  matcher: ['/((?!api/auth|sign-in|_next/static|_next/image|favicon.ico).*)'],
}
