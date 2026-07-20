import * as React from "react"
export function Progress({ value = 0, className = "", ...props }: React.HTMLAttributes<HTMLDivElement> & { value?: number }) {
  return (
    <div className={`relative h-2 w-full overflow-hidden rounded-full bg-slate-900 ${className}`} {...props}>
      <div className="h-full w-full flex-1 bg-sky-400 transition-all" style={{ transform: `translateX(-${100 - (value || 0)}%)` }} />
    </div>
  )
}
