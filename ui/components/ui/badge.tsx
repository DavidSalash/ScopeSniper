import * as React from "react"
export function Badge({ className = "", variant = "default", children, ...props }: React.HTMLAttributes<HTMLDivElement> & { variant?: string }) {
  return <div className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-hidden ${className}`} {...props}>{children}</div>
}
