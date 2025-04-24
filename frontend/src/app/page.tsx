// app/page.tsx
import Link from 'next/link'

export default function Page() {
  return (
     <div className="text-center text-gray-500 pt-10 space-y-4">
      <p>Select a mode from the nav to get started.</p>
      <Link href="/demo" className="text-blue-600 underline">
        Go to demo page →
      </Link>
    </div>
  )
}