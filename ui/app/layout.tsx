import "./globals.css"

export const metadata = {
  title: "Unified Bug Bounty Control Room",
  description: "vLLM Batch Execution Autopilot & Target Profitability Scoring Control Room",
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen p-6">
        <main className="max-w-7xl mx-auto">
          {children}
        </main>
      </body>
    </html>
  )
}
