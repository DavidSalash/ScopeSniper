import * as React from "react"
interface TabsContextType {
  value: string
  onValueChange: (val: string) => void
}
const TabsContext = React.createContext<TabsContextType>({ value: "", onValueChange: () => {} })

export function Tabs({ value, onValueChange, className = "", children, ...props }: any) {
  return (
    <TabsContext.Provider value={{ value, onValueChange }}>
      <div className={className} {...props}>{children}</div>
    </TabsContext.Provider>
  )
}
export function TabsList({ className = "", children, ...props }: any) {
  return <div className={`inline-flex items-center justify-center rounded-md p-1 ${className}`} {...props}>{children}</div>
}
export function TabsTrigger({ value, className = "", children, ...props }: any) {
  const ctx = React.useContext(TabsContext)
  const active = ctx.value === value
  return (
    <button
      data-state={active ? "active" : "inactive"}
      onClick={() => ctx.onValueChange(value)}
      className={`inline-flex items-center justify-center whitespace-nowrap rounded-xs px-3 py-1.5 text-sm font-medium transition-all ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}
export function TabsContent({ value, className = "", children, ...props }: any) {
  const ctx = React.useContext(TabsContext)
  if (ctx.value !== value) return null
  return <div className={className} {...props}>{children}</div>
}
