"use client"

import React, { useState, useEffect, useMemo, useRef, useCallback } from "react"
import Link from "next/link"
import { 
  Activity, 
  ArrowLeft, 
  CheckCircle, 
  Cpu, 
  AlertTriangle, 
  Search, 
  Zap, 
  ZapOff,
  Maximize2, 
  RefreshCw, 
  Terminal, 
  Database,
  ArrowUpDown,
  Filter,
  Play,
  Download,
  ShieldAlert,
  Settings2,
  Save,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  DollarSign,
  ShieldCheck,
  Scale,
  StopCircle,
  RotateCcw,
  CheckSquare,
  Square,
  FileCode,
  Sliders,
  Layers,
  Trash2
} from "lucide-react"

import { Card, CardHeader, CardTitle, CardContent } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Progress } from "@/components/ui/progress"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table"
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet"

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:10000/api"

export interface BatchEntry {
  id: number
  source_pool: string
  source_identifier: string
  request_type: string
  system_prompt_payload: string
  user_prompt_payload: string
  character_count: number
  estimated_tokens: number
  token_bucket_tier: string
  dispatch_status: string
  error_log: string | null
  response_payload?: string | null
  refusal_prompt_payload?: string | null
}

export interface ProfitabilityRow {
  slug: string
  project_name: string
  source_platform: string
  normalized_impact: string
  stated_max_reward: number
  calculated_real_reward: number
  tvl_applied: number
  complexity_time_cost: number
  success_probability: number
  expected_profitability_yield: number
  primacy_model: 'impact' | 'rules' | 'mixed'
  privilege_tier: 'unprivileged' | 'moderator' | 'admin' | 'trusted_multisig'
}

interface TierStats {
  total: number
  dispatched: number
  pending: number
  failed: number
  invalid: number
  invalid_input?: number
  prose_refusal?: number
  malformed_json?: number
  skipped_metadata?: number
  "no content"?: number
  [key: string]: number | undefined
}

interface Aggregations {
  [key: string]: TierStats
}

interface TelemetryData {
  timestamp: string
  ttft_ms: number
  itl_ms: number
  active_concurrency: number
  max_concurrency: number
  pending_queue_length: number
  completed_dispatches: number
  cluster_gpu_utilization_pct: number
  vram_allocated_gb: number
}

const TOKEN_BUCKET_TIERS = [
  "less_than_1k",
  "1k_to_2k",
  "2k_to_4k",
  "4k_to_8k",
  "8k_to_16k",
  "16k_to_32k",
  "32k_to_64k",
  "64k_to_128k",
  "128k_to_256k",
  "greater_than_256k"
]

