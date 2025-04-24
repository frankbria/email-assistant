// components/NavItem.tsx
'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { ReactNode } from 'react'

interface NavItemProps {
  icon: ReactNode
  label: string
  href: string
}

export function NavItem({ icon, label, href }: NavItemProps) {
  const pathname = usePathname()
  const isActive = pathname === href

  return (
    <Link
      href={href}
      className={`flex flex-col items-center text-xs rounded-lg p-2 transition duration-200
        ${isActive ? 'text-blue-600 font-semibold' : 'text-gray-600 hover:bg-gray-300'}`}
    >
      {icon}
      <span className="mt-1">{label}</span>
    </Link>
  )
}