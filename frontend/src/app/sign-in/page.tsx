import { OwnerAuthForm } from '@/components/OwnerAuthForm'
import { ownerExists } from '@/lib/auth'

// Reads the database on every request; never prerender.
export const dynamic = 'force-dynamic'

export default async function SignInPage() {
  return <OwnerAuthForm mode={(await ownerExists()) ? 'sign-in' : 'sign-up'} />
}