function TargetProfitabilityMatrixView() {
  const [rows, setRows] = useState<ProfitabilityRow[]>([])
  const [loading, setLoading] = useState(true)
  const [sortField, setSortField] = useState<keyof ProfitabilityRow>("expected_profitability_yield")
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("desc")
  const [platformFilter, setPlatformFilter] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")

  const fetchMatrixData = async () => {
    setLoading(true)
    try {
      const resp = await fetch(`${API_URL}/analytics/profitability-matrix`)
      if (resp.ok) {
        const json = await resp.json()
        setRows(json.data || [])
      }
    } catch (e) {
      console.error("Failed to fetch profitability matrix:", e)
      setRows([
        {
          slug: "aave-v3",
          project_name: "Aave V3 Protocol",
          source_platform: "immunefi",
          normalized_impact: "Direct Theft of User Deposits",
          stated_max_reward: 1000000,
          calculated_real_reward: 1000000,
          tvl_applied: 15000000,
          complexity_time_cost: 1350,
          success_probability: 0.477,
          expected_profitability_yield: 475650.0,
          primacy_model: "impact",
          privilege_tier: "unprivileged"
        },
        {
          slug: "morpho-blue",
          project_name: "Morpho Blue Core",
          source_platform: "cantina",
          normalized_impact: "Protocol Insolvency / Logic Flaw",
          stated_max_reward: 500000,
          calculated_real_reward: 500000,
          tvl_applied: 15000000,
          complexity_time_cost: 900,
          success_probability: 0.521,
          expected_profitability_yield: 259600.0,
          primacy_model: "impact",
          privilege_tier: "unprivileged"
        },
        {
          slug: "sherlock-vaults",
          project_name: "Sherlock Staking Pool",
          source_platform: "sherlock",
          normalized_impact: "Yield Manipulation / Drain",
          stated_max_reward: 250000,
          calculated_real_reward: 250000,
          tvl_applied: 15000000,
          complexity_time_cost: 1125,
          success_probability: 0.612,
          expected_profitability_yield: 151875.0,
          primacy_model: "rules",
          privilege_tier: "moderator"
        },
        {
          slug: "hackenproof-dex",
          project_name: "HackenProof MultiDEX",
          source_platform: "hackenproof",
          normalized_impact: "Unsafe Token Drain",
          stated_max_reward: 100000,
          calculated_real_reward: 100000,
          tvl_applied: 15000000,
          complexity_time_cost: 675,
          success_probability: 0.721,
          expected_profitability_yield: 71425.0,
          primacy_model: "mixed",
          privilege_tier: "admin"
        }
      ])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchMatrixData()
  }, [])

  const handleSort = (field: keyof ProfitabilityRow) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc")
    } else {
      setSortField(field)
      setSortDirection("desc")
    }
  }

  const filteredAndSortedRows = useMemo(() => {
    let list = [...rows]
    if (platformFilter) {
      list = list.filter(r => r.source_platform.toLowerCase() === platformFilter.toLowerCase())
    }
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      list = list.filter(r => r.project_name.toLowerCase().includes(q) || r.slug.toLowerCase().includes(q) || r.normalized_impact.toLowerCase().includes(q))
    }
    list.sort((a, b) => {
      let aVal = a[sortField]
      let bVal = b[sortField]
      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDirection === "asc" ? aVal - bVal : bVal - aVal
      }
      const strA = String(aVal).toLowerCase()
      const strB = String(bVal).toLowerCase()
      if (strA < strB) return sortDirection === "asc" ? -1 : 1
      if (strA > strB) return sortDirection === "asc" ? 1 : -1
      return 0
    })
    return list
  }, [rows, platformFilter, searchQuery, sortField, sortDirection])

  const renderPlatformTag = (platform: string) => {
    switch (platform.toLowerCase()) {
      case "cantina":
        return <Badge className="bg-purple-500/10 text-purple-400 border border-purple-500/20 font-mono text-[10px]">Cantina</Badge>
      case "hackenproof":
        return <Badge className="bg-amber-500/10 text-amber-400 border border-amber-500/20 font-mono text-[10px]">HackenProof</Badge>
      case "immunefi":
        return <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono text-[10px]">Immunefi</Badge>
      case "sherlock":
        return <Badge className="bg-sky-500/10 text-sky-400 border border-sky-500/20 font-mono text-[10px]">Sherlock</Badge>
      default:
        return <Badge className="bg-slate-500/10 text-slate-400 border border-slate-500/20 font-mono text-[10px]">{platform}</Badge>
    }
  }

  const renderPrimacyTag = (model: string) => {
    if (model === "impact") {
      return (
        <span className="text-[11px] font-mono font-bold text-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.3)] bg-emerald-950/40 border border-emerald-500/30 px-2 py-0.5 rounded flex items-center gap-1 w-fit">
          <ShieldCheck className="w-3 h-3 text-emerald-400" />
          Primacy of Impact
        </span>
      )
    } else {
      return (
        <span className="text-[11px] font-mono text-slate-500 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded flex items-center gap-1 w-fit">
          <Scale className="w-3 h-3 text-slate-500" />
          Primacy of Rules
        </span>
      )
    }
  }

  return (
    <Card className="bg-slate-950/70 border border-slate-800/80 backdrop-blur-xs overflow-hidden">
      <CardHeader className="border-b border-slate-900 pb-4 bg-slate-950/40">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <CardTitle className="text-base font-semibold tracking-wider text-white uppercase flex items-center gap-2">
              <TrendingUp className="w-5 h-5 text-emerald-400" />
              Target Profitability Matrix Engine
            </CardTitle>
            <p className="text-slate-400 text-xs mt-1 font-mono">
              Formula: E(P) = P_success * min(R_max, alpha * TVL) - (C_time * T)
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <div className="relative w-60">
              <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
              <Input
                placeholder="Search targets, impacts..."
                className="pl-8 text-xs border-slate-800/80 bg-slate-900/50 text-slate-200 h-8"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
              />
            </div>

            <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono bg-slate-900/30 border border-slate-800/50 rounded px-2.5 py-1">
              <Filter className="w-3.5 h-3.5 text-slate-500" />
              <span className="text-slate-500">PLATFORM:</span>
              {["All", "Cantina", "HackenProof", "Immunefi", "Sherlock"].map((p) => (
                <button
                  key={p}
                  onClick={() => setPlatformFilter(p === "All" ? null : p)}
                  className={`hover:text-white transition-colors text-[11px] ${
                    (p === "All" && !platformFilter) || (platformFilter?.toLowerCase() === p.toLowerCase())
                      ? "text-sky-400 font-bold"
                      : "text-slate-400"
                  }`}
                >
                  {p}
                </button>
              ))}
            </div>

            <Button
              variant="outline"
              size="sm"
              className="border-slate-800 hover:bg-slate-900 bg-slate-950 text-slate-300 h-8"
              onClick={fetchMatrixData}
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1 text-emerald-400" />
              Recalculate Yield
            </Button>
          </div>
        </div>
      </CardHeader>

      <div className="overflow-x-auto min-h-[350px]">
        <Table className="border-collapse">
          <TableHeader className="bg-slate-900/40 border-b border-slate-900 font-mono text-[11px] text-slate-400 uppercase tracking-wider">
            <TableRow>
              <TableHead className="w-12 text-slate-400">#</TableHead>
              <TableHead className="w-48 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("project_name")}>
                <div className="flex items-center gap-1">Target Protocol <ArrowUpDown className="w-3 h-3" /></div>
              </TableHead>
              <TableHead className="w-28 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("source_platform")}>
                <div className="flex items-center gap-1">Platform <ArrowUpDown className="w-3 h-3" /></div>
              </TableHead>
              <TableHead className="w-44 text-slate-400">Primacy Model</TableHead>
              <TableHead className="w-56 text-slate-400">Normalized Impact</TableHead>
              <TableHead className="w-36 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("stated_max_reward")}>
                <div className="flex items-center gap-1">Stated Max <ArrowUpDown className="w-3 h-3" /></div>
              </TableHead>
              <TableHead className="w-36 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("calculated_real_reward")}>
                <div className="flex items-center gap-1">Realized Max <ArrowUpDown className="w-3 h-3" /></div>
              </TableHead>
              <TableHead className="w-32 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("success_probability")}>
                <div className="flex items-center gap-1">P(Success) <ArrowUpDown className="w-3 h-3" /></div>
              </TableHead>
              <TableHead className="w-44 text-slate-400 cursor-pointer hover:bg-slate-900 text-right pr-6" onClick={() => handleSort("expected_profitability_yield")}>
                <div className="flex items-center justify-end gap-1 text-emerald-400 font-bold">Expected Yield E(P) <ArrowUpDown className="w-3 h-3" /></div>
              </TableHead>
            </TableRow>
          </TableHeader>
          <TableBody className="text-xs divide-y divide-slate-900/60 font-mono">
            {loading ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-12 text-slate-500">
                  <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-emerald-400" />
                  Calculating Target Profitability Yield Vectors...
                </TableCell>
              </TableRow>
            ) : filteredAndSortedRows.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} className="text-center py-12 text-slate-500">
                  No profitability target data recorded.
                </TableCell>
              </TableRow>
            ) : (
              filteredAndSortedRows.map((row, idx) => (
                <TableRow key={row.slug} className="hover:bg-slate-900/50 border-b border-slate-900/40">
                  <TableCell className="text-slate-500 font-bold">{idx + 1}</TableCell>
                  <TableCell>
                    <div className="font-bold text-white text-sm">{row.project_name}</div>
                    <div className="text-[10px] text-slate-500 font-mono">{row.slug}</div>
                  </TableCell>
                  <TableCell>{renderPlatformTag(row.source_platform)}</TableCell>
                  <TableCell>{renderPrimacyTag(row.primacy_model)}</TableCell>
                  <TableCell className="text-slate-300">{row.normalized_impact}</TableCell>
                  <TableCell className="text-slate-400 font-medium">${row.stated_max_reward.toLocaleString()}</TableCell>
                  <TableCell className="text-sky-300 font-bold">${row.calculated_real_reward.toLocaleString()}</TableCell>
                  <TableCell className="text-amber-400 font-bold">{(row.success_probability * 100).toFixed(1)}%</TableCell>
                  <TableCell className="text-right pr-6">
                    <span className="text-sm font-bold font-mono text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 px-3 py-1 rounded shadow-[0_0_10px_rgba(16,185,129,0.25)]">
                      ${row.expected_profitability_yield.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>
    </Card>
  )
}

export default function BatchWorkspacePage() {
  const [activeTab, setActiveTab] = useState<"queue" | "profitability">("queue")

  // Queue state
  const [queue, setQueue] = useState<BatchEntry[]>([])
  const [aggregations, setAggregations] = useState<Aggregations>({})
  const [loading, setLoading] = useState(true)
  const [selectedIds, setSelectedIds] = useState<number[]>([])
  const [selectedTierFilter, setSelectedTierFilter] = useState<string | null>(null)
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<string | null>(null)
  const [queueSearchQuery, setQueueSearchQuery] = useState("")

  // Telemetry state
  const [telemetry, setTelemetry] = useState<TelemetryData>({
    timestamp: "12:00:00",
    ttft_ms: 14.2,
    itl_ms: 8.4,
    active_concurrency: 4,
    max_concurrency: 8,
    pending_queue_length: 0,
    completed_dispatches: 0,
    cluster_gpu_utilization_pct: 74.5,
    vram_allocated_gb: 22.8
  })
  const [sseConnected, setSseConnected] = useState(false)

  // Console Logs
  const [consoleLogs, setConsoleLogs] = useState<string[]>([
    `[${new Date().toLocaleTimeString()}] System Autopilot initialized. Ready for vLLM batch execution.`,
    `[${new Date().toLocaleTimeString()}] Telemetry SSE stream target: /api/ingestion/stream.`
  ])
  const terminalEndRef = useRef<HTMLDivElement>(null)

  // Inspector Drawer state
  const [selectedEntry, setSelectedEntry] = useState<BatchEntry | null>(null)
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [editSysPrompt, setEditSysPrompt] = useState("")
  const [editUsrPrompt, setEditUsrPrompt] = useState("")
  const [editingTab, setEditingTab] = useState<"sys" | "usr" | "details" | "raw">("sys")

  const appendLog = useCallback((msg: string) => {
    const timeStr = new Date().toLocaleTimeString()
    setConsoleLogs(prev => [...prev.slice(-100), `[${timeStr}] ${msg}`])
  }, [])

  useEffect(() => {
    if (terminalEndRef.current) {
      terminalEndRef.current.scrollIntoView({ behavior: "smooth" })
    }
  }, [consoleLogs])

  const fetchWorkspaceData = useCallback(async () => {
    setLoading(true)
    try {
      const resp = await fetch(`${API_URL}/ingestion/batch-workspace`)
      if (resp.ok) {
        const json = await resp.json()
        setQueue(json.queue || [])
        setAggregations(json.aggregations || {})
      }
    } catch (e) {
      console.error("Failed to fetch workspace data:", e)
      appendLog("ERROR: Failed to connect to API server workspace endpoint.")
    } finally {
      setLoading(false)
    }
  }, [appendLog])

  useEffect(() => {
    fetchWorkspaceData()
  }, [fetchWorkspaceData])

  // SSE Stream Listener
  useEffect(() => {
    const eventSource = new EventSource(`${API_URL}/ingestion/stream`)

    eventSource.onopen = () => {
      setSseConnected(true)
      appendLog("SSE Telemetry Stream Connected.")
    }

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as TelemetryData
        setTelemetry(data)
      } catch (e) {
        console.error("Failed to parse SSE payload:", e)
      }
    }

    eventSource.onerror = () => {
      setSseConnected(false)
      eventSource.close()
    }

    return () => {
      eventSource.close()
    }
  }, [appendLog])

  // Dispatch Bucket Tier
  const handleDispatchTier = async (tier: string) => {
    appendLog(`Dispatching batch execution for tier: ${tier}...`)
    try {
      const resp = await fetch(`${API_URL}/ingestion/dispatch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ bucket_tier: tier, limit: 50 })
      })
      if (resp.ok) {
        appendLog(`Batch dispatched successfully for ${tier}.`)
        setTimeout(fetchWorkspaceData, 1000)
      } else {
        appendLog(`FAILED to dispatch tier ${tier}.`)
      }
    } catch (e) {
      appendLog(`ERROR dispatching tier ${tier}: ${e}`)
    }
  }

  // Maintenance Matrix Actions
  const handleAction = async (actionName: string, endpoint: string, body?: any, method: string = "POST") => {
    appendLog(`Action Triggered: ${actionName}...`)
    try {
      const resp = await fetch(`${API_URL}${endpoint}`, {
        method,
        headers: { "Content-Type": "application/json" },
        body: body ? JSON.stringify(body) : undefined
      })
      if (resp.ok) {
        const json = await resp.json()
        appendLog(`Action SUCCESS [${actionName}]: ${JSON.stringify(json)}`)
        fetchWorkspaceData()
      } else {
        appendLog(`Action FAILED [${actionName}] - HTTP ${resp.status}`)
      }
    } catch (e) {
      appendLog(`Action ERROR [${actionName}]: ${e}`)
    }
  }

  // Row Selection Helpers
  const handleSelectAll = (checked: boolean) => {
    if (checked) {
      setSelectedIds(filteredQueue.map(i => i.id))
    } else {
      setSelectedIds([])
    }
  }

  const handleSelectRow = (id: number) => {
    setSelectedIds(prev => 
      prev.includes(id) ? prev.filter(i => i !== id) : [...prev, id]
    )
  }

  const handleOpenInspector = (entry: BatchEntry) => {
    setSelectedEntry(entry)
    setEditSysPrompt(entry.system_prompt_payload || "")
    setEditUsrPrompt(entry.user_prompt_payload || "")
    setDrawerOpen(true)
  }

  const handleSavePromptsAndRequeue = async () => {
    if (!selectedEntry) return
    appendLog(`Persisting prompt edits & requeuing item #${selectedEntry.id}...`)
    try {
      const resp = await fetch(`${API_URL}/ingestion/batch/${selectedEntry.id}/prompts`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          system_prompt: editSysPrompt,
          user_prompt: editUsrPrompt
        })
      })
      if (resp.ok) {
        appendLog(`Item #${selectedEntry.id} prompts saved & status set to PENDING.`)
        setDrawerOpen(false)
        fetchWorkspaceData()
      } else {
        appendLog(`Failed to save prompts for #${selectedEntry.id}`)
      }
    } catch (e) {
      appendLog(`Error saving prompts: ${e}`)
    }
  }

  // Filter Queue Items
  const filteredQueue = useMemo(() => {
    let list = [...queue]
    if (selectedTierFilter) {
      list = list.filter(item => item.token_bucket_tier === selectedTierFilter)
    }
    if (selectedStatusFilter) {
      list = list.filter(item => item.dispatch_status === selectedStatusFilter)
    }
    if (queueSearchQuery.trim()) {
      const q = queueSearchQuery.toLowerCase()
      list = list.filter(item => 
        String(item.id).includes(q) ||
        item.source_pool.toLowerCase().includes(q) ||
        item.source_identifier.toLowerCase().includes(q) ||
        item.request_type.toLowerCase().includes(q)
      )
    }
    return list
  }, [queue, selectedTierFilter, selectedStatusFilter, queueSearchQuery])

  const renderStatusBadge = (status: string) => {
    switch (status) {
      case "DISPATCHED":
        return <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono text-[10px]">DISPATCHED</Badge>
      case "PENDING":
        return <Badge className="bg-sky-500/10 text-sky-400 border border-sky-500/20 font-mono text-[10px]">PENDING</Badge>
      case "FAILED":
        return <Badge className="bg-rose-500/10 text-rose-400 border border-rose-500/20 font-mono text-[10px]">FAILED</Badge>
      case "INVALID_INPUT":
        return <Badge className="bg-amber-500/10 text-amber-400 border border-amber-500/20 font-mono text-[10px]">INVALID_INPUT</Badge>
      case "PROSE_REFUSAL":
        return <Badge className="bg-purple-500/10 text-purple-400 border border-purple-500/20 font-mono text-[10px]">PROSE_REFUSAL</Badge>
      case "MALFORMED_JSON":
        return <Badge className="bg-orange-500/10 text-orange-400 border border-orange-500/20 font-mono text-[10px]">MALFORMED_JSON</Badge>
      default:
        return <Badge className="bg-slate-500/10 text-slate-400 border border-slate-500/20 font-mono text-[10px]">{status}</Badge>
    }
  }

  const getTierContextWindow = (tier: string) => {
    switch (tier) {
      case "less_than_1k": return "1,024 Tokens"
      case "1k_to_2k": return "2,048 Tokens"
      case "2k_to_4k": return "4,096 Tokens"
      case "4k_to_8k": return "8,192 Tokens"
      case "8k_to_16k": return "16,384 Tokens"
      case "16k_to_32k": return "32,768 Tokens"
      case "32k_to_64k": return "65,536 Tokens"
      case "64k_to_128k": return "131,072 Tokens"
      case "128k_to_256k": return "262,144 Tokens"
      case "greater_than_256k": return "524,288 Tokens"
      default: return "4,096 Tokens"
    }
  }

  return (
    <div className="flex flex-col gap-6 text-slate-100 pb-12">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-slate-800/80 pb-6">
        <div>
          <div className="flex items-center gap-2 mb-1.5">
            <Link href="/" className="flex items-center text-xs text-slate-400 hover:text-slate-100 transition-colors">
              <ArrowLeft className="w-3.5 h-3.5 mr-1" />
              Observability Dashboard
            </Link>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-white flex items-center gap-3">
            <Database className="w-8 h-8 text-sky-400" />
            Unified Bug Bounty Control Room
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            vLLM Batch Execution Autopilot & Target Profitability Scoring Control Room.
          </p>
        </div>

        <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="w-full md:w-auto">
          <TabsList className="bg-slate-950 border border-slate-800 p-1">
            <TabsTrigger value="queue" className="text-xs font-mono data-[state=active]:bg-slate-800">
              <Database className="w-3.5 h-3.5 mr-1.5 text-sky-400" />
              Preflight Batch Queue
            </TabsTrigger>
            <TabsTrigger value="profitability" className="text-xs font-mono data-[state=active]:bg-slate-800 text-emerald-400">
              <TrendingUp className="w-3.5 h-3.5 mr-1.5 text-emerald-400" />
              Target Profitability Matrix
            </TabsTrigger>
          </TabsList>
        </Tabs>
      </div>

      {activeTab === "profitability" ? (
        <TargetProfitabilityMatrixView />
      ) : (
        <div className="flex flex-col gap-6">
          {/* SECTION 1: Top 10 Token Tier Summary Grid Cards */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <h2 className="text-sm font-semibold tracking-wider text-slate-300 uppercase flex items-center gap-2 font-mono">
                <Layers className="w-4 h-4 text-sky-400" />
                Token Tier Execution Buckets Summary (10 Tiers)
              </h2>
              <Button
                variant="outline"
                size="sm"
                className="border-slate-800 bg-slate-950 text-slate-300 text-xs h-7"
                onClick={fetchWorkspaceData}
              >
                <RefreshCw className="w-3 h-3 mr-1 text-sky-400" />
                Refresh Aggregations
              </Button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-3">
              {TOKEN_BUCKET_TIERS.map((tier) => {
                const stat = aggregations[tier] || { total: 0, dispatched: 0, pending: 0, failed: 0, invalid: 0 }
                const pct = stat.total > 0 ? Math.round((stat.dispatched / stat.total) * 100) : 0
                return (
                  <Card key={tier} className="bg-slate-950/80 border border-slate-800/80 p-3 flex flex-col justify-between hover:border-slate-700 transition-colors">
                    <div>
                      <div className="flex items-center justify-between text-[11px] font-mono text-slate-400 mb-1">
                        <span className="font-bold text-sky-300 truncate">{tier}</span>
                        <span className="text-slate-500">{stat.total} items</span>
                      </div>
                      <Progress value={pct} className="h-1.5 bg-slate-900" />
                      
                      <div className="grid grid-cols-2 gap-1 mt-2 text-[10px] font-mono">
                        <div className="text-emerald-400">Done: {stat.dispatched}</div>
                        <div className="text-sky-400">Pending: {stat.pending}</div>
                        <div className="text-rose-400">Failed: {stat.failed}</div>
                        <div className="text-amber-400">Invalid: {(stat.invalid || 0) + (stat.invalid_input || 0)}</div>
                      </div>
                    </div>

                    <Button
                      size="sm"
                      variant="outline"
                      className="mt-3 w-full border-slate-800 hover:bg-slate-900 bg-slate-950 text-[10px] font-mono h-6 text-sky-400"
                      onClick={() => handleDispatchTier(tier)}
                    >
                      <Play className="w-2.5 h-2.5 mr-1" />
                      Dispatch Tier
                    </Button>
                  </Card>
                )
              })}
            </div>
          </div>

          {/* SECTION 2: 2-Column Subsection (Telemetry Monitors & Maintenance Matrix) */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Left Column: RTX 5090 Autopilot Hardware Telemetry Monitors */}
            <Card className="bg-slate-950/70 border border-slate-800/80 backdrop-blur-xs p-5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-slate-900 pb-3 mb-4">
                  <div className="flex items-center gap-2">
                    <Cpu className="w-5 h-5 text-emerald-400" />
                    <div>
                      <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">RTX 5090 Cluster Telemetry Monitors</h3>
                      <p className="text-[11px] text-slate-400 font-mono">Live Hardware & vLLM Inter-Token Telemetry Stream</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-2 font-mono text-[10px]">
                    <span className={`w-2 h-2 rounded-full ${sseConnected ? "bg-emerald-400 animate-pulse" : "bg-rose-500"}`} />
                    <span className={sseConnected ? "text-emerald-400" : "text-rose-400"}>
                      {sseConnected ? "SSE LIVE" : "OFFLINE"}
                    </span>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono">
                  <div className="bg-slate-900/60 border border-slate-800/60 p-2.5 rounded">
                    <span className="text-[10px] text-slate-500 uppercase block">TTFT Latency</span>
                    <span className="text-base font-bold text-sky-400">{telemetry.ttft_ms} ms</span>
                  </div>
                  <div className="bg-slate-900/60 border border-slate-800/60 p-2.5 rounded">
                    <span className="text-[10px] text-slate-500 uppercase block">ITL Latency</span>
                    <span className="text-base font-bold text-emerald-400">{telemetry.itl_ms} ms</span>
                  </div>
                  <div className="bg-slate-900/60 border border-slate-800/60 p-2.5 rounded">
                    <span className="text-[10px] text-slate-500 uppercase block">Concurrency</span>
                    <span className="text-base font-bold text-amber-400">{telemetry.active_concurrency} / {telemetry.max_concurrency}</span>
                  </div>
                  <div className="bg-slate-900/60 border border-slate-800/60 p-2.5 rounded">
                    <span className="text-[10px] text-slate-500 uppercase block">GPU Load</span>
                    <span className="text-base font-bold text-purple-400">{telemetry.cluster_gpu_utilization_pct}%</span>
                  </div>
                </div>

                <div className="mt-4 grid grid-cols-2 gap-3 font-mono text-xs text-slate-400">
                  <div className="flex justify-between border-b border-slate-900 pb-1">
                    <span>VRAM Allocation:</span>
                    <span className="text-slate-200 font-bold">{telemetry.vram_allocated_gb} GB</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-900 pb-1">
                    <span>Queue Pending:</span>
                    <span className="text-slate-200 font-bold">{telemetry.pending_queue_length}</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-900 pb-1">
                    <span>Total Dispatched:</span>
                    <span className="text-slate-200 font-bold">{telemetry.completed_dispatches}</span>
                  </div>
                  <div className="flex justify-between border-b border-slate-900 pb-1">
                    <span>Cluster Host:</span>
                    <span className="text-slate-200 font-bold">192.168.1.57:8000</span>
                  </div>
                </div>
              </div>
            </Card>

            {/* Right Column: Ingest/Queue Maintenance Reset Action Center Button Matrix */}
            <Card className="bg-slate-950/70 border border-slate-800/80 backdrop-blur-xs p-5 flex flex-col justify-between">
              <div>
                <div className="flex items-center justify-between border-b border-slate-900 pb-3 mb-4">
                  <div className="flex items-center gap-2">
                    <Sliders className="w-5 h-5 text-sky-400" />
                    <div>
                      <h3 className="text-sm font-bold text-white uppercase tracking-wider font-mono">Ingest / Queue Maintenance Action Matrix</h3>
                      <p className="text-[11px] text-slate-400 font-mono">Control Operations & Requeue Trigger Engine</p>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 font-mono">
                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-800 bg-slate-900/50 hover:bg-slate-900 text-sky-400 text-[11px] h-9 justify-start"
                    onClick={() => handleAction("Full Ingestion", "/ingestion/compile")}
                  >
                    <Database className="w-3.5 h-3.5 mr-1.5 text-sky-400" />
                    Compile Source DBs
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-800 bg-slate-900/50 hover:bg-slate-900 text-emerald-400 text-[11px] h-9 justify-start"
                    onClick={() => handleAction("Recalculate Tokens", "/ingestion/calculate-tokens")}
                  >
                    <RefreshCw className="w-3.5 h-3.5 mr-1.5 text-emerald-400" />
                    Recalc Tokens
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-800 bg-slate-900/50 hover:bg-slate-900 text-amber-400 text-[11px] h-9 justify-start"
                    onClick={() => handleAction("Reset Status", "/ingestion/reset-status")}
                  >
                    <RotateCcw className="w-3.5 h-3.5 mr-1.5 text-amber-400" />
                    Reset Errored
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-800 bg-slate-900/50 hover:bg-slate-900 text-rose-400 text-[11px] h-9 justify-start"
                    onClick={() => handleAction("Stop Execution", "/ingestion/stop")}
                  >
                    <StopCircle className="w-3.5 h-3.5 mr-1.5 text-rose-400" />
                    Stop Workers
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    className="border-slate-800 bg-slate-900/50 hover:bg-slate-900 text-purple-400 text-[11px] h-9 justify-start"
                    onClick={() => handleAction("Export Queue", "/ingestion/export-simplified")}
                  >
                    <Download className="w-3.5 h-3.5 mr-1.5 text-purple-400" />
                    Export Queue JSON
                  </Button>

                  <Button
                    variant="outline"
                    size="sm"
                    disabled={selectedIds.length === 0}
                    className="border-slate-800 bg-slate-900/50 hover:bg-slate-900 text-sky-300 text-[11px] h-9 justify-start disabled:opacity-40"
                    onClick={() => handleAction("Requeue Batch Selected", "/ingestion/requeue-batch", { item_ids: selectedIds })}
                  >
                    <CheckSquare className="w-3.5 h-3.5 mr-1.5 text-sky-300" />
                    Requeue ({selectedIds.length})
                  </Button>
                </div>
              </div>
            </Card>
          </div>

          {/* SECTION 3: Streaming Black Text Terminal Log Output Section */}
          <Card className="bg-black border border-slate-800 overflow-hidden font-mono">
            <div className="bg-slate-950 border-b border-slate-800 px-4 py-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-bold text-slate-300">
                <Terminal className="w-4 h-4 text-emerald-400" />
                Live Autopilot Console Output Logs
              </div>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 text-[10px] text-slate-400 hover:text-white"
                onClick={() => setConsoleLogs([])}
              >
                Clear Terminal
              </Button>
            </div>
            <div className="p-4 h-40 overflow-y-auto text-xs text-emerald-400/90 leading-relaxed font-mono select-text">
              {consoleLogs.length === 0 ? (
                <span className="text-slate-600">Terminal ready. Waiting for events...</span>
              ) : (
                consoleLogs.map((log, i) => (
                  <div key={i} className="hover:bg-slate-900/40 px-1 py-0.5 rounded">
                    {log}
                  </div>
                ))
              )}
              <div ref={terminalEndRef} />
            </div>
          </Card>

          {/* SECTION 4: Primary Multi-Selection Relational Data Queue Grid Table */}
          <Card className="bg-slate-950/70 border border-slate-800/80 backdrop-blur-xs overflow-hidden">
            <CardHeader className="border-b border-slate-900 pb-4 bg-slate-950/40">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div>
                  <CardTitle className="text-base font-semibold tracking-wider text-white uppercase flex items-center gap-2">
                    <Database className="w-5 h-5 text-sky-400" />
                    Preflight Relational Data Queue Grid
                  </CardTitle>
                  <p className="text-slate-400 text-xs mt-1 font-mono">
                    Showing {filteredQueue.length} of {queue.length} preflight context window items.
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-3">
                  <div className="relative w-60">
                    <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
                    <Input
                      placeholder="Filter by ID, feed, type..."
                      className="pl-8 text-xs border-slate-800/80 bg-slate-900/50 text-slate-200 h-8"
                      value={queueSearchQuery}
                      onChange={(e) => setQueueSearchQuery(e.target.value)}
                    />
                  </div>

                  {/* Tier Filter */}
                  <select
                    className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded px-2.5 py-1 font-mono h-8"
                    value={selectedTierFilter || ""}
                    onChange={(e) => setSelectedTierFilter(e.target.value || null)}
                  >
                    <option value="">All Tiers</option>
                    {TOKEN_BUCKET_TIERS.map(t => (
                      <option key={t} value={t}>{t}</option>
                    ))}
                  </select>

                  {/* Status Filter */}
                  <select
                    className="bg-slate-900 border border-slate-800 text-slate-300 text-xs rounded px-2.5 py-1 font-mono h-8"
                    value={selectedStatusFilter || ""}
                    onChange={(e) => setSelectedStatusFilter(e.target.value || null)}
                  >
                    <option value="">All Statuses</option>
                    <option value="PENDING">PENDING</option>
                    <option value="DISPATCHED">DISPATCHED</option>
                    <option value="FAILED">FAILED</option>
                    <option value="INVALID_INPUT">INVALID_INPUT</option>
                    <option value="PROSE_REFUSAL">PROSE_REFUSAL</option>
                    <option value="MALFORMED_JSON">MALFORMED_JSON</option>
                  </select>

                  {/* Batch Action */}
                  {selectedIds.length > 0 && (
                    <Button
                      size="sm"
                      className="bg-sky-600 hover:bg-sky-500 text-white font-mono text-xs h-8"
                      onClick={() => handleAction("Batch Requeue", "/ingestion/requeue-batch", { item_ids: selectedIds })}
                    >
                      Requeue Selected ({selectedIds.length})
                    </Button>
                  )}
                </div>
              </div>
            </CardHeader>

            <div className="overflow-x-auto min-h-[400px]">
              <Table className="border-collapse">
                <TableHeader className="bg-slate-900/40 border-b border-slate-900 font-mono text-[11px] text-slate-400 uppercase tracking-wider">
                  <TableRow>
                    <TableHead className="w-10 text-center">
                      <input
                        type="checkbox"
                        className="rounded border-slate-800 bg-slate-900 text-sky-400 focus:ring-0"
                        checked={filteredQueue.length > 0 && selectedIds.length === filteredQueue.length}
                        onChange={(e) => handleSelectAll(e.target.checked)}
                      />
                    </TableHead>
                    <TableHead className="w-16 text-slate-400">ID</TableHead>
                    <TableHead className="w-32 text-slate-400">Source Feed</TableHead>
                    <TableHead className="w-44 text-slate-400">Request Type</TableHead>
                    <TableHead className="w-28 text-slate-400">Char Length</TableHead>
                    <TableHead className="w-28 text-slate-400">Est Tokens</TableHead>
                    <TableHead className="w-32 text-slate-400">Context Window</TableHead>
                    <TableHead className="w-36 text-slate-400">Token Tier</TableHead>
                    <TableHead className="w-32 text-slate-400">Status</TableHead>
                    <TableHead className="w-32 text-right pr-4 text-slate-400">Action</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="text-xs divide-y divide-slate-900/60 font-mono">
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={10} className="text-center py-12 text-slate-500">
                        <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-sky-400" />
                        Loading Preflight Queue Items...
                      </TableCell>
                    </TableRow>
                  ) : filteredQueue.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={10} className="text-center py-12 text-slate-500">
                        No preflight queue records found matching criteria.
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredQueue.map((item) => {
                      const isSelected = selectedIds.includes(item.id)
                      return (
                        <TableRow key={item.id} className={`hover:bg-slate-900/50 border-b border-slate-900/40 ${isSelected ? "bg-slate-900/40" : ""}`}>
                          <TableCell className="text-center">
                            <input
                              type="checkbox"
                              className="rounded border-slate-800 bg-slate-900 text-sky-400 focus:ring-0"
                              checked={isSelected}
                              onChange={() => handleSelectRow(item.id)}
                            />
                          </TableCell>
                          <TableCell className="text-slate-400 font-bold">#{item.id}</TableCell>
                          <TableCell>
                            <Badge variant="outline" className="border-slate-800 bg-slate-900 text-slate-300 font-mono text-[10px]">
                              {item.source_pool} / {item.source_identifier}
                            </Badge>
                          </TableCell>
                          <TableCell className="text-slate-300 font-medium">{item.request_type}</TableCell>
                          <TableCell className="text-slate-400">{item.character_count?.toLocaleString()}</TableCell>
                          <TableCell className="text-sky-300 font-bold">{item.estimated_tokens?.toLocaleString()}</TableCell>
                          <TableCell className="text-slate-400">{getTierContextWindow(item.token_bucket_tier)}</TableCell>
                          <TableCell>
                            <span className="text-[11px] font-mono text-sky-400 bg-sky-950/40 border border-sky-500/30 px-2 py-0.5 rounded">
                              {item.token_bucket_tier}
                            </span>
                          </TableCell>
                          <TableCell>{renderStatusBadge(item.dispatch_status)}</TableCell>
                          <TableCell className="text-right pr-4">
                            <div className="flex items-center justify-end gap-1.5">
                              <Button
                                size="sm"
                                variant="outline"
                                className="border-slate-800 hover:bg-slate-900 text-[10px] h-6 px-2 text-amber-400"
                                onClick={() => handleAction(`Requeue #${item.id}`, `/ingestion/requeue/${item.id}`)}
                              >
                                Requeue
                              </Button>
                              <Button
                                size="sm"
                                variant="outline"
                                className="border-slate-800 hover:bg-slate-900 text-[10px] h-6 px-2 text-sky-400"
                                onClick={() => handleOpenInspector(item)}
                              >
                                Inspect
                              </Button>
                            </div>
                          </TableCell>
                        </TableRow>
                      )
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          </Card>

          {/* SECTION 5: Side-Sheet Slide Drawer Inspector */}
          <Sheet open={drawerOpen} onOpenChange={setDrawerOpen}>
            <SheetContent className="bg-slate-950 border-l border-slate-800 text-slate-100 sm:max-w-xl overflow-y-auto">
              <SheetHeader>
                <SheetTitle className="text-lg font-bold text-white flex items-center gap-2 font-mono">
                  <FileCode className="w-5 h-5 text-sky-400" />
                  Preflight Queue Inspector #{selectedEntry?.id}
                </SheetTitle>
                <SheetDescription className="text-xs text-slate-400 font-mono">
                  View and edit system/user prompt payloads or review response payloads.
                </SheetDescription>
              </SheetHeader>

              {selectedEntry && (
                <div className="mt-6 flex flex-col gap-4">
                  <div className="flex items-center justify-between bg-slate-900/60 p-3 rounded border border-slate-800/80 font-mono text-xs">
                    <div>
                      <span className="text-slate-500 block text-[10px]">TARGET:</span>
                      <span className="text-white font-bold">{selectedEntry.source_pool} / {selectedEntry.source_identifier}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px]">TIER:</span>
                      <span className="text-sky-400">{selectedEntry.token_bucket_tier}</span>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px]">STATUS:</span>
                      {renderStatusBadge(selectedEntry.dispatch_status)}
                    </div>
                  </div>

                  <Tabs value={editingTab} onValueChange={(v) => setEditingTab(v as any)}>
                    <TabsList className="bg-slate-900 border border-slate-800 p-1 w-full grid grid-cols-4">
                      <TabsTrigger value="sys" className="text-xs font-mono">System Prompt</TabsTrigger>
                      <TabsTrigger value="usr" className="text-xs font-mono">User Prompt</TabsTrigger>
                      <TabsTrigger value="details" className="text-xs font-mono">Details</TabsTrigger>
                      <TabsTrigger value="raw" className="text-xs font-mono">Payload</TabsTrigger>
                    </TabsList>

                    <TabsContent value="sys" className="mt-3">
                      <label className="text-xs font-mono text-slate-400 block mb-1">System Prompt Payload:</label>
                      <textarea
                        className="w-full h-64 bg-black border border-slate-800 rounded p-3 text-xs font-mono text-emerald-400 focus:outline-none focus:border-sky-500"
                        value={editSysPrompt}
                        onChange={(e) => setEditSysPrompt(e.target.value)}
                      />
                    </TabsContent>

                    <TabsContent value="usr" className="mt-3">
                      <label className="text-xs font-mono text-slate-400 block mb-1">User Prompt Payload:</label>
                      <textarea
                        className="w-full h-64 bg-black border border-slate-800 rounded p-3 text-xs font-mono text-sky-300 focus:outline-none focus:border-sky-500"
                        value={editUsrPrompt}
                        onChange={(e) => setEditUsrPrompt(e.target.value)}
                      />
                    </TabsContent>

                    <TabsContent value="details" className="mt-3">
                      <div className="bg-slate-900/40 border border-slate-800 p-4 rounded font-mono text-xs flex flex-col gap-2">
                        <div><span className="text-slate-500">Item ID:</span> {selectedEntry.id}</div>
                        <div><span className="text-slate-500">Request Type:</span> {selectedEntry.request_type}</div>
                        <div><span className="text-slate-500">Character Count:</span> {selectedEntry.character_count}</div>
                        <div><span className="text-slate-500">Estimated Tokens:</span> {selectedEntry.estimated_tokens}</div>
                        <div><span className="text-slate-500">Refusal Guard Text:</span> {selectedEntry.refusal_prompt_payload || "Default Refusal Guard"}</div>
                        {selectedEntry.error_log && (
                          <div className="mt-2 p-2 bg-rose-950/40 border border-rose-800/50 rounded text-rose-300">
                            <span className="font-bold block text-[10px] text-rose-400">ERROR LOG:</span>
                            {selectedEntry.error_log}
                          </div>
                        )}
                      </div>
                    </TabsContent>

                    <TabsContent value="raw" className="mt-3">
                      <label className="text-xs font-mono text-slate-400 block mb-1">Response Payload / Raw Data:</label>
                      <pre className="w-full h-64 bg-black border border-slate-800 rounded p-3 text-xs font-mono text-slate-300 overflow-auto whitespace-pre-wrap">
                        {selectedEntry.response_payload || "No response payload received yet."}
                      </pre>
                    </TabsContent>
                  </Tabs>

                  <div className="flex items-center justify-end gap-3 border-t border-slate-900 pt-4 mt-2">
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-slate-800 text-slate-400 text-xs"
                      onClick={() => setDrawerOpen(false)}
                    >
                      Cancel
                    </Button>
                    <Button
                      size="sm"
                      className="bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs flex items-center gap-1.5"
                      onClick={handleSavePromptsAndRequeue}
                    >
                      <Save className="w-3.5 h-3.5" />
                      Save & Requeue Item
                    </Button>
                  </div>
                </div>
              )}
            </SheetContent>
          </Sheet>
        </div>
      )}
    </div>
  )
}
