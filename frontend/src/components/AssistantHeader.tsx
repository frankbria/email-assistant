// components/AssistantHeader.tsx
import AuthButton from './AuthButton';

export function AssistantHeader() {
  return (
    <header className="flex items-center justify-between px-4 pt-4 pb-2 bg-white dark:bg-gray-800 shadow-sm">
      <h1 className="text-lg text-gray-700 dark:text-gray-200 font-semibold tracking-tight">Email Assistant</h1>
      <AuthButton />
    </header>
  )
}