// app/layout.tsx

import './globals.css'
import 'react-toastify/dist/ReactToastify.css'
import { ToastContainer } from 'react-toastify'
import { BottomNav } from '@/components/BottomNav'
import { AssistantHeader } from '@/components/AssistantHeader'
import { Container } from '@/components/Container'

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body className="flex flex-col min-h-screen bg-muted text-foreground">
        <div className="flex-1 flex flex-col overflow-y-auto">
          <AssistantHeader />
          <main className="flex-1 p-4 space-y-4 bg-gray-100">
            <Container>
              {children}
            </Container>
          </main>
        </div>
        <BottomNav />
        <ToastContainer
          position="top-right"
          autoClose={5000}
          hideProgressBar={false}
          newestOnTop
          closeOnClick
          rtl={false}
          pauseOnFocusLoss
          draggable
          pauseOnHover
          theme="light"
        />
      </body>
    </html>
  )
}
