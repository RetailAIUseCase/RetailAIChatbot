import type { Metadata } from 'next'
import { GeistSans } from 'geist/font/sans'
import { GeistMono } from 'geist/font/mono'
import { Toaster } from "sonner"
import './globals.css'

export const metadata: Metadata = {
  title: 'RAG App',
  description: 'Created with RAG App',
  generator: 'RAG App',
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en">
      <head>
        <style>{`
html {
  font-family: ${GeistSans.style.fontFamily};
  --font-sans: ${GeistSans.variable};
  --font-mono: ${GeistMono.variable};
}
        `}</style>
      </head>
      <body>
        {children}
        <Toaster
          position="top-right"
          richColors={true}
          closeButton={true}
          duration={6000}
          expand={true}
          visibleToasts={5}
          toastOptions={{
            style: {
              background: 'white',
              color: 'black',
              border: '1px solid #e5e7eb',
              fontSize: '14px',
              fontFamily: GeistSans.style.fontFamily,
            },
          }}
        />
      </body>
    </html>
  )
}