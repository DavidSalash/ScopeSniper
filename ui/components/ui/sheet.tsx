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
    <div 
      className="fixed inset-0 z-50 flex justify-end bg-black/80 backdrop-blur-xs animate-in fade-in-0 duration-200"
      onClick={() => ctx.onOpenChange(false)}
    >
      <div 
        className={`relative h-full w-full p-6 shadow-2xl transition-transform ${className}`}
        onClick={(e) => e.stopPropagation()}
      >
        <button 
          type="button"
          onClick={() => ctx.onOpenChange(false)} 
          className="absolute right-4 top-4 text-slate-400 hover:text-white z-10 p-1"
        >
          ✕
        </button>
        {children}
      </div>
    </div>
  )
}

export function SheetHeader({ className = "", children }: any) {
  return <div className={`flex flex-col space-y-2 text-center sm:text-left ${className}`}>{children}</div>
}

export function SheetTitle({ className = "", children }: any) {
  return <h2 className={`text-lg font-semibold text-white ${className}`}>{children}</h2>
}

export function SheetDescription({ className = "", children }: any) {
  return <p className={`text-sm text-slate-400 ${className}`}>{children}</p>
}
