import * as React from "react"

interface TabsContextType {
  value: string
  onValueChange: (val: string) => void
}

const TabsContext = React.createContext<TabsContextType>({ value: "", onValueChange: () => {} })

export function Tabs({ defaultValue, value: controlledValue, onValueChange, className = "", children, ...props }: any) {
  const [uncontrolledValue, setUncontrolledValue] = React.useState(defaultValue || "")
  
  const isControlled = controlledValue !== undefined
  const currentValue = isControlled ? controlledValue : uncontrolledValue

  const handleValueChange = React.useCallback((val: string) => {
    if (!isControlled) {
      setUncontrolledValue(val)
    }
    if (onValueChange) {
      onValueChange(val)
    }
  }, [isControlled, onValueChange])

  return (
    <TabsContext.Provider value={{ value: currentValue, onValueChange: handleValueChange }}>
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
      type="button"
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
