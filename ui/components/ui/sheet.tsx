import * as React from "react"
interface SheetProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  children: React.ReactNode
}
const SheetContext = React.createContext<{ open: boolean; onOpenChange: (open: boolean) => void }>({ open: false, onOpenChange: () => {} })

export function Sheet({ open, onOpenChange, children }: SheetProps) {
  return <SheetContext.Provider value={{ open, onOpenChange }}>{children}</SheetContext.Provider>
}
export function SheetContent({ className = "", children }: { className?: string; children: React.ReactNode }) {
  const ctx = React.useContext(SheetContext)
  if (!ctx.open) return null
  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-xs">
      <div className={`relative h-full w-full max-w-lg p-6 shadow-lg transition-transform ${className}`}>
        <button onClick={() => ctx.onOpenChange(false)} className="absolute right-4 top-4 text-slate-400 hover:text-white">✕</button>
        {children}
      </div>
    </div>
  )
}
export function SheetHeader({ className = "", children }: any) {
  return <div className={`flex flex-col space-y-2 text-center sm:text-left ${className}`}>{children}</div>
}
export function SheetTitle({ className = "", children }: any) {
  return <h2 className={`text-lg font-semibold text-foreground ${className}`}>{children}</h2>
}
export function SheetDescription({ className = "", children }: any) {
  return <p className={`text-sm text-muted-foreground ${className}`}>{children}</p>
}
