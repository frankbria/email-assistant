// frontend/src/components/BottomNav.tsx
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  ClipboardList,
  Brain,
  History,
  Settings,
} from 'lucide-react'

export function BottomNav() {
  const pathname = usePathname()

  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-800 border-t shadow-sm z-50">
      <div className="flex flex-row justify-around items-center py-2">
        <NavItem
          href="/"
          active={pathname === '/'}
          icon={<ClipboardList className="w-6 h-6" />}
          label="Do"
        />
        <NavItem
          href="/train"
          active={pathname.startsWith('/train')}
          icon={<Brain className="w-6 h-6" />}
          label="Train"
        />
        <NavItem
          href="/history"
          active={pathname.startsWith('/history')}
          icon={<History className="w-6 h-6" />}
          label="History"
        />
        <NavItem
          href="/settings"
          active={pathname.startsWith('/settings')}
          icon={<Settings className="w-6 h-6" />}
          label="Settings"
        />
      </div>
    </nav>
  )
}

function NavItem({
  href,
  active,
  icon,
  label,
}: {
  href: string
  active: boolean
  icon: React.ReactNode
  label: string
}) {
  return (
    <Link
      href={href}
      className={`
        flex flex-col items-center text-xs rounded-lg p-2 transition-colors duration-200
        ${active
          ? "text-blue-700 bg-blue-100 dark:text-blue-300 dark:bg-blue-900 font-semibold"
          : "text-gray-700 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white"
        }
      `}
    >
      {icon}
      <span className="mt-1">{label}</span>
    </Link>
  )
}
