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
    <nav
      className="fixed bottom-0 left-0 right-0 bg-white dark:bg-gray-800 border-t shadow-lg z-50 rounded-t-2xl md:rounded-none"
      role="navigation"
      aria-label="Main navigation"
    >
      <div className="flex flex-row justify-around items-center py-2 px-1 md:px-0">
        <NavItem
          href="/"
          active={pathname === '/'}
          icon={<ClipboardList className="w-7 h-7 md:w-6 md:h-6" />}
          label="Do"
        />
        <NavItem
          href="/train"
          active={pathname.startsWith('/train')}
          icon={<Brain className="w-7 h-7 md:w-6 md:h-6" />}
          label="Train"
        />
        <NavItem
          href="/history"
          active={pathname.startsWith('/history')}
          icon={<History className="w-7 h-7 md:w-6 md:h-6" />}
          label="History"
        />
        <NavItem
          href="/settings"
          active={pathname.startsWith('/settings')}
          icon={<Settings className="w-7 h-7 md:w-6 md:h-6" />}
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
      aria-current={active ? 'page' : undefined}
      className={`
        flex flex-col items-center justify-center text-xs font-medium rounded-lg transition-colors duration-200
        min-w-[44px] min-h-[44px] px-2 py-1
        focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2
        ${active
          ? "text-blue-700 bg-blue-100 dark:text-blue-300 dark:bg-blue-900 font-semibold"
          : "text-gray-700 dark:text-gray-400 hover:bg-gray-300 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white"
        }
      `}
      tabIndex={0}
      role="link"
    >
      {icon}
      <span className="mt-1 text-sm md:text-xs leading-tight">{label}</span>
    </Link>
  )
}
