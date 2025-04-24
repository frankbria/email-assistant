// components/BottomNav.tsx

import { ClipboardList, Brain, History, Settings } from 'lucide-react'
import { NavItem } from './NavItem'

export function BottomNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-white border-t shadow-sm flex justify-around py-2">
      <NavItem icon={<ClipboardList className="w-6 h-6" />} label="Do" href="/" />
      <NavItem icon={<Brain className="w-6 h-6" />} label="Train" href="/train" />
      <NavItem icon={<History className="w-6 h-6" />} label="History" href="/history" />
      <NavItem icon={<Settings className="w-6 h-6" />} label="Settings" href="/settings" />
    </nav>
  )
}
