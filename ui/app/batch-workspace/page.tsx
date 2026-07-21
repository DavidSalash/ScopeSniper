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

interface PromptConfig {
  structural_extraction: { agent_name: string; system_prompt: string; user_prompt_template: string }
  taxonomy_tagging: { agent_name: string; system_prompt: string; user_prompt_template: string }
  refusal_prompt: string
  max_tokens?: number
  concurrency_slots?: number
  selected_model?: string
  available_models?: string[]
}

interface Aggregations {
  [key: string]: TierStats
}

interface SystemDiagnostics {
  docker: {
    connected: boolean
    active_sandbox_containers: number
  }
  llm_lock: {
    concurrency_limit: number
    queued_requests: number
  }
  resources: {
    backend_memory_mb: number
    cpu_percentage: number
  }
  swarm_status: {
    queued: number
    running: number
    paused: number
  }
  log_stats: {
    info: number
    warning: number
    error: number
  }
}

// High-fidelity terminal solidity code formatter
const HighlightSolidityCode = React.memo(function HighlightSolidityCode({ code }: { code: string }) {
  if (!code) return <div className="text-slate-500 font-mono text-xs">Empty payload</div>

  const renderedLines = useMemo(() => {
    const keywords = [
      "pragma", "solidity", "contract", "library", "interface", "is", "function",
      "modifier", "returns", "return", "mapping", "address", "uint256", "uint",
      "bool", "string", "bytes", "memory", "storage", "calldata", "public",
      "private", "internal", "external", "view", "pure", "payable", "constant",
      "immutable", "require", "assert", "revert", "if", "else", "for", "while",
      "emit", "event", "constructor", "struct", "enum", "assembly"
    ]
    
    return code.split("\n").map((line, idx) => {
      let highlighted = line
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")

      keywords.forEach((kw) => {
        const regex = new RegExp(`\\b${kw}\\b`, "g")
        highlighted = highlighted.replace(regex, `<span class="text-sky-400 font-semibold">${kw}</span>`)
      })

      highlighted = highlighted.replace(/(["'])(.*?)\1/g, `<span class="text-amber-400">"$2"</span>`)

      if (line.trim().startsWith("//") || line.trim().startsWith("*")) {
        highlighted = `<span class="text-slate-500 font-normal">${highlighted}</span>`
      } else {
        highlighted = highlighted.replace(/(\/\/.*)$/g, `<span class="text-slate-500">$1</span>`)
      }

      return { idx, highlighted }
    })
  }, [code])

  return (
    <pre className="font-mono text-[11px] leading-relaxed text-slate-300 whitespace-pre-wrap break-words overflow-y-auto bg-slate-950 p-4 rounded-md border border-slate-900 shadow-inner max-h-[380px]">
      <div className="table w-full">
        {renderedLines.map((line) => (
          <div key={line.idx} className="table-row">
            <span className="table-cell text-slate-600 text-right pr-4 select-none w-8 text-left">{line.idx + 1}</span>
            <span className="table-cell">{line.highlighted ? <span dangerouslySetInnerHTML={{ __html: line.highlighted }} /> : " "}</span>
          </div>
        ))}
      </div>
    </pre>
  )
})

function PrettyJsonViewer({ data }: { data: any }) {
  const jsonString = useMemo(() => {
    try {
      if (typeof data === "string") {
        return JSON.stringify(JSON.parse(data), null, 2)
      }
      return JSON.stringify(data, null, 2)
    } catch (e) {
      return typeof data === "string" ? data : ""
    }
  }, [data])

  return (
    <pre className="font-mono text-[11px] leading-relaxed text-sky-300 whitespace-pre-wrap break-words overflow-y-auto bg-slate-950 p-4 rounded-md border border-slate-900 shadow-inner max-h-[380px] select-text">
      {jsonString}
    </pre>
  )
}

function RequestDetailsView({ item, maxTokens }: { item: BatchEntry; maxTokens: number }) {
  const requestDetails = useMemo(() => {
    const messages: { role: string; content: string }[] = [
      { role: "system", content: item.system_prompt_payload },
      { role: "user", content: item.user_prompt_payload }
    ]
    const refusalText = item.refusal_prompt_payload || "IMPORTANT INSTRUCTION: If the input provided above does not contain valid source code or relevant data for your analysis task, or if you cannot extract the requested information because it is simply not present in the input, respond with exactly the words 'invalid input' at the end of your response. Do not attempt to fabricate, hallucinate, or infer information that is not present in the input."
    messages.push({ role: "user", content: refusalText })
    return {
      url: "http://192.168.1.57:8000/v1/chat/completions",
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "Authorization": "Bearer dummy"
      },
      body: {
        model: "qwen",
        messages,
        max_tokens: maxTokens,
        temperature: 0.2
      }
    }
  }, [item, maxTokens])

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 bg-slate-900/40 p-3 rounded-lg border border-slate-800/40 font-mono text-[11px]">
        <div>
          <span className="text-slate-500 block">METHOD & ENDPOINT</span>
          <span className="text-sky-400 block font-bold">POST v1/chat/completions</span>
        </div>
        <div>
          <span className="text-slate-500 block">LOCAL IP ENDPOINT</span>
          <span className="text-slate-300 block truncate">192.168.1.57:8000</span>
        </div>
        <div>
          <span className="text-slate-500 block">TIMEOUT CONSTRAINT</span>
          <span className="text-slate-300 block">120.0s (Max Edge Limit)</span>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-wider">
          HTTP Transport Headers
        </div>
        <pre className="font-mono text-[11px] leading-relaxed text-slate-400 bg-slate-950 p-3 rounded-md border border-slate-900 select-text">
{`{
  "Content-Type": "application/json",
  "Authorization": "Bearer dummy"
}`}
        </pre>
      </div>

      <div className="flex flex-col gap-1.5">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-wider">
          Full JSON Request Body
        </div>
        <PrettyJsonViewer data={requestDetails.body} />
      </div>
    </div>
  )
}

function ResponseDetailsView({ responsePayload }: { responsePayload: string }) {
  const parsed = useMemo(() => {
    try {
      return JSON.parse(responsePayload)
    } catch (e) {
      return null
    }
  }, [responsePayload])

  if (!parsed) {
    return (
      <div className="flex flex-col gap-2">
        <div className="text-[10px] text-slate-500 font-mono">RAW UNFORMATTED RESPONSE</div>
        <pre className="font-mono text-[11px] leading-relaxed text-slate-300 whitespace-pre-wrap break-words overflow-y-auto bg-slate-950 p-4 rounded-md border border-slate-900 shadow-inner max-h-[380px] select-text">
          {responsePayload}
        </pre>
      </div>
    )
  }

  const message = parsed.choices?.[0]?.message
  const content = message?.content
  const reasoning = message?.reasoning || message?.thinking
  const usage = parsed.usage

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2 bg-slate-900/40 p-3 rounded-lg border border-slate-800/40 font-mono text-[11px]">
        <div>
          <span className="text-slate-500 block">MODEL</span>
          <span className="text-slate-300 block truncate font-bold">{parsed.model || "Unknown"}</span>
        </div>
        {usage && (
          <>
            <div>
              <span className="text-slate-500 block">PROMPT TOKENS</span>
              <span className="text-slate-300 block">{usage.prompt_tokens ?? 0}</span>
            </div>
            <div>
              <span className="text-slate-500 block">COMPLETION TOKENS</span>
              <span className="text-slate-300 block text-sky-400 font-bold">{usage.completion_tokens ?? 0}</span>
            </div>
            <div>
              <span className="text-slate-500 block">TOTAL TOKENS</span>
              <span className="text-slate-300 block">{usage.total_tokens ?? 0}</span>
            </div>
          </>
        )}
      </div>

      {reasoning && (
        <div className="flex flex-col gap-1.5">
          <div className="text-[10px] text-amber-500 font-mono font-semibold uppercase tracking-wider flex items-center gap-1.5">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
            Model Thinking Process
          </div>
          <pre className="font-mono text-[11px] leading-relaxed text-amber-200/90 whitespace-pre-wrap break-words overflow-y-auto bg-amber-950/15 p-4 rounded-md border border-amber-900/30 max-h-[250px] shadow-inner select-text">
            {reasoning}
          </pre>
        </div>
      )}

      {content && (
        <div className="flex flex-col gap-1.5">
          <div className="text-[10px] text-emerald-500 font-mono font-semibold uppercase tracking-wider">
            Assistant Completion Content
          </div>
          <HighlightSolidityCode code={content} />
        </div>
      )}

      <div className="flex flex-col gap-1.5">
        <div className="text-[10px] text-slate-500 font-mono uppercase tracking-wider">
          Pretty Raw JSON Response
        </div>
        <PrettyJsonViewer data={parsed} />
      </div>
    </div>
  )
}

function EditItemPromptsView({ item, onSaveAndRequeue }: { 
  item: BatchEntry; 
  onSaveAndRequeue: (id: number, sys: string, usr: string, refusal: string) => void 
}) {
  const defaultRefusal = "IMPORTANT INSTRUCTION: If the input provided above does not contain valid source code or relevant data for your analysis task, or if you cannot extract the requested information because it is simply not present in the input, respond with exactly the words 'invalid input' at the end of your response. Do not attempt to fabricate, hallucinate, or infer information that is not present in the input."
  
  const [editSys, setEditSys] = useState(item.system_prompt_payload || "")
  const [editUsr, setEditUsr] = useState(item.user_prompt_payload || "")
  const [editRefusal, setEditRefusal] = useState(item.refusal_prompt_payload || defaultRefusal)

  useEffect(() => {
    setEditSys(item.system_prompt_payload || "")
    setEditUsr(item.user_prompt_payload || "")
    setEditRefusal(item.refusal_prompt_payload || defaultRefusal)
  }, [item.id])

  return (
    <div className="flex flex-col gap-4">
      <p className="text-[11px] text-slate-400 leading-relaxed">
        Edit the prompts for this specific request. Saving will update the record and immediately requeue it for dispatch.
      </p>

      <div className="flex flex-col gap-1.5">
        <label className="text-[10px] text-slate-500 font-mono uppercase">System Prompt</label>
        <textarea
          className="bg-slate-950 border border-slate-800 rounded p-3 text-xs font-mono text-slate-300 focus:outline-none focus:border-slate-700 resize-y min-h-[70px] max-h-[180px] leading-relaxed"
          value={editSys}
          onChange={(e) => setEditSys(e.target.value)}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-[10px] text-slate-500 font-mono uppercase">User Prompt</label>
        <textarea
          className="bg-slate-950 border border-slate-800 rounded p-3 text-xs font-mono text-slate-300 focus:outline-none focus:border-slate-700 resize-y min-h-[70px] max-h-[180px] leading-relaxed"
          value={editUsr}
          onChange={(e) => setEditUsr(e.target.value)}
        />
      </div>

      <div className="flex flex-col gap-1.5">
        <label className="text-[10px] text-orange-400 font-mono uppercase flex items-center gap-1.5">
          <ShieldAlert className="w-3 h-3" />
          Refusal Guard Instruction
        </label>
        <textarea
          className="bg-slate-950 border border-orange-900/30 rounded p-3 text-xs font-mono text-orange-200 focus:outline-none focus:border-orange-800 resize-y min-h-[60px] max-h-[150px] leading-relaxed"
          value={editRefusal}
          onChange={(e) => setEditRefusal(e.target.value)}
        />
      </div>

      <Button
        size="sm"
        className="bg-indigo-600 hover:bg-indigo-700 text-white font-mono flex items-center gap-1.5 self-end"
        onClick={() => onSaveAndRequeue(item.id, editSys, editUsr, editRefusal)}
      >
        <Save className="w-3.5 h-3.5" />
        Save & Requeue
      </Button>
    </div>
  )
}

export interface PreProcessedItem {
  id: string
  source_pool: string
  protocol_name: string
  title: string
  severity?: string
  system_prompt_tokens?: number
  user_prompt_tokens?: number
  total_tokens: number
  context_tier: string
  enrichment_status: "COMPLETED" | "PENDING"
  status?: string
}

export interface SummaryCounts {
  less_than_1k: number
  "1k_to_2k": number
  "2k_to_4k": number
  greater_than_4k: number
}

function PreProcessedQueueInspectorView({ addConsoleLog }: { addConsoleLog: (msg: string, type?: "info" | "warn" | "error") => void }) {
  const [items, setItems] = useState<PreProcessedItem[]>([])
  const [summaryCounts, setSummaryCounts] = useState<SummaryCounts>({
    less_than_1k: 0,
    "1k_to_2k": 77875,
    "2k_to_4k": 508,
    greater_than_4k: 0
  })
  const [totalStaged, setTotalStaged] = useState(78383)
  const [totalMatching, setTotalMatching] = useState(0)
  const [page, setPage] = useState(1)
  const [limit, setLimit] = useState(50)
  const [selectedTier, setSelectedTier] = useState<string | null>(null)
  const [searchQuery, setSearchQuery] = useState("")
  const [debouncedSearch, setDebouncedSearch] = useState("")
  const [loading, setLoading] = useState(true)

  // Control State
  const [batchStatus, setBatchStatus] = useState<"RUNNING" | "STOPPED">("STOPPED")
  const [isControlling, setIsControlling] = useState(false)

  // Debounce search query updates
  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedSearch(searchQuery)
    }, 300)
    return () => clearTimeout(handler)
  }, [searchQuery])

  const fetchPreprocessedQueue = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true)
    try {
      const params = new URLSearchParams()
      params.append("page", page.toString())
      params.append("limit", limit.toString())
      if (selectedTier) params.append("tier", selectedTier)
      if (debouncedSearch.trim()) params.append("search", debouncedSearch.trim())

      const res = await fetch(`${API_URL}/batch/queue?${params.toString()}`)
      if (res.ok) {
        const data = await res.json()
        setItems(data.items || [])
        setTotalStaged(data.total_staged || 78383)
        setTotalMatching(data.total || (data.items ? data.items.length : 0))
        if (data.summary_counts) setSummaryCounts(data.summary_counts)
      } else {
        addConsoleLog(`Failed to fetch preprocessed queue: ${res.statusText}`, "error")
      }
    } catch (e) {
      addConsoleLog(`Error requesting preprocessed queue: ${e}`, "error")
    } finally {
      setLoading(false)
    }
  }, [page, limit, selectedTier, debouncedSearch, addConsoleLog])

  const checkBatchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/batch/control?action=status`)
      if (res.ok) {
        const data = await res.json()
        setBatchStatus(data.batch_status || "STOPPED")
      }
    } catch (e) {
      console.error("Failed to check batch control status:", e)
    }
  }, [])

  useEffect(() => {
    fetchPreprocessedQueue(items.length === 0)
  }, [page, limit, selectedTier, debouncedSearch])

  useEffect(() => {
    checkBatchStatus()
    const interval = setInterval(checkBatchStatus, 5000)
    return () => clearInterval(interval)
  }, [checkBatchStatus])

  const handleToggleInferenceRun = async () => {
    setIsControlling(true)
    const targetAction = batchStatus === "RUNNING" ? "pause" : "start"
    addConsoleLog(`Sending batch control command: '${targetAction}'...`, "info")
    try {
      const res = await fetch(`${API_URL}/batch/control`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action: targetAction })
      })
      if (res.ok) {
        const data = await res.json()
        setBatchStatus(data.batch_status || "STOPPED")
        addConsoleLog(`Batch control response: ${data.message}`, "info")
        fetchPreprocessedQueue()
      } else {
        const err = await res.text()
        addConsoleLog(`Batch control command failed: ${err}`, "error")
      }
    } catch (e) {
      addConsoleLog(`Exception sending batch control command: ${e}`, "error")
    } finally {
      setIsControlling(false)
    }
  }

  const totalPages = Math.ceil(totalMatching / limit) || 1

  return (
    <div className="flex flex-col gap-6">
      {/* Control Banner & Action Trigger */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-slate-950/70 border border-slate-800/80 p-4 rounded-xl backdrop-blur-xs">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-sky-500/10 border border-sky-500/20 rounded-lg text-sky-400">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-white tracking-wide uppercase">
                78k Pre-Processed Inference Queue Inspector
              </h2>
              <Badge className={batchStatus === "RUNNING" ? "bg-emerald-500/20 text-emerald-400 border-emerald-500/30 animate-pulse font-mono" : "bg-slate-800 text-slate-400 border-slate-700 font-mono"}>
                {batchStatus === "RUNNING" ? "INFERENCE ACTIVE" : "IDLE / STOPPED"}
              </Badge>
            </div>
            <p className="text-xs text-slate-400 font-mono mt-0.5">
              Total Staged Records: <span className="text-sky-300 font-bold">{totalStaged.toLocaleString()}</span> | Formatted Token Vectors Ready for GPU Enrichment
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          <Button
            size="sm"
            className={batchStatus === "RUNNING" 
              ? "bg-rose-600 hover:bg-rose-700 text-white font-mono flex items-center gap-2" 
              : "bg-emerald-600 hover:bg-emerald-700 text-white font-mono flex items-center gap-2 shadow-[0_0_12px_rgba(16,185,129,0.3)]"}
            disabled={isControlling}
            onClick={handleToggleInferenceRun}
          >
            {isControlling ? (
              <RefreshCw className="w-4 h-4 animate-spin" />
            ) : batchStatus === "RUNNING" ? (
              <ZapOff className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4 fill-current" />
            )}
            {batchStatus === "RUNNING" ? "Pause Inference Run" : "Launch Inference Run"}
          </Button>

          <Button
            variant="outline"
            size="sm"
            className="border-slate-800 hover:bg-slate-900 bg-slate-950 text-slate-300 h-9 font-mono"
            onClick={() => fetchPreprocessedQueue()}
          >
            <RefreshCw className="w-3.5 h-3.5 mr-1.5 text-sky-400" />
            Refresh Queue
          </Button>
        </div>
      </div>

      {/* 1. Token Tier Cards (4 Tiers: <1k, 1k-2k, 2k-4k, >4k) */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { key: "less_than_1k", label: "<1k Tokens", color: "from-emerald-500/20 to-teal-500/10", border: "border-emerald-500/20" },
          { key: "1k_to_2k", label: "1k - 2k Tokens", color: "from-teal-500/20 to-cyan-500/10", border: "border-teal-500/20" },
          { key: "2k_to_4k", label: "2k - 4k Tokens", color: "from-cyan-500/20 to-sky-500/10", border: "border-cyan-500/20" },
          { key: "greater_than_4k", label: ">4k Tokens", color: "from-sky-500/20 to-indigo-500/10", border: "border-sky-500/20" }
        ].map((card) => {
          const count = summaryCounts[card.key as keyof SummaryCounts] || 0
          const isFilterActive = selectedTier === card.key
          const percentage = totalStaged > 0 ? ((count / totalStaged) * 100).toFixed(1) : "0.0"

          return (
            <Card
              key={card.key}
              className={`bg-slate-950/70 border ${card.border} backdrop-blur-xs relative overflow-hidden transition-all duration-300 cursor-pointer hover:border-slate-500 ${isFilterActive ? "ring-2 ring-sky-500 shadow-[0_0_15px_rgba(56,189,248,0.25)]" : ""}`}
              onClick={() => {
                setSelectedTier(isFilterActive ? null : card.key)
                setPage(1)
              }}
            >
              <div className={`absolute top-0 inset-x-0 h-1 bg-gradient-to-r ${card.color}`} />
              <CardContent className="pt-5 pb-4">
                <div className="flex items-center justify-between mb-2">
                  <span className="text-slate-400 text-xs font-semibold uppercase tracking-wider">{card.label}</span>
                  {isFilterActive && (
                    <Badge className="bg-sky-500/20 text-sky-400 border border-sky-500/30 rounded px-1.5 font-bold uppercase text-[9px]">
                      FILTERED
                    </Badge>
                  )}
                </div>

                <div className="flex items-baseline justify-between mb-3">
                  <span className="text-3xl font-bold text-white tracking-tight">{count.toLocaleString()}</span>
                  <span className="text-slate-400 text-xs font-mono">{percentage}% of queue</span>
                </div>

                <Progress value={parseFloat(percentage)} className="h-1.5" />
              </CardContent>
            </Card>
          )
        })}
      </div>

      {/* 2. Search & Filter Controls and Data Table */}
      <Card className="bg-slate-950/70 border border-slate-800/80 backdrop-blur-xs overflow-hidden">
        <CardHeader className="border-b border-slate-900 pb-4 bg-slate-950/40">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <CardTitle className="text-sm font-semibold tracking-wider text-slate-300 uppercase flex items-center gap-2">
                <Layers className="w-4 h-4 text-sky-400" />
                Pre-Processed Finding Queue Table
              </CardTitle>
              <Badge className="bg-sky-500/10 text-sky-400 border border-sky-500/20 font-mono text-[10px]">
                {totalMatching.toLocaleString()} Items Filtered
              </Badge>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              {/* Search input */}
              <div className="relative w-64">
                <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
                <Input
                  placeholder="Search finding ID, protocol, pool..."
                  className="pl-8 text-xs border-slate-800/80 bg-slate-900/50 text-slate-200 h-8"
                  value={searchQuery}
                  onChange={(e) => {
                    setSearchQuery(e.target.value)
                    setPage(1)
                  }}
                />
              </div>

              {/* Tier Filter Pills */}
              <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono bg-slate-900/30 border border-slate-800/50 rounded px-2.5 py-1">
                <Filter className="w-3.5 h-3.5 text-slate-500" />
                <span className="text-slate-500">TIER:</span>
                {[
                  { id: null, label: "All" },
                  { id: "less_than_1k", label: "<1k" },
                  { id: "1k_to_2k", label: "1k-2k" },
                  { id: "2k_to_4k", label: "2k-4k" },
                  { id: "greater_than_4k", label: ">4k" }
                ].map((t) => (
                  <button
                    key={t.label}
                    onClick={() => {
                      setSelectedTier(t.id)
                      setPage(1)
                    }}
                    className={`hover:text-white transition-colors text-[11px] ${
                      selectedTier === t.id ? "text-sky-400 font-bold" : "text-slate-400"
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        </CardHeader>

        {/* 3. Paginated Data Table */}
        <div className="overflow-x-auto min-h-[350px]">
          <Table className="border-collapse">
            <TableHeader className="bg-slate-900/40 border-b border-slate-900 font-mono text-[11px] text-slate-400 uppercase tracking-wider">
              <TableRow>
                <TableHead className="w-12 text-slate-400">#</TableHead>
                <TableHead className="w-64 text-slate-400">Finding ID</TableHead>
                <TableHead className="w-32 text-slate-400">Source Pool</TableHead>
                <TableHead className="w-48 text-slate-400">Protocol / Repo</TableHead>
                <TableHead className="w-36 text-slate-400">Token Count</TableHead>
                <TableHead className="w-36 text-slate-400">Context Tier</TableHead>
                <TableHead className="w-36 text-slate-400">Enrichment Status</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody className="text-xs divide-y divide-slate-900/60 font-mono">
              {loading ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-12 text-slate-500">
                    <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-sky-400" />
                    Fetching pre-processed findings...
                  </TableCell>
                </TableRow>
              ) : items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-12 text-slate-500">
                    No pre-processed queue items match your filter criteria.
                  </TableCell>
                </TableRow>
              ) : (
                items.map((row, idx) => (
                  <TableRow key={`${row.id}-${idx}`} className="hover:bg-slate-900/50 border-b border-slate-900/40">
                    <TableCell className="text-slate-500 font-bold">{(page - 1) * limit + idx + 1}</TableCell>
                    <TableCell>
                      <div className="font-bold text-white text-xs truncate max-w-[240px]" title={row.id}>
                        {row.id}
                      </div>
                      <div className="text-[10px] text-slate-500 font-mono truncate max-w-[240px]">
                        {row.title || "No Title"}
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline" className="bg-slate-900/80 border-slate-800 text-slate-300 font-mono text-[10px] uppercase">
                        {row.source_pool}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-slate-300 font-medium">{row.protocol_name}</TableCell>
                    <TableCell>
                      <span className="text-sky-300 font-bold font-mono">{row.total_tokens?.toLocaleString() || 0}</span>
                      <span className="text-[10px] text-slate-500 block font-mono">
                        sys:{row.system_prompt_tokens || 0} | usr:{row.user_prompt_tokens || 0}
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant="secondary" className="bg-indigo-950/40 border border-indigo-500/20 text-indigo-300 font-mono text-[10px]">
                        {row.context_tier}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      {row.enrichment_status === "COMPLETED" ? (
                        <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-[0_0_8px_rgba(16,185,129,0.2)]">
                          <CheckCircle className="w-3 h-3 mr-1 inline" />
                          COMPLETED
                        </Badge>
                      ) : (
                        <Badge className="bg-amber-500/10 text-amber-500 border border-amber-500/20 animate-pulse">
                          PENDING
                        </Badge>
                      )}
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </div>

        {/* Pagination Footer */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4 p-4 border-t border-slate-900 bg-slate-950/40 text-xs font-mono text-slate-400">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span>Page Size:</span>
              <select
                className="bg-slate-900 border border-slate-800 rounded px-2 py-1 text-slate-200 text-xs focus:outline-none"
                value={limit}
                onChange={(e) => {
                  setLimit(parseInt(e.target.value))
                  setPage(1)
                }}
              >
                <option value="25">25</option>
                <option value="50">50</option>
                <option value="100">100</option>
                <option value="250">250</option>
              </select>
            </div>
            <div>
              Showing <span className="text-slate-200 font-bold">{totalMatching > 0 ? (page - 1) * limit + 1 : 0}</span> to{" "}
              <span className="text-slate-200 font-bold">{Math.min(page * limit, totalMatching)}</span> of{" "}
              <span className="text-slate-200 font-bold">{totalMatching.toLocaleString()}</span> entries
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              className="border-slate-800 bg-slate-900 hover:bg-slate-950 text-slate-300 h-8 font-mono"
              disabled={page <= 1 || loading}
              onClick={() => setPage(page - 1)}
            >
              Previous
            </Button>
            <span className="text-slate-400 text-xs px-2">
              Page {page} of {totalPages}
            </span>
            <Button
              variant="outline"
              size="sm"
              className="border-slate-800 bg-slate-900 hover:bg-slate-950 text-slate-300 h-8 font-mono"
              disabled={page >= totalPages || loading}
              onClick={() => setPage(page + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </Card>
    </div>
  )
}

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
      setRows([])
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
  const [mounted, setMounted] = useState(false)
  const [activeTab, setActiveTab] = useState<"preprocessed" | "queue" | "profitability">("preprocessed")

  useEffect(() => {
    setMounted(true)
  }, [])

  // Database States
  const [entries, setEntries] = useState<BatchEntry[]>([])
  const [aggregations, setAggregations] = useState<Aggregations | null>(null)
  const [loading, setLoading] = useState(true)
  const [totalCount, setTotalCount] = useState(0)

  // Filters & Pagination
  const [selectedTierFilter, setSelectedTierFilter] = useState<string | null>(null)
  const [selectedStatusFilter, setSelectedStatusFilter] = useState<string | null>(null)
  const [selectedPoolFilter, setSelectedPoolFilter] = useState<string | null>(null)
  const [limit, setLimit] = useState(50)
  const [offset, setOffset] = useState(0)
  const [searchTerm, setSearchTerm] = useState("")

  // Table Sort States
  const [sortField, setSortField] = useState<keyof BatchEntry>("id")
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc")

  // Selected Detail Item
  const [selectedItem, setSelectedItem] = useState<BatchEntry | null>(null)

  // Diagnostics Telemetry States
  const [diagnostics, setDiagnostics] = useState<SystemDiagnostics | null>(null)
  const [concurrencyTelemetry, setConcurrencyTelemetry] = useState({
    current_limit: 1000,
    active_slots: 0,
    waiting_requests: 0,
    itl_moving_average: 20.0,
    ttft_moving_average: 50.0
  })
  
  // Throughput States
  const sessionStartTime = useRef<number>(Date.now())
  const initialCompletedCount = useRef<number | null>(null)
  const [throughput, setThroughput] = useState(0.0)

  // Console Logs
  const [consoleLogs, setConsoleLogs] = useState<{ id: string; text: string; type: "info" | "warn" | "error" }[]>([])

  // Action Spinners & Config
  const [isIgniting, setIsIgniting] = useState<string | null>(null)
  const [isRequeuing, setIsRequeuing] = useState<number | null>(null)
  const [activeDispatches, setActiveDispatches] = useState<string[]>([])
  const [maxTokens, setMaxTokens] = useState<number>(1024)
  const [localMaxTokens, setLocalMaxTokens] = useState<number>(1024)
  const [concurrencySlots, setConcurrencySlots] = useState<number>(48)
  const [localConcurrencySlots, setLocalConcurrencySlots] = useState<number>(48)
  const [selectedModel, setSelectedModel] = useState<string>("Kbenkhaled/Qwen3.5-9B-NVFP4")
  const [availableModels, setAvailableModels] = useState<string[]>(["Kbenkhaled/Qwen3.5-9B-NVFP4"])
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null)

  useEffect(() => {
    setLocalMaxTokens(maxTokens)
  }, [maxTokens])

  useEffect(() => {
    setLocalConcurrencySlots(concurrencySlots)
  }, [concurrencySlots])

  const [selectedRequestIds, setSelectedRequestIds] = useState<number[]>([])
  const [isCompiling, setIsCompiling] = useState(false)
  const [isCalculatingTokens, setIsCalculatingTokens] = useState(false)
  const [promptConfig, setPromptConfig] = useState<PromptConfig | null>(null)
  const [promptConfigExpanded, setPromptConfigExpanded] = useState(false)
  const [isSavingPromptConfig, setIsSavingPromptConfig] = useState(false)
  const [isExecutingSelected, setIsExecutingSelected] = useState(false)
  const [isSettingPendingSelected, setIsSettingPendingSelected] = useState(false)
  const [isResettingStatus, setIsResettingStatus] = useState(false)

  // Log Message Helper
  const addConsoleLog = (text: string, type: "info" | "warn" | "error" = "info") => {
    const timestamp = new Date().toLocaleTimeString()
    setConsoleLogs((prev) => [
      ...prev.slice(-49),
      { id: `${Date.now()}-${Math.random()}`, text: `[${timestamp}] ${text}`, type }
    ])
  }

  // 1. Fetch Batch Entries and Queue Aggregations
  const fetchBatchWorkspace = useCallback(async (showLoading = false) => {
    if (showLoading) setLoading(true)
    try {
      const params = new URLSearchParams()
      if (selectedTierFilter) params.append("tier", selectedTierFilter)
      if (selectedStatusFilter) params.append("status", selectedStatusFilter)
      if (selectedPoolFilter) params.append("source_pool", selectedPoolFilter)
      params.append("limit", limit.toString())
      params.append("offset", offset.toString())

      const response = await fetch(`${API_URL}/ingestion/batch-workspace?${params.toString()}`)
      if (response.ok) {
        const data = await response.json()
        setEntries(data.entries || data.queue || [])
        setTotalCount(data.total || (data.queue ? data.queue.length : 0))
        setAggregations(data.aggregations || null)
        setActiveDispatches(data.active_dispatches || [])

        const getCompletedCount = (overall: any) => {
          if (!overall) return 0
          return (overall.total || 0) - (overall.pending || 0) - (overall.running || 0)
        }
        if (data.aggregations?.overall && initialCompletedCount.current === null) {
          initialCompletedCount.current = getCompletedCount(data.aggregations.overall)
        }
        if (data.aggregations?.overall) {
          const completedNow = getCompletedCount(data.aggregations.overall)
          const elapsedSecs = (Date.now() - sessionStartTime.current) / 1000
          const deltaCompleted = Math.max(0, completedNow - (initialCompletedCount.current ?? completedNow))
          setThroughput(elapsedSecs > 1.0 ? deltaCompleted / elapsedSecs : 0.0)
        }
      } else {
        addConsoleLog(`Failed to fetch workspace queue data: ${response.statusText}`, "error")
      }
    } catch (error) {
      addConsoleLog(`Error requesting queue workspace details: ${error}`, "error")
    } finally {
      setLoading(false)
    }
  }, [selectedTierFilter, selectedStatusFilter, selectedPoolFilter, limit, offset])

  // 2. Fetch Performance Diagnostics (Poller)
  const fetchDiagnostics = async () => {
    try {
      const response = await fetch(`${API_URL}/system/diagnostics`)
      if (response.ok) {
        const data = await response.json()
        setDiagnostics(data)
      }
    } catch (error) {
      console.error("Error fetching diagnostics:", error)
    }
  }

  useEffect(() => {
    setSelectedRequestIds([])
    fetchBatchWorkspace(true)
  }, [selectedTierFilter, selectedStatusFilter, selectedPoolFilter, limit, offset])

  useEffect(() => {
    fetchDiagnostics()
    const diagInterval = setInterval(fetchDiagnostics, 4000)
    const dbInterval = setInterval(() => fetchBatchWorkspace(false), 6000)
    return () => {
      clearInterval(diagInterval)
      clearInterval(dbInterval)
    }
  }, [fetchBatchWorkspace])

  useEffect(() => {
    fetchPromptConfig()
  }, [])

  // 3. SSE Telemetry Stream Listener
  useEffect(() => {
    let eventSource: EventSource | null = null
    let reconnectTimeout: NodeJS.Timeout | null = null

    const connectSSE = () => {
      if (eventSource) {
        eventSource.close()
      }

      eventSource = new EventSource(`${API_URL}/ingestion/stream`)
      
      eventSource.onopen = () => {
        addConsoleLog("Inference telemetry stream connection established", "info")
      }

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data)
          if (data.type === "concurrency_update") {
            setConcurrencyTelemetry({
              current_limit: data.current_limit || 1000,
              active_slots: data.active_slots || 0,
              waiting_requests: data.waiting_requests || 0,
              itl_moving_average: data.itl_moving_average || 20.0,
              ttft_moving_average: data.ttft_moving_average || 50.0
            })
          } else if (data.type === "ping") {
            // Heartbeat
          } else {
            addConsoleLog(data.message || JSON.stringify(data), "info")
          }
        } catch (e) {
          console.error("SSE parse error", e)
        }
      }

      eventSource.onerror = () => {
        addConsoleLog("Inference stream connection lost. Attempting auto-recovery...", "warn")
        if (eventSource) {
          eventSource.close()
          eventSource = null
        }
        reconnectTimeout = setTimeout(connectSSE, 4000)
      }
    }

    connectSSE()

    return () => {
      if (eventSource) {
        eventSource.close()
      }
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout)
      }
    }
  }, [])

  // Sync selectedItem details when entries update
  useEffect(() => {
    if (selectedItem) {
      const updated = entries.find((e) => e.id === selectedItem.id)
      if (updated) {
        if (
          updated.dispatch_status !== selectedItem.dispatch_status ||
          updated.error_log !== selectedItem.error_log ||
          updated.response_payload !== selectedItem.response_payload ||
          updated.estimated_tokens !== selectedItem.estimated_tokens ||
          updated.token_bucket_tier !== selectedItem.token_bucket_tier
        ) {
          setSelectedItem(updated)
        }
      }
    }
  }, [entries, selectedItem])

  // 4. One-Click Trigger Dispatch Tasks
  const handleIgniteTier = async (bucket: string) => {
    setIsIgniting(bucket)
    addConsoleLog(`Initiating dispatch batch queue target: '${bucket}'`, "info")
    try {
      const response = await fetch(`${API_URL}/ingestion/dispatch?bucket=${bucket}&max_tokens=${maxTokens}`, {
        method: "POST"
      })
      if (response.ok) {
        addConsoleLog(`Ignite trigger successfully registered for: ${bucket}`, "info")
        setTimeout(() => fetchBatchWorkspace(false), 1000)
      } else {
        const errorText = await response.text()
        addConsoleLog(`Ignite command failed: ${errorText}`, "error")
      }
    } catch (error) {
      addConsoleLog(`Ignite trigger exception: ${error}`, "error")
    } finally {
      setIsIgniting(null)
    }
  }

  // 5. Stop Active Dispatch Pipeline
  const handleStopDispatch = async (bucket: string) => {
    addConsoleLog(`Requesting stop command for bucket: '${bucket}'`, "warn")
    try {
      const response = await fetch(`${API_URL}/ingestion/stop?bucket=${bucket}`, {
        method: "POST"
      })
      if (response.ok) {
        addConsoleLog(`Successfully stopped dispatching bucket: '${bucket}'`, "info")
        fetchBatchWorkspace(false)
      } else {
        const errorText = await response.text()
        addConsoleLog(`Stop command failed: ${errorText}`, "error")
      }
    } catch (error) {
      addConsoleLog(`Exception stopping batch: ${error}`, "error")
    }
  }

  // 6. Global Stop Command
  const handleStopAll = async () => {
    addConsoleLog("Sending Global STOP Command to all active batch pipelines...", "error")
    try {
      const response = await fetch(`${API_URL}/ingestion/stop`, {
        method: "POST"
      })
      if (response.ok) {
        addConsoleLog("Successfully stopped all running pipelines", "info")
        fetchBatchWorkspace(false)
      } else {
        const errorText = await response.text()
        addConsoleLog(`Global stop command failed: ${errorText}`, "error")
      }
    } catch (error) {
      addConsoleLog(`Exception during global stop: ${error}`, "error")
    }
  }

  // 7. Surgical Re-Queue Action Trigger
  const handleRequeueItem = async (itemId: number) => {
    setIsRequeuing(itemId)
    addConsoleLog(`Surgically re-queueing request ID ${itemId}...`, "info")
    try {
      const response = await fetch(`${API_URL}/ingestion/requeue/${itemId}?max_tokens=${maxTokens}`, {
        method: "POST"
      })
      if (response.ok) {
        addConsoleLog(`Request ID ${itemId} successfully re-queued to PENDING status`, "info")
        if (selectedItem && selectedItem.id === itemId) {
          setSelectedItem(prev => prev ? { ...prev, dispatch_status: "PENDING" } : null)
        }
        fetchBatchWorkspace(false)
      } else {
        addConsoleLog(`Failed to requeue request ID ${itemId}`, "error")
      }
    } catch (error) {
      addConsoleLog(`Re-queue exception: ${error}`, "error")
    } finally {
      setIsRequeuing(null)
    }
  }

  // 8. Export Selected Requests as JSON
  const handleExportSelected = () => {
    if (selectedRequestIds.length === 0) return
    const selectedData = entries.filter(e => selectedRequestIds.includes(e.id))
    const blob = new Blob([JSON.stringify(selectedData, null, 2)], { type: "application/json" })
    const url = URL.createObjectURL(blob)
    const a = document.createElement("a")
    a.href = url
    a.download = `exported_requests_${Date.now()}.json`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    addConsoleLog(`Successfully exported ${selectedRequestIds.length} requests to JSON file`, "info")
  }

  const handleExportSimplified = async () => {
    if (selectedRequestIds.length === 0) return
    try {
      const response = await fetch(`${API_URL}/ingestion/export-simplified`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: selectedRequestIds })
      })
      if (!response.ok) {
        throw new Error(`Export failed: ${response.statusText}`)
      }
      const data = await response.json()
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" })
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `simplified_export_${Date.now()}.json`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
      addConsoleLog(`Successfully exported ${selectedRequestIds.length} requests in simplified format`, "info")
    } catch (err: any) {
      addConsoleLog(`Failed to export simplified: ${err.message || err}`, "error")
    }
  }

  // 9. Compile Staging Registry
  const handleCompileRegistry = async () => {
    setIsCompiling(true)
    addConsoleLog("Initiating compilation of all staged records into the registry...", "info")
    try {
      const response = await fetch(`${API_URL}/ingestion/compile`, {
        method: "POST"
      })
      if (response.ok) {
        addConsoleLog("Compilation started in the background. Reloading queue state...", "info")
        setTimeout(() => {
          fetchBatchWorkspace(false)
          setIsCompiling(false)
        }, 3000)
      } else {
        const err = await response.text()
        addConsoleLog(`Compilation trigger failed: ${err}`, "error")
        setIsCompiling(false)
      }
    } catch (e) {
      addConsoleLog(`Exception during compilation trigger: ${e}`, "error")
      setIsCompiling(false)
    }
  }

  // 10. Calculate Real Tokens via vLLM Endpoint
  const handleCalculateRealTokens = async (ids?: number[]) => {
    setIsCalculatingTokens(true)
    const targetText = ids && ids.length > 0 ? `${ids.length} selected request(s)` : "all registry records"
    addConsoleLog(`Initiating exact token count calculation via vLLM /tokenize endpoint for ${targetText}...`, "info")
    try {
      const response = await fetch(`${API_URL}/ingestion/calculate-tokens`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: ids || null })
      })
      if (response.ok) {
        const data = await response.json()
        addConsoleLog(`Token calculation completed successfully. Updated count: ${data.updated_count} records. Re-fetching queue state...`, "info")
        fetchBatchWorkspace(false)
      } else {
        const err = await response.text()
        addConsoleLog(`Token calculation trigger failed: ${err}`, "error")
      }
    } catch (e) {
      addConsoleLog(`Exception during token calculation: ${e}`, "error")
    } finally {
      setIsCalculatingTokens(false)
    }
  }

  // 11. Fetch Prompt Configuration
  const fetchPromptConfig = async () => {
    try {
      const response = await fetch(`${API_URL}/ingestion/prompt-config`)
      if (response.ok) {
        const data = await response.json()
        setPromptConfig(data)
        if (data.max_tokens) setMaxTokens(data.max_tokens)
        if (data.concurrency_slots) setConcurrencySlots(data.concurrency_slots)
        if (data.selected_model) setSelectedModel(data.selected_model)
        if (data.available_models) setAvailableModels(data.available_models)
      }
    } catch (e) {
      addConsoleLog(`Failed to load prompt configuration: ${e}`, "error")
    }
  }

  const handleUpdateSelectedModel = async (val: string) => {
    setSelectedModel(val)
    if (promptConfig) {
      setPromptConfig(prev => prev ? { ...prev, selected_model: val } : null)
    }
    try {
      addConsoleLog(`Saving selected active model target: ${val}...`, "info")
      const response = await fetch(`${API_URL}/ingestion/prompt-config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ selected_model: val })
      })
      if (response.ok) {
        addConsoleLog(`Active model target saved successfully: ${val}`, "info")
      } else {
        addConsoleLog(`Failed to save active model limit`, "error")
      }
    } catch (e) {
      console.error("Failed to auto-save selected_model:", e)
    }
  }

  const handleUpdateMaxTokens = async (val: number) => {
    setMaxTokens(val)
    if (promptConfig) {
      setPromptConfig(prev => prev ? { ...prev, max_tokens: val } : null)
    }
    try {
      addConsoleLog(`Re-calculating token buckets and context window tiers for all registry requests...`, "info")
      const response = await fetch(`${API_URL}/ingestion/prompt-config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ max_tokens: val })
      })
      if (response.ok) {
        addConsoleLog(`Max completion tokens limit saved: ${val} tokens. Token buckets reorganized successfully.`, "info")
        fetchBatchWorkspace(false)
      } else {
        addConsoleLog(`Failed to save max tokens limit`, "error")
      }
    } catch (e) {
      console.error("Failed to auto-save max_tokens:", e)
    }
  }

  const triggerTokensSave = (val: number) => {
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }
    handleUpdateMaxTokens(val)
  }

  const handleInputChange = (val: number) => {
    setLocalMaxTokens(val)
    if (debounceTimerRef.current) {
      clearTimeout(debounceTimerRef.current)
    }
    debounceTimerRef.current = setTimeout(() => {
      triggerTokensSave(val)
    }, 3000)
  }

  const handleUpdateConcurrencySlots = async (val: number) => {
    setConcurrencySlots(val)
    if (promptConfig) {
      setPromptConfig(prev => prev ? { ...prev, concurrency_slots: val } : null)
    }
    try {
      addConsoleLog(`Saving concurrency slots limit: ${val}...`, "info")
      const response = await fetch(`${API_URL}/ingestion/prompt-config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ concurrency_slots: val })
      })
      if (response.ok) {
        addConsoleLog(`Concurrency slots limit saved successfully: ${val}`, "info")
      } else {
        addConsoleLog(`Failed to save concurrency slots limit`, "error")
      }
    } catch (e) {
      console.error("Failed to auto-save concurrency_slots:", e)
    }
  }

  const handleResetQueueStatus = async (status: string) => {
    setIsResettingStatus(true)
    addConsoleLog(`Initiating registry queue reset for status group: '${status}'...`, "info")
    try {
      const response = await fetch(`${API_URL}/ingestion/reset-status?status=${status}`, {
        method: "POST"
      })
      if (response.ok) {
        const data = await response.json()
        addConsoleLog(`Queue reset completed successfully. Reset ${data.reset_count} requests back to PENDING. Re-fetching queue state...`, "info")
        fetchBatchWorkspace(false)
      } else {
        const err = await response.text()
        addConsoleLog(`Queue reset failed: ${err}`, "error")
      }
    } catch (e) {
      addConsoleLog(`Exception during queue reset: ${e}`, "error")
    } finally {
      setIsResettingStatus(false)
    }
  }

  const handleSavePromptConfig = async () => {
    if (!promptConfig) return
    setIsSavingPromptConfig(true)
    try {
      const response = await fetch(`${API_URL}/ingestion/prompt-config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(promptConfig)
      })
      if (response.ok) {
        addConsoleLog("Pipeline prompt configuration saved successfully. Recompile registry to apply changes.", "info")
      } else {
        const err = await response.text()
        addConsoleLog(`Failed to save prompt config: ${err}`, "error")
      }
    } catch (e) {
      addConsoleLog(`Exception saving prompt config: ${e}`, "error")
    } finally {
      setIsSavingPromptConfig(false)
    }
  }

  const handleSaveItemPromptsAndRequeue = async (itemId: number, systemPrompt: string, userPrompt: string, refusalPrompt: string) => {
    addConsoleLog(`Saving edited prompts for request ID ${itemId}...`, "info")
    try {
      const response = await fetch(`${API_URL}/ingestion/batch/${itemId}/prompts`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          system_prompt: systemPrompt,
          user_prompt: userPrompt,
          refusal_prompt: refusalPrompt
        })
      })
      if (response.ok) {
        addConsoleLog(`Prompts saved for ID ${itemId}. Re-queuing...`, "info")
        handleRequeueItem(itemId)
      } else {
        addConsoleLog(`Failed to save prompts for ID ${itemId}`, "error")
      }
    } catch (e) {
      addConsoleLog(`Exception saving item prompts: ${e}`, "error")
    }
  }

  const handleExecuteSelected = async () => {
    if (selectedRequestIds.length === 0) return
    setIsExecutingSelected(true)
    addConsoleLog(`Executing ${selectedRequestIds.length} selected requests...`, "info")
    try {
      const response = await fetch(`${API_URL}/ingestion/requeue-batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ids: selectedRequestIds,
          max_tokens: maxTokens
        })
      })
      if (response.ok) {
        addConsoleLog(`Successfully executed ${selectedRequestIds.length} requests in the background.`, "info")
        setSelectedRequestIds([])
        fetchBatchWorkspace(false)
      } else {
        const err = await response.text()
        addConsoleLog(`Execution failed: ${err}`, "error")
      }
    } catch (e) {
      addConsoleLog(`Exception executing selected: ${e}`, "error")
    } finally {
      setIsExecutingSelected(false)
    }
  }

  const handleSetPendingSelected = async () => {
    if (selectedRequestIds.length === 0) return
    setIsSettingPendingSelected(true)
    addConsoleLog(`Setting ${selectedRequestIds.length} selected requests to PENDING...`, "info")
    try {
      const response = await fetch(`${API_URL}/ingestion/set-pending-batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ids: selectedRequestIds
        })
      })
      if (response.ok) {
        addConsoleLog(`Successfully set ${selectedRequestIds.length} requests to PENDING.`, "info")
        setSelectedRequestIds([])
        fetchBatchWorkspace(false)
      } else {
        const err = await response.text()
        addConsoleLog(`Setting pending failed: ${err}`, "error")
      }
    } catch (e) {
      addConsoleLog(`Exception setting pending selected: ${e}`, "error")
    } finally {
      setIsSettingPendingSelected(false)
    }
  }

  useEffect(() => {
    if (promptConfigExpanded && !promptConfig) {
      fetchPromptConfig()
    }
  }, [promptConfigExpanded])

  const handleSort = (field: keyof BatchEntry) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc")
    } else {
      setSortField(field)
      setSortDirection("asc")
    }
  }

  const filteredAndSortedEntries = useMemo(() => {
    let result = [...entries]
    if (searchTerm.trim()) {
      const keywords = searchTerm.trim().split(/\s+/)
      result = result.filter((entry) => {
        return keywords.every((kw) => {
          try {
            const regex = new RegExp(kw, "i")
            return (
              regex.test(entry.id.toString()) ||
              regex.test(entry.source_pool || "") ||
              regex.test(entry.source_identifier || "") ||
              regex.test(entry.request_type || "") ||
              regex.test(entry.token_bucket_tier || "") ||
              regex.test(entry.dispatch_status || "") ||
              (entry.user_prompt_payload && regex.test(entry.user_prompt_payload))
            )
          } catch (e) {
            const loweredKw = kw.toLowerCase()
            return (
              entry.id.toString().includes(loweredKw) ||
              (entry.source_pool || "").toLowerCase().includes(loweredKw) ||
              (entry.source_identifier || "").toLowerCase().includes(loweredKw) ||
              (entry.request_type || "").toLowerCase().includes(loweredKw) ||
              (entry.token_bucket_tier || "").toLowerCase().includes(loweredKw) ||
              (entry.dispatch_status || "").toLowerCase().includes(loweredKw)
            )
          }
        })
      })
    }

    result.sort((a, b) => {
      let aVal = a[sortField]
      let bVal = b[sortField]

      if (aVal === null || aVal === undefined) return sortDirection === "asc" ? -1 : 1
      if (bVal === null || bVal === undefined) return sortDirection === "asc" ? 1 : -1

      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDirection === "asc" ? aVal - bVal : bVal - aVal
      }

      const strA = String(aVal).toLowerCase()
      const strB = String(bVal).toLowerCase()
      if (strA < strB) return sortDirection === "asc" ? -1 : 1
      if (strA > strB) return sortDirection === "asc" ? 1 : -1
      return 0
    })

    return result
  }, [entries, searchTerm, sortField, sortDirection])

  const renderStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case "RUNNING":
        return (
          <Badge 
            className="bg-sky-500/10 text-sky-400 border border-sky-500/20 font-mono rounded px-2.5 py-0.5 hover:bg-sky-500/20 animate-pulse flex items-center gap-1.5"
          >
            <RefreshCw className="w-3 h-3 animate-spin shrink-0 text-sky-400" />
            RUNNING
          </Badge>
        )
      case "DISPATCHED":
        return (
          <Badge 
            className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 shadow-[0_0_8px_rgba(16,185,129,0.2)] rounded px-2.5 py-0.5 hover:bg-emerald-500/20"
          >
            DISPATCHED
          </Badge>
        )
      case "FAILED":
        return (
          <Badge 
            className="bg-rose-500/10 text-rose-400 border border-rose-500/20 font-mono rounded px-2.5 py-0.5 hover:bg-rose-500/20"
          >
            FAILED
          </Badge>
        )
      case "INVALID":
        return (
          <Badge 
            className="bg-orange-500/10 text-orange-400 border border-orange-500/20 font-mono rounded px-2.5 py-0.5 hover:bg-orange-500/20"
          >
            <ShieldAlert className="w-3 h-3 mr-1 inline" />
            INVALID
          </Badge>
        )
      case "INVALID_INPUT":
        return (
          <Badge 
            className="bg-orange-500/10 text-orange-400 border border-orange-500/20 font-mono rounded px-2.5 py-0.5 hover:bg-orange-500/20"
          >
            <ShieldAlert className="w-3 h-3 mr-1 inline" />
            INVALID INPUT
          </Badge>
        )
      case "PROSE_REFUSAL":
        return (
          <Badge 
            className="bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 font-mono rounded px-2.5 py-0.5 hover:bg-yellow-500/20"
          >
            <AlertTriangle className="w-3 h-3 mr-1 inline" />
            PROSE REFUSAL
          </Badge>
        )
      case "MALFORMED_JSON":
        return (
          <Badge 
            className="bg-red-500/10 text-red-400 border border-red-500/20 font-mono rounded px-2.5 py-0.5 hover:bg-red-500/20"
          >
            <AlertTriangle className="w-3 h-3 mr-1 inline" />
            MALFORMED JSON
          </Badge>
        )
      case "SKIPPED_METADATA":
        return (
          <Badge 
            className="bg-slate-500/10 text-slate-400 border border-slate-500/20 font-mono rounded px-2.5 py-0.5 hover:bg-slate-500/20"
          >
            SKIPPED METADATA
          </Badge>
        )
      case "NO CONTENT":
      case "NO_CONTENT":
        return (
          <Badge 
            className="bg-slate-500/10 text-slate-400 border border-slate-500/20 font-mono rounded px-2.5 py-0.5 hover:bg-slate-500/20"
          >
            NO CONTENT
          </Badge>
        )
      case "PENDING":
      default:
        return (
          <Badge 
            className="bg-amber-500/10 text-amber-500 border border-amber-500/20 animate-pulse rounded px-2.5 py-0.5 hover:bg-amber-500/20"
          >
            PENDING
          </Badge>
        )
    }
  }

  const getDispatchedPercentage = (tier: string) => {
    if (!aggregations || !aggregations[tier]) return 0
    const stats = aggregations[tier]
    if (stats.total === 0) return 0
    return Math.round((stats.dispatched / stats.total) * 100)
  }

  if (!mounted) {
    return (
      <div className="flex items-center justify-center min-h-[400px] text-slate-500 font-mono text-xs">
        <RefreshCw className="w-5 h-5 animate-spin mr-2 text-sky-400" />
        Loading Control Room Workspace...
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-6 text-slate-100 pb-12">
      {/* Header Bar with View Switching Tabs */}
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
            Unified Pre-Flight Batch & Profitability Control Room
          </h1>
          <p className="text-slate-400 text-sm mt-1">
            Segment, calibrate, and hot-trigger batch jobs over {totalCount} records or analyze target profitability scoring matrices.
          </p>
        </div>
        
        <div className="flex flex-wrap items-center gap-3">
          <Tabs value={activeTab} onValueChange={(v) => setActiveTab(v as any)} className="w-full md:w-auto">
            <TabsList className="bg-slate-950 border border-slate-800 p-1">
              <TabsTrigger value="preprocessed" className="text-xs font-mono data-[state=active]:bg-slate-800 text-sky-400">
                <Layers className="w-3.5 h-3.5 mr-1.5 text-sky-400" />
                Pre-Processed Queue Inspector
              </TabsTrigger>
              <TabsTrigger value="queue" className="text-xs font-mono data-[state=active]:bg-slate-800">
                <Database className="w-3.5 h-3.5 mr-1.5 text-slate-400" />
                Preflight Batch Queue
              </TabsTrigger>
              <TabsTrigger value="profitability" className="text-xs font-mono data-[state=active]:bg-slate-800 text-emerald-400">
                <TrendingUp className="w-3.5 h-3.5 mr-1.5 text-emerald-400" />
                Target Profitability Matrix
              </TabsTrigger>
            </TabsList>
          </Tabs>

          {activeTab === "queue" && (
            <>
              {activeDispatches.length > 0 && (
                <Button
                  variant="destructive"
                  size="sm"
                  className="bg-rose-900/60 hover:bg-rose-900 text-rose-100 border border-rose-800"
                  onClick={handleStopAll}
                >
                  <ZapOff className="w-4 h-4 mr-2" />
                  Stop All Pipelines
                </Button>
              )}
              <Button
                variant="outline"
                size="sm"
                className="border-slate-800 hover:bg-slate-900 bg-slate-950 text-slate-300"
                disabled={isCompiling}
                onClick={handleCompileRegistry}
              >
                {isCompiling ? (
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Terminal className="w-4 h-4 mr-2 text-indigo-400" />
                )}
                Compile Staging Registry
              </Button>
              <Button
                variant="outline"
                size="sm"
                className="border-slate-800 hover:bg-slate-900 bg-slate-950 text-slate-300"
                disabled={isCalculatingTokens}
                onClick={() => handleCalculateRealTokens()}
              >
                {isCalculatingTokens ? (
                  <RefreshCw className="w-4 h-4 mr-2 animate-spin" />
                ) : (
                  <Cpu className="w-4 h-4 mr-2 text-cyan-400" />
                )}
                Calculate Real Tokens
              </Button>
              <Button 
                variant="outline" 
                size="sm" 
                className="border-slate-800 hover:bg-slate-900 bg-slate-950 text-slate-300"
                onClick={() => fetchBatchWorkspace(true)}
              >
                <RefreshCw className="w-4 h-4 mr-2" />
                Refresh Queue State
              </Button>
            </>
          )}
        </div>
      </div>

      {activeTab === "preprocessed" ? (
        <PreProcessedQueueInspectorView addConsoleLog={addConsoleLog} />
      ) : activeTab === "profitability" ? (
        <TargetProfitabilityMatrixView />
      ) : (
        <div className="flex flex-col gap-6">
          {/* ── PANEL 1: LIVE TOKEN TIER MATRIX PANEL ───────────────────────────── */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-4">
            {[
              { key: "less_than_1k", label: "T < 1k Tokens", color: "from-emerald-500/20 to-teal-500/10", border: "border-emerald-500/20" },
              { key: "1k_to_2k", label: "1k <= T < 2k Tokens", color: "from-teal-500/20 to-cyan-500/10", border: "border-teal-500/20" },
              { key: "2k_to_4k", label: "2k <= T < 4k Tokens", color: "from-cyan-500/20 to-sky-500/10", border: "border-cyan-500/20" },
              { key: "4k_to_8k", label: "4k <= T < 8k Tokens", color: "from-sky-500/20 to-indigo-500/10", border: "border-sky-500/20" },
              { key: "8k_to_16k", label: "8k <= T < 16k Tokens", color: "from-indigo-500/20 to-purple-500/10", border: "border-indigo-500/20" },
              { key: "16k_to_32k", label: "16k <= T < 32k Tokens", color: "from-purple-500/20 to-fuchsia-500/10", border: "border-purple-500/20" },
              { key: "32k_to_64k", label: "32k <= T < 64k Tokens", color: "from-fuchsia-500/20 to-rose-500/10", border: "border-fuchsia-500/20" },
              { key: "64k_to_128k", label: "64k <= T < 128k Tokens", color: "from-rose-500/20 to-orange-500/10", border: "border-rose-500/20" },
              { key: "128k_to_256k", label: "128k <= T < 256k Tokens", color: "from-orange-500/20 to-amber-500/10", border: "border-orange-500/20" },
              { key: "greater_than_256k", label: "T >= 256k Tokens", color: "from-amber-500/20 to-yellow-500/10", border: "border-amber-500/20" }
            ].map((card) => {
              const stats = aggregations?.[card.key]
              const pct = getDispatchedPercentage(card.key)
              const isFilterActive = selectedTierFilter === card.key

              return (
                <Card 
                  key={card.key}
                  className={`bg-slate-950/70 border ${card.border} backdrop-blur-xs relative overflow-hidden transition-all duration-300 cursor-pointer hover:border-slate-500 ${isFilterActive ? "ring-2 ring-sky-500" : ""}`}
                  onClick={() => setSelectedTierFilter(isFilterActive ? null : card.key)}
                >
                  <div className={`absolute top-0 inset-x-0 h-1 bg-gradient-to-r ${card.color}`} />
                  <CardContent className="pt-5 pb-4">
                    <div className="flex items-center justify-between mb-2">
                      <span className="text-slate-400 text-xs font-semibold uppercase tracking-wider">{card.label}</span>
                      {isFilterActive && <span className="text-[10px] bg-sky-500/20 text-sky-400 border border-sky-500/30 rounded px-1.5 font-bold uppercase">Filtered</span>}
                    </div>
                    
                    <div className="flex items-baseline justify-between mb-3">
                      <span className="text-3xl font-bold text-white tracking-tight">{stats?.total ?? 0}</span>
                      <span className="text-slate-400 text-xs font-mono">
                        {stats?.dispatched ?? 0} / {stats?.total ?? 0} Dispatched
                      </span>
                    </div>

                    <div className="flex flex-col gap-1.5">
                      <div className="flex justify-between items-center text-[10px] text-slate-500 font-mono">
                        <span>PROGRESS RATIO</span>
                        <span>{pct}%</span>
                      </div>
                      <Progress value={pct} className="h-1.5" />
                    </div>

                    <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 mt-4 pt-3 border-t border-slate-900 text-[10px] font-mono text-slate-400">
                      <div className="flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
                        <span>{stats?.pending ?? 0} Pnd</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 shadow-[0_0_4px_rgba(16,185,129,0.5)]" />
                        <span>{stats?.dispatched ?? 0} Disp</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-rose-500" />
                        <span>{stats?.failed ?? 0} Fail</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />
                        <span>{stats?.invalid_input ?? 0} InvInp</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-yellow-500" />
                        <span>{stats?.prose_refusal ?? 0} Prose</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-red-500" />
                        <span>{stats?.malformed_json ?? 0} MalJSON</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-400" />
                        <span>{stats?.skipped_metadata ?? 0} Skip</span>
                      </div>
                      <div className="flex items-center gap-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-slate-500" />
                        <span>{stats?.["no content"] ?? 0} No Cnt</span>
                      </div>
                    </div>
                  </CardContent>
                </Card>
              )
            })}
          </div>

          {/* Grid: Diagnostics Telemetry and Action Triggers */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* ── PANEL 2: HARDWARE SATURATION & TELEMETRY MONITOR ─────────────── */}
            <Card className="lg:col-span-2 bg-slate-950/70 border border-slate-800/80 backdrop-blur-xs flex flex-col justify-between">
              <CardHeader className="border-b border-slate-900 pb-3">
                <div className="flex items-center justify-between">
                  <CardTitle className="text-sm font-semibold tracking-wider text-slate-300 uppercase flex items-center gap-2">
                    <Activity className="w-4 h-4 text-emerald-400" />
                    NVIDIA RTX 5090 cluster Autopilot Telemetry
                  </CardTitle>
                  <div className="flex items-center gap-1 text-[11px] text-slate-400 font-mono bg-slate-900/60 border border-slate-800/50 rounded px-2 py-0.5">
                    <Cpu className="w-3 h-3 text-sky-400" />
                    Inference Autopilot: ACTIVE
                  </div>
                </div>
              </CardHeader>
              <CardContent className="pt-5 flex-1 flex flex-col gap-6">
                
                {/* Live Numbers Grid */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                  <div className="bg-slate-900/40 p-3 rounded-lg border border-slate-800/50">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">CONCURRENCY SLOTS</span>
                    <span className="text-2xl font-mono font-bold text-white mt-1 block">
                      {concurrencyTelemetry.active_slots} / {concurrencyTelemetry.current_limit}
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono block mt-0.5">Auto Semaphore Limit</span>
                  </div>
                  <div className="bg-slate-900/40 p-3 rounded-lg border border-slate-800/50">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">RUN-TIME THROUGHPUT</span>
                    <span className="text-2xl font-mono font-bold text-emerald-400 mt-1 block">
                      {throughput.toFixed(2)} <span className="text-xs text-slate-400 font-normal">req/s</span>
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono block mt-0.5">Δ Req / Δ t</span>
                  </div>
                  <div className="bg-slate-900/40 p-3 rounded-lg border border-slate-800/50">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">INTER-TOKEN LATENCY (ITL)</span>
                    <span className="text-2xl font-mono font-bold text-sky-400 mt-1 block">
                      {concurrencyTelemetry.itl_moving_average.toFixed(1)} <span className="text-xs text-slate-400 font-normal">ms</span>
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono block mt-0.5">Moving Average Window</span>
                  </div>
                  <div className="bg-slate-900/40 p-3 rounded-lg border border-slate-800/50">
                    <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">TIME-TO-FIRST-TOKEN (TTFT)</span>
                    <span className="text-2xl font-mono font-bold text-indigo-400 mt-1 block">
                      {concurrencyTelemetry.ttft_moving_average.toFixed(1)} <span className="text-xs text-slate-400 font-normal">ms</span>
                    </span>
                    <span className="text-[10px] text-slate-500 font-mono block mt-0.5">Average Latency</span>
                  </div>
                </div>

                {/* Diagnostic system load */}
                <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono border-t border-slate-900 pt-5 text-slate-400">
                  <div className="flex justify-between md:flex-col md:gap-1 bg-slate-900/20 p-2.5 rounded border border-slate-900">
                    <span className="text-slate-500">HOST RYZEN CPU LOAD</span>
                    <span className="text-slate-200 font-bold">{diagnostics?.resources.cpu_percentage ?? 0.0}%</span>
                  </div>
                  <div className="flex justify-between md:flex-col md:gap-1 bg-slate-900/20 p-2.5 rounded border border-slate-900">
                    <span className="text-slate-500">BACKEND RAM ALLOCATION</span>
                    <span className="text-slate-200 font-bold">{diagnostics?.resources.backend_memory_mb ?? 0.0} MB</span>
                  </div>
                  <div className="flex justify-between md:flex-col md:gap-1 bg-slate-900/20 p-2.5 rounded border border-slate-900">
                    <span className="text-slate-500">SANDBOX CONTAINERS</span>
                    <span className="text-slate-200 font-bold">{diagnostics?.docker.active_sandbox_containers ?? 0} Active</span>
                  </div>
                </div>

                {/* Dynamic Console Logs */}
                <div className="flex-1 flex flex-col gap-2">
                  <div className="flex items-center justify-between text-xs text-slate-500 font-mono">
                    <span>OBSERVABILITY TELEMETRY LOG STREAM</span>
                    <span>Max Capacity: 50 Lines</span>
                  </div>
                  <div className="bg-black/85 border border-slate-900 rounded p-3 font-mono text-[10px] leading-relaxed h-[130px] overflow-y-auto flex flex-col gap-1 shadow-inner">
                    {consoleLogs.length === 0 ? (
                      <span className="text-slate-600 italic">Listening for streaming events...</span>
                    ) : (
                      consoleLogs.map((log) => {
                        let typeColor = "text-slate-400"
                        if (log.type === "warn") typeColor = "text-amber-400"
                        if (log.type === "error") typeColor = "text-rose-400"
                        return (
                          <div key={log.id} className={typeColor}>
                            {log.text}
                          </div>
                        )
                      })
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>

            {/* ── PANEL 3: ONE-CLICK "IGNITE TIER" TOOLBAR ────────────────────── */}
            <Card className="bg-slate-950/70 border border-slate-800/80 backdrop-blur-xs flex flex-col justify-between">
              <CardHeader className="border-b border-slate-900 pb-3">
                <CardTitle className="text-sm font-semibold tracking-wider text-slate-300 uppercase flex items-center gap-2">
                  <Zap className="w-4 h-4 text-amber-400" />
                  Ignite Action Control center
                </CardTitle>
              </CardHeader>
              <CardContent className="pt-5 flex-1 flex flex-col gap-4 justify-between">
                <p className="text-xs text-slate-400 leading-relaxed mb-1">
                  Selectively initiate dispatch pipelines directly to the GPU fuzzer server. 
                  The task scheduler executes concurrent threads matching model parameters.
                </p>

                <div className="grid grid-cols-2 gap-2.5">
                  {[
                    { bucket: "less_than_1k", label: "<1k Tier", shortLabel: "<1k" },
                    { bucket: "1k_to_2k", label: "1k-2k Tier", shortLabel: "1k-2k" },
                    { bucket: "2k_to_4k", label: "2k-4k Tier", shortLabel: "2k-4k" },
                    { bucket: "4k_to_8k", label: "4k-8k Tier", shortLabel: "4k-8k" },
                    { bucket: "8k_to_16k", label: "8k-16k Tier", shortLabel: "8k-16k" },
                    { bucket: "16k_to_32k", label: "16k-32k Tier", shortLabel: "16k-32k" },
                    { bucket: "32k_to_64k", label: "32k-64k Tier", shortLabel: "32k-64k" },
                    { bucket: "64k_to_128k", label: "64k-128k Tier", shortLabel: "64k-128k" },
                    { bucket: "128k_to_256k", label: "128k-256k Tier", shortLabel: "128k-256k" },
                    { bucket: "greater_than_256k", label: ">256k Tier", shortLabel: ">256k" }
                  ].map((act) => {
                    const isActive = activeDispatches.includes(act.bucket);
                    return (
                      <Button
                        key={act.bucket}
                        variant="outline"
                        size="sm"
                        className={`w-full text-xs font-mono justify-between border-slate-800/80 bg-slate-900/60 hover:text-white ${
                          isActive 
                            ? "border-rose-900/50 text-rose-300 hover:bg-rose-950/40" 
                            : "hover:bg-slate-950 text-slate-300"
                        }`}
                        disabled={isIgniting !== null}
                        onClick={() => isActive ? handleStopDispatch(act.bucket) : handleIgniteTier(act.bucket)}
                      >
                        <span className="flex items-center gap-1.5 min-w-0">
                          {isActive ? (
                            <ZapOff className="w-3.5 h-3.5 text-rose-500 shrink-0 animate-pulse" />
                          ) : (
                            <Play className="w-3.5 h-3.5 text-amber-500 fill-amber-500/20 shrink-0" />
                          )}
                          <span className="text-[11px] font-semibold">{isActive ? `Stop ${act.shortLabel}` : act.label}</span>
                        </span>
                        {isIgniting === act.bucket ? (
                          <RefreshCw className="w-3 h-3 animate-spin text-slate-400 shrink-0" />
                        ) : (
                          <Badge 
                            variant="secondary" 
                            className={`text-[9px] shrink-0 border bg-slate-950/80 px-1 py-0 ${
                              isActive 
                                ? "border-rose-800/40 text-rose-400" 
                                : "border-slate-800/50 text-slate-400"
                            }`}
                          >
                            {isActive ? "Active" : `${aggregations?.[act.bucket]?.pending ?? 0}`}
                          </Badge>
                        )}
                      </Button>
                    )
                  })}
                </div>

                <div className="flex flex-col gap-1.5 bg-slate-900/30 p-3 rounded-lg border border-slate-900 mt-2">
                  <span className="text-[10px] text-slate-500 font-mono uppercase tracking-wider block">ACTIVE MODEL TARGET</span>
                  <div className="mt-1">
                    <select
                      className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs font-mono text-sky-400 focus:outline-none focus:border-slate-700 w-full h-8 cursor-pointer"
                      value={selectedModel}
                      onChange={(e) => handleUpdateSelectedModel(e.target.value)}
                    >
                      {availableModels.map((model) => (
                        <option key={model} value={model}>
                          {model}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>

                <div className="flex flex-col gap-1.5 bg-slate-900/30 p-3 rounded-lg border border-slate-900 mt-2">
                  <span className="text-[10px] text-slate-500 font-mono uppercase tracking-wider block">MAX COMPLETION TOKENS</span>
                  <div className="flex items-center gap-2 mt-1">
                    <input
                      type="number"
                      min="1"
                      max="65536"
                      className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs font-mono text-sky-400 focus:outline-none focus:border-slate-700 w-28 h-8"
                      value={localMaxTokens}
                      onChange={(e) => handleInputChange(parseInt(e.target.value) || 1024)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          triggerTokensSave(localMaxTokens)
                        }
                      }}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 w-8 p-0 border-slate-800 bg-slate-900/60 hover:bg-slate-950 text-slate-300"
                      onClick={() => triggerTokensSave(localMaxTokens)}
                    >
                      <Save className="w-3.5 h-3.5" />
                    </Button>
                    <span className="text-[10px] text-slate-400 font-mono">tokens per request</span>
                  </div>
                </div>

                <div className="flex flex-col gap-1.5 bg-slate-900/30 p-3 rounded-lg border border-slate-900 mt-2">
                  <span className="text-[10px] text-slate-500 font-mono uppercase tracking-wider block">CONCURRENCY SLOTS</span>
                  <div className="flex items-center gap-2 mt-1">
                    <input
                      type="number"
                      min="1"
                      max="10000"
                      className="bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs font-mono text-sky-400 focus:outline-none focus:border-slate-700 w-28 h-8"
                      value={localConcurrencySlots}
                      onChange={(e) => setLocalConcurrencySlots(parseInt(e.target.value) || 48)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          handleUpdateConcurrencySlots(localConcurrencySlots)
                        }
                      }}
                    />
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 w-8 p-0 border-slate-800 bg-slate-900/60 hover:bg-slate-950 text-slate-300"
                      onClick={() => handleUpdateConcurrencySlots(localConcurrencySlots)}
                    >
                      <Save className="w-3.5 h-3.5" />
                    </Button>
                    <span className="text-[10px] text-slate-400 font-mono">concurrent slots</span>
                  </div>
                </div>

                <div className="flex flex-col gap-2 bg-slate-900/30 p-3 rounded-lg border border-slate-900 mt-2 font-mono">
                  <span className="text-[10px] text-slate-500 uppercase tracking-wider block">QUEUE MAINTENANCE RESETS</span>
                  <div className="grid grid-cols-2 gap-2 mt-1">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-[10px] border-rose-900/50 hover:bg-rose-950/30 text-rose-300 flex items-center justify-center py-0"
                      onClick={() => handleResetQueueStatus("failed")}
                      disabled={isResettingStatus}
                    >
                      Reset Failed
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-[10px] border-orange-900/50 hover:bg-orange-950/30 text-orange-300 flex items-center justify-center py-0"
                      onClick={() => handleResetQueueStatus("invalid")}
                      disabled={isResettingStatus}
                    >
                      Reset All Invalid
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-[10px] border-orange-900/30 hover:bg-orange-950/20 text-orange-400 flex items-center justify-center py-0"
                      onClick={() => handleResetQueueStatus("invalid_input")}
                      disabled={isResettingStatus}
                    >
                      Reset Invalid Input
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-[10px] border-yellow-900/50 hover:bg-yellow-950/30 text-yellow-300 flex items-center justify-center py-0"
                      onClick={() => handleResetQueueStatus("prose_refusal")}
                      disabled={isResettingStatus}
                    >
                      Reset Prose Refusal
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-[10px] border-red-900/50 hover:bg-red-950/30 text-red-300 flex items-center justify-center py-0"
                      onClick={() => handleResetQueueStatus("malformed_json")}
                      disabled={isResettingStatus}
                    >
                      Reset Malformed JSON
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-[10px] border-slate-700 hover:bg-slate-800 text-slate-400 flex items-center justify-center py-0"
                      onClick={() => handleResetQueueStatus("skipped_metadata")}
                      disabled={isResettingStatus}
                    >
                      Reset Skipped Meta
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-[10px] border-slate-800 hover:bg-slate-900/50 text-slate-300 flex items-center justify-center py-0"
                      onClick={() => handleResetQueueStatus("no_content")}
                      disabled={isResettingStatus}
                    >
                      Reset No Content
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 text-[10px] border-amber-900/50 hover:bg-amber-950/50 text-amber-400 flex items-center justify-center py-0"
                      onClick={() => handleResetQueueStatus("all_non_success")}
                      disabled={isResettingStatus}
                    >
                      Reset All Errors
                    </Button>
                  </div>
                </div>

                <div className="border-t border-slate-900 pt-4 mt-2">
                  <div className="flex flex-col gap-2">
                    <div className="flex justify-between items-center text-[10px] font-mono text-slate-500">
                      <span>QUEUE HARDWARE OVERRIDE</span>
                      <span className="text-rose-400">UNRESTRICTED CAPACITY</span>
                    </div>
                    <Button
                      variant="destructive"
                      size="sm"
                      className="w-full text-xs font-mono font-bold tracking-wider uppercase border border-rose-900/50 bg-gradient-to-r from-rose-950 to-red-900 hover:from-rose-900 hover:to-red-800 text-white flex items-center justify-center gap-2 shadow-[0_0_15px_rgba(239,68,68,0.15)]"
                      disabled={isIgniting !== null}
                      onClick={() => handleIgniteTier("all")}
                    >
                      <Maximize2 className="w-4 h-4 text-white" />
                      Saturate RTX 5090 Core
                    </Button>
                  </div>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* ── PANEL 3.5: PIPELINE PROMPT CONFIGURATION ──────────────────────── */}
          <Card className="bg-slate-950/70 border border-slate-800/80 backdrop-blur-xs overflow-hidden">
            <CardHeader 
              className="border-b border-slate-900 pb-3 cursor-pointer hover:bg-slate-900/20 transition-colors"
              onClick={() => setPromptConfigExpanded(!promptConfigExpanded)}
            >
              <div className="flex items-center justify-between">
                <CardTitle className="text-sm font-semibold tracking-wider text-slate-300 uppercase flex items-center gap-2">
                  <Settings2 className="w-4 h-4 text-indigo-400" />
                  Pipeline Prompt Configuration
                </CardTitle>
                <div className="flex items-center gap-2">
                  {promptConfigExpanded && promptConfig && (
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-[10px] font-mono border-indigo-800 hover:bg-indigo-950 bg-indigo-950/40 text-indigo-300 py-0 flex items-center"
                      disabled={isSavingPromptConfig}
                      onClick={(e) => { e.stopPropagation(); handleSavePromptConfig() }}
                    >
                      {isSavingPromptConfig ? (
                        <RefreshCw className="w-3 h-3 mr-1 animate-spin" />
                      ) : (
                        <Save className="w-3 h-3 mr-1" />
                      )}
                      Save Configuration
                    </Button>
                  )}
                  {promptConfigExpanded ? (
                    <ChevronDown className="w-4 h-4 text-slate-500" />
                  ) : (
                    <ChevronRight className="w-4 h-4 text-slate-500" />
                  )}
                </div>
              </div>
            </CardHeader>
            {promptConfigExpanded && (
              <CardContent className="pt-5">
                {!promptConfig ? (
                  <div className="flex items-center gap-2 text-sm text-slate-500 py-8 justify-center">
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    Loading prompt configuration...
                  </div>
                ) : (
                  <div className="flex flex-col gap-6">
                    <p className="text-xs text-slate-400 leading-relaxed">
                      Edit the system prompts and user prompt templates for each pipeline request type. 
                      Changes take effect on the next <span className="text-indigo-400 font-mono">Compile Staging Registry</span> execution.
                    </p>

                    {/* Structural Extraction Prompts */}
                    <div className="flex flex-col gap-3 bg-slate-900/30 p-4 rounded-lg border border-slate-900">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-emerald-400 font-mono uppercase tracking-wider font-bold">structural_extraction</span>
                        <span className="text-[10px] text-slate-600 font-mono">→ agent: {promptConfig.structural_extraction.agent_name}</span>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label className="text-[10px] text-slate-500 font-mono uppercase">System Prompt</label>
                        <textarea
                          className="bg-slate-950 border border-slate-800 rounded p-3 text-xs font-mono text-slate-300 focus:outline-none focus:border-slate-700 resize-y min-h-[80px] max-h-[200px] leading-relaxed"
                          value={promptConfig.structural_extraction.system_prompt}
                          onChange={(e) => setPromptConfig({
                            ...promptConfig,
                            structural_extraction: { ...promptConfig.structural_extraction, system_prompt: e.target.value }
                          })}
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label className="text-[10px] text-slate-500 font-mono uppercase">User Prompt Template <span className="text-slate-600">(use &#123;raw_content&#125; placeholder)</span></label>
                        <textarea
                          className="bg-slate-950 border border-slate-800 rounded p-3 text-xs font-mono text-slate-300 focus:outline-none focus:border-slate-700 resize-y min-h-[60px] max-h-[150px] leading-relaxed"
                          value={promptConfig.structural_extraction.user_prompt_template}
                          onChange={(e) => setPromptConfig({
                            ...promptConfig,
                            structural_extraction: { ...promptConfig.structural_extraction, user_prompt_template: e.target.value }
                          })}
                        />
                      </div>
                    </div>

                    {/* Taxonomy Tagging Prompts */}
                    <div className="flex flex-col gap-3 bg-slate-900/30 p-4 rounded-lg border border-slate-900">
                      <div className="flex items-center gap-2">
                        <span className="text-[10px] text-cyan-400 font-mono uppercase tracking-wider font-bold">taxonomy_tagging</span>
                        <span className="text-[10px] text-slate-600 font-mono">→ agent: {promptConfig.taxonomy_tagging.agent_name}</span>
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label className="text-[10px] text-slate-500 font-mono uppercase">System Prompt</label>
                        <textarea
                          className="bg-slate-950 border border-slate-800 rounded p-3 text-xs font-mono text-slate-300 focus:outline-none focus:border-slate-700 resize-y min-h-[80px] max-h-[200px] leading-relaxed"
                          value={promptConfig.taxonomy_tagging.system_prompt}
                          onChange={(e) => setPromptConfig({
                            ...promptConfig,
                            taxonomy_tagging: { ...promptConfig.taxonomy_tagging, system_prompt: e.target.value }
                          })}
                        />
                      </div>
                      <div className="flex flex-col gap-1.5">
                        <label className="text-[10px] text-slate-500 font-mono uppercase">User Prompt Template <span className="text-slate-600">(use &#123;raw_content&#125; placeholder)</span></label>
                        <textarea
                          className="bg-slate-950 border border-slate-800 rounded p-3 text-xs font-mono text-slate-300 focus:outline-none focus:border-slate-700 resize-y min-h-[60px] max-h-[150px] leading-relaxed"
                          value={promptConfig.taxonomy_tagging.user_prompt_template}
                          onChange={(e) => setPromptConfig({
                            ...promptConfig,
                            taxonomy_tagging: { ...promptConfig.taxonomy_tagging, user_prompt_template: e.target.value }
                          })}
                        />
                      </div>
                    </div>

                    {/* Refusal Guard Prompt */}
                    <div className="flex flex-col gap-3 bg-orange-950/20 p-4 rounded-lg border border-orange-900/30">
                      <div className="flex items-center gap-2">
                        <ShieldAlert className="w-3.5 h-3.5 text-orange-400" />
                        <span className="text-[10px] text-orange-400 font-mono uppercase tracking-wider font-bold">Refusal Guard Instruction</span>
                        <span className="text-[10px] text-slate-600 font-mono">→ role: &quot;user&quot; (appended after user prompt)</span>
                      </div>
                      <p className="text-[11px] text-slate-400 leading-relaxed">
                        This instruction is appended as a final <code className="text-orange-300 bg-orange-950/40 px-1 rounded">role: &quot;user&quot;</code> message after the user prompt. 
                        It tells the model how to respond when the input is invalid. Responses ending with &quot;invalid input&quot; are auto-classified as <code className="text-orange-300 bg-orange-950/40 px-1 rounded">INVALID</code>.
                      </p>
                      <textarea
                        className="bg-slate-950 border border-orange-900/30 rounded p-3 text-xs font-mono text-orange-200 focus:outline-none focus:border-orange-800 resize-y min-h-[80px] max-h-[200px] leading-relaxed"
                        value={promptConfig.refusal_prompt}
                        onChange={(e) => setPromptConfig({
                          ...promptConfig,
                          refusal_prompt: e.target.value
                        })}
                      />
                    </div>
                  </div>
                )}
              </CardContent>
            )}
          </Card>

          {/* ── PANEL 4: RELATIONAL DATA QUEUE GRID ───────────────────────────── */}
          <Card className="bg-slate-950/70 border border-slate-800/80 backdrop-blur-xs overflow-hidden">
            <CardHeader className="border-b border-slate-900 pb-4 bg-slate-950/40">
              <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <CardTitle className="text-sm font-semibold tracking-wider text-slate-300 uppercase flex items-center gap-2">
                    <Database className="w-4 h-4 text-sky-400" />
                    Relational Data Queue Grid
                  </CardTitle>
                  <Badge className="bg-sky-500/10 text-sky-400 border border-sky-500/20 font-mono text-[10px]">
                    {filteredAndSortedEntries.length} Items Listed
                  </Badge>
                  {selectedRequestIds.length > 0 && (
                    <div className="flex items-center gap-2 border-l border-slate-800 pl-3">
                      <Badge className="bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-mono text-[10px]">
                        {selectedRequestIds.length} Selected
                      </Badge>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-[10px] font-mono border-emerald-800 hover:bg-emerald-950 bg-emerald-950/40 text-emerald-300 py-0 flex items-center"
                        onClick={handleExportSelected}
                      >
                        <Download className="w-3.5 h-3.5 mr-1" />
                        Export JSON
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-[10px] font-mono border-teal-800 hover:bg-teal-950 bg-teal-950/40 text-teal-300 py-0 flex items-center"
                        onClick={handleExportSimplified}
                      >
                        <Download className="w-3.5 h-3.5 mr-1" />
                        Export Simplified
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-[10px] font-mono border-indigo-800 hover:bg-indigo-950 bg-indigo-950/40 text-indigo-300 py-0 flex items-center"
                        onClick={handleExecuteSelected}
                        disabled={isExecutingSelected}
                      >
                        {isExecutingSelected ? (
                          <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
                        ) : (
                          <Play className="w-3.5 h-3.5 mr-1 text-indigo-400 fill-indigo-400/20" />
                        )}
                        Execute Selected
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-[10px] font-mono border-amber-800 hover:bg-amber-950 bg-amber-950/40 text-amber-500 py-0 flex items-center"
                        onClick={handleSetPendingSelected}
                        disabled={isSettingPendingSelected}
                      >
                        {isSettingPendingSelected ? (
                          <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
                        ) : (
                          <Zap className="w-3.5 h-3.5 mr-1 text-amber-500" />
                        )}
                        Set Pending
                      </Button>
                      <Button
                        variant="outline"
                        size="sm"
                        className="h-7 text-[10px] font-mono border-cyan-800 hover:bg-cyan-950 bg-cyan-950/40 text-cyan-300 py-0 flex items-center"
                        onClick={() => handleCalculateRealTokens(selectedRequestIds)}
                        disabled={isCalculatingTokens}
                      >
                        {isCalculatingTokens ? (
                          <RefreshCw className="w-3.5 h-3.5 mr-1 animate-spin" />
                        ) : (
                          <Cpu className="w-3.5 h-3.5 mr-1 text-cyan-400" />
                        )}
                        Recalculate Tokens
                      </Button>
                    </div>
                  )}
                </div>

                {/* Keyword search and filters */}
                <div className="flex flex-wrap items-center gap-3">
                  <div className="relative w-64">
                    <Search className="absolute left-2.5 top-2.5 h-3.5 w-3.5 text-slate-500" />
                    <Input
                      placeholder="Regex Filter (e.g. cbb structural)..."
                      className="pl-8 text-xs border-slate-800/80 bg-slate-900/50 text-slate-200 h-8"
                      value={searchTerm}
                      onChange={(e) => setSearchTerm(e.target.value)}
                    />
                  </div>

                  {/* Source feed filter */}
                  <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono bg-slate-900/30 border border-slate-800/50 rounded px-2.5 py-1">
                    <Filter className="w-3.5 h-3.5 text-slate-500" />
                    <span className="text-slate-500">FEED:</span>
                    {["All", "CBB", "SBB", "IBB"].map((pool) => (
                      <button
                        key={pool}
                        onClick={() => setSelectedPoolFilter(pool === "All" ? null : pool.toLowerCase())}
                        className={`hover:text-white transition-colors uppercase ${
                          (pool === "All" && !selectedPoolFilter) || (selectedPoolFilter === pool.toLowerCase())
                            ? "text-sky-400 font-bold"
                            : "text-slate-400"
                        }`}
                      >
                        {pool}
                      </button>
                    ))}
                  </div>

                  {/* Status filter */}
                  <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-400 font-mono bg-slate-900/30 border border-slate-800/50 rounded px-2.5 py-1">
                    <span className="text-slate-500">STATUS:</span>
                    {["All", "PENDING", "RUNNING", "DISPATCHED", "FAILED", "INVALID", "INVALID_INPUT", "PROSE_REFUSAL", "MALFORMED_JSON", "SKIPPED_METADATA", "NO CONTENT"].map((status) => (
                      <button
                        key={status}
                        onClick={() => setSelectedStatusFilter(status === "All" ? null : status)}
                        className={`hover:text-white transition-colors ${
                          (status === "All" && !selectedStatusFilter) || (selectedStatusFilter === status)
                            ? "text-sky-400 font-bold"
                            : "text-slate-400"
                        }`}
                      >
                        {status}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </CardHeader>
            
            <div className="overflow-x-auto min-h-[300px]">
              <Table className="border-collapse">
                <TableHeader className="bg-slate-900/30 border-b border-slate-900 font-mono text-[11px] text-slate-400 uppercase tracking-wider">
                  <TableRow>
                    <TableHead className="w-12 text-slate-400">
                      <input
                        type="checkbox"
                        className="rounded bg-slate-950 border-slate-800 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-950"
                        checked={filteredAndSortedEntries.length > 0 && selectedRequestIds.length === filteredAndSortedEntries.length}
                        onChange={(e) => {
                          if (e.target.checked) {
                            setSelectedRequestIds(filteredAndSortedEntries.map(entry => entry.id))
                          } else {
                            setSelectedRequestIds([])
                          }
                        }}
                      />
                    </TableHead>
                    <TableHead className="w-16 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("id")}>
                      <div className="flex items-center gap-1">
                        ID
                        <ArrowUpDown className="w-3 h-3" />
                      </div>
                    </TableHead>
                    <TableHead className="w-32 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("source_pool")}>
                      <div className="flex items-center gap-1">
                        Source Feed
                        <ArrowUpDown className="w-3 h-3" />
                      </div>
                    </TableHead>
                    <TableHead className="w-48 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("request_type")}>
                      <div className="flex items-center gap-1">
                        Request Type
                        <ArrowUpDown className="w-3 h-3" />
                      </div>
                    </TableHead>
                    <TableHead className="w-36 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("character_count")}>
                      <div className="flex items-center gap-1">
                        Char Length
                        <ArrowUpDown className="w-3 h-3" />
                      </div>
                    </TableHead>
                    <TableHead className="w-36 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("character_count")}>
                      <div className="flex items-center gap-1">
                        Est Tokens
                        <ArrowUpDown className="w-3 h-3" />
                      </div>
                    </TableHead>
                    <TableHead className="w-36 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("estimated_tokens")}>
                      <div className="flex items-center gap-1">
                        Context Window
                        <ArrowUpDown className="w-3 h-3" />
                      </div>
                    </TableHead>
                    <TableHead className="w-40 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("token_bucket_tier")}>
                      <div className="flex items-center gap-1">
                        Token Tier
                        <ArrowUpDown className="w-3 h-3" />
                      </div>
                    </TableHead>
                    <TableHead className="w-36 text-slate-400 cursor-pointer hover:bg-slate-900" onClick={() => handleSort("dispatch_status")}>
                      <div className="flex items-center gap-1">
                        Status
                        <ArrowUpDown className="w-3 h-3" />
                      </div>
                    </TableHead>
                    <TableHead className="w-20 text-right text-slate-400">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody className="text-xs divide-y divide-slate-900/60 font-mono">
                  {loading ? (
                    <TableRow>
                      <TableCell colSpan={10} className="text-center py-10 text-slate-500">
                        <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-sky-400" />
                        Querying Relational Batch Workspace Registry...
                      </TableCell>
                    </TableRow>
                  ) : filteredAndSortedEntries.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={10} className="text-center py-10 text-slate-500">
                        No registry rows match active search criteria.
                      </TableCell>
                    </TableRow>
                  ) : (
                    filteredAndSortedEntries.map((row) => (
                      <TableRow 
                        key={row.id} 
                        className="hover:bg-slate-900/40 border-b border-slate-900/40 cursor-pointer"
                        onClick={() => setSelectedItem(row)}
                      >
                        <TableCell onClick={(e) => e.stopPropagation()} className="w-12">
                          <input
                            type="checkbox"
                            className="rounded bg-slate-950 border-slate-800 text-sky-500 focus:ring-sky-500 focus:ring-offset-slate-950"
                            checked={selectedRequestIds.includes(row.id)}
                            onChange={(e) => {
                              if (e.target.checked) {
                                setSelectedRequestIds(prev => [...prev, row.id])
                              } else {
                                setSelectedRequestIds(prev => prev.filter(id => id !== row.id))
                              }
                            }}
                          />
                        </TableCell>
                        <TableCell className="font-bold text-slate-400">{row.id}</TableCell>
                        <TableCell className="uppercase text-slate-300 font-semibold">{row.source_pool}</TableCell>
                        <TableCell className="text-slate-400">{row.request_type}</TableCell>
                        <TableCell>{row.character_count ? row.character_count.toLocaleString() : 0}</TableCell>
                        <TableCell className="text-slate-300 font-medium">{Math.floor((row.character_count || 0) / 4).toLocaleString()}</TableCell>
                        <TableCell className="text-sky-300 font-bold">{row.estimated_tokens ? row.estimated_tokens.toLocaleString() : 0}</TableCell>
                        <TableCell>
                          <span className="text-[11px] bg-slate-900/80 px-2 py-0.5 border border-slate-800/80 rounded text-slate-300">
                            {row.token_bucket_tier}
                          </span>
                        </TableCell>
                        <TableCell>{renderStatusBadge(row.dispatch_status)}</TableCell>
                        <TableCell className="text-right" onClick={(e) => e.stopPropagation()}>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 w-7 p-0 text-slate-400 hover:text-slate-100 hover:bg-slate-800"
                            onClick={() => setSelectedItem(row)}
                          >
                            <Maximize2 className="w-3.5 h-3.5" />
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>

            {/* Client side pagination */}
            <div className="bg-slate-950/40 p-4 border-t border-slate-900 flex items-center justify-between text-xs font-mono text-slate-500">
              <div className="flex items-center gap-4">
                <div className="flex items-center gap-1.5">
                  <span>Show:</span>
                  <select
                    className="bg-slate-900 border border-slate-850 rounded px-2 py-0.5 text-xs text-sky-400 focus:outline-none focus:border-slate-700 cursor-pointer h-7"
                    value={limit === totalCount ? "all" : limit.toString()}
                    onChange={(e) => {
                      const val = e.target.value
                      if (val === "all") {
                        setLimit(totalCount || 100000)
                        setOffset(0)
                      } else {
                        setLimit(parseInt(val))
                        setOffset(0)
                      }
                    }}
                  >
                    <option value="50">50</option>
                    <option value="100">100</option>
                    <option value="250">250</option>
                    <option value="500">500</option>
                    <option value="all">All</option>
                  </select>
                </div>
                <div>
                  Showing <span className="text-slate-300">{totalCount > 0 ? offset + 1 : 0}</span> to{" "}
                  <span className="text-slate-300">{Math.min(offset + limit, totalCount)}</span> of{" "}
                  <span className="text-slate-300">{totalCount}</span> entries
                </div>
              </div>
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  size="sm"
                  className="border-slate-850 bg-slate-900 hover:bg-slate-950 text-slate-400 hover:text-slate-200 h-8"
                  disabled={offset === 0}
                  onClick={() => setOffset(Math.max(0, offset - limit))}
                >
                  Previous
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  className="border-slate-850 bg-slate-900 hover:bg-slate-950 text-slate-400 hover:text-slate-200 h-8"
                  disabled={offset + limit >= totalCount}
                  onClick={() => setOffset(offset + limit)}
                >
                  Next
                </Button>
              </div>
            </div>
          </Card>

          {/* ── PANEL 5 & 6: SHEET INSPECTOR & DIAGNOSTIC PANEL ────────────────── */}
          <Sheet open={selectedItem !== null} onOpenChange={(open) => { if (!open) setSelectedItem(null) }}>
            <SheetContent className="sm:max-w-3xl border-l border-slate-800/80 bg-slate-950/95 text-slate-100 flex flex-col justify-between overflow-y-auto">
              {selectedItem && (
                <>
                  <div>
                    <SheetHeader className="mb-4">
                      <div className="flex items-center gap-3">
                        <span className="text-xs font-mono uppercase bg-slate-900 text-sky-400 border border-slate-800 px-2 py-0.5 rounded">
                          ID #{selectedItem.id}
                        </span>
                        <span className="text-xs font-mono uppercase text-slate-400">
                          FEED: <span className="text-slate-200 font-bold">{selectedItem.source_pool}</span>
                        </span>
                      </div>
                      <SheetTitle className="text-xl font-bold tracking-tight text-white flex items-center justify-between">
                        Request Cell Details
                        {renderStatusBadge(selectedItem.dispatch_status)}
                      </SheetTitle>
                      <SheetDescription className="text-slate-400 text-xs">
                        Inspect structural parameters, token estimations, and prompt layouts compiled inside the registry.
                      </SheetDescription>
                    </SheetHeader>

                    {/* ── PANEL 6: SURGICAL FAILURE DIAGNOSTIC PANEL ───────────── */}
                    {selectedItem.dispatch_status.toUpperCase() === "FAILED" && (
                      <div className="bg-amber-950/30 border border-amber-500/20 text-amber-300 p-4 rounded-lg mb-6 text-xs font-mono whitespace-pre-wrap">
                        <div className="font-semibold text-sm mb-1 text-amber-400 flex items-center gap-1.5">
                          <AlertTriangle className="w-4 h-4 text-amber-400" />
                          Connection / Timeout Trace Log:
                        </div>
                        {selectedItem.error_log || "Connection timeout trace log. Check remote vLLM endpoint availability."}
                        
                        <div className="mt-3.5 flex justify-end">
                          <Button
                            size="sm"
                            className="bg-amber-500 hover:bg-amber-600 text-black font-semibold h-7 font-sans rounded-xs flex items-center gap-1"
                            disabled={isRequeuing === selectedItem.id}
                            onClick={() => handleRequeueItem(selectedItem.id)}
                          >
                            {isRequeuing === selectedItem.id ? (
                              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <Zap className="w-3.5 h-3.5 text-black" />
                            )}
                            Surgically Re-Queue
                          </Button>
                        </div>
                      </div>
                    )}

                    {/* Queue context layout */}
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-3 bg-slate-900/30 p-3.5 rounded border border-slate-900 mb-6 font-mono text-[11px]">
                      <div>
                        <span className="text-slate-500 block">SOURCE IDENTIFIER</span>
                        <span className="text-slate-200 mt-0.5 block truncate">{selectedItem.source_identifier}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">REQUEST TYPE</span>
                        <span className="text-slate-200 mt-0.5 block">{selectedItem.request_type}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">CHARACTER COUNT</span>
                        <span className="text-slate-200 mt-0.5 block">{selectedItem.character_count ? selectedItem.character_count.toLocaleString() : 0}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">EST PROMPT TOKENS</span>
                        <span className="text-slate-200 mt-0.5 block font-medium text-slate-300">{Math.floor((selectedItem.character_count || 0) / 4).toLocaleString()}</span>
                      </div>
                      <div>
                        <span className="text-slate-500 block">CONTEXT WINDOW</span>
                        <span className="text-slate-200 mt-0.5 block font-bold text-sky-400">{selectedItem.estimated_tokens ? selectedItem.estimated_tokens.toLocaleString() : 0}</span>
                      </div>
                      <div className="col-span-2 md:col-span-4 flex justify-end border-t border-slate-900 pt-2 mt-1">
                        <Button
                          variant="outline"
                          size="sm"
                          className="h-6 text-[9px] font-mono border-cyan-900/60 bg-cyan-950/20 hover:bg-cyan-950/50 text-cyan-400 px-2 flex items-center gap-1"
                          onClick={() => handleCalculateRealTokens([selectedItem.id])}
                          disabled={isCalculatingTokens}
                        >
                          {isCalculatingTokens ? (
                            <RefreshCw className="w-3 h-3 animate-spin" />
                          ) : (
                            <Cpu className="w-3 h-3 text-cyan-400" />
                          )}
                          Recalculate via vLLM
                        </Button>
                      </div>
                    </div>

                    {/* Refusal Guard alert block */}
                    <div className="bg-orange-950/20 border border-orange-900/30 text-orange-200 p-3.5 rounded mb-6 text-xs leading-relaxed flex flex-col gap-1 font-mono">
                      <span className="text-[10px] text-orange-400 font-bold uppercase tracking-wider block flex items-center gap-1.5">
                        <ShieldAlert className="w-3.5 h-3.5 text-orange-400" />
                        ACTIVE REFUSAL GUARD INSTRUCTION
                      </span>
                      <span>{selectedItem.refusal_prompt_payload || "IMPORTANT INSTRUCTION: If the input provided above does not contain valid source code or relevant data for your analysis task, or if you cannot extract the requested information because it is simply not present in the input, respond with exactly the words 'invalid input' at the end of your response. Do not attempt to fabricate, hallucinate, or infer information that is not present in the input."}</span>
                    </div>

                    {/* Prompt Construction & Architecture details */}
                    <div className="bg-slate-950/60 border border-slate-800/60 rounded p-4 mb-6 text-xs flex flex-col gap-3 font-sans">
                      <div className="text-[10px] text-slate-500 font-mono tracking-wider uppercase font-semibold">Prompt Construction & Architecture</div>
                      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                        <div>
                          <div className="text-slate-400 font-semibold mb-1">Source Assembly</div>
                          <p className="text-slate-300 leading-relaxed">
                            Built from staged record <span className="font-mono text-sky-400 text-[11px]">{selectedItem.source_identifier}</span> within the <span className="font-mono text-slate-200 text-[11px]">{selectedItem.source_pool}</span> source repository feed.
                          </p>
                        </div>
                        <div>
                          <div className="text-slate-400 font-semibold mb-1">Objectives & Target</div>
                          <p className="text-slate-300 leading-relaxed">
                            {selectedItem.request_type === "structural_extraction" 
                              ? "Aiming to parse Solidity source code to extract code metrics, operators count, loop nesting depth, and external call footprints."
                              : "Aiming to extract vulnerability micro-niches, testability tiers, and programmatic payout parameters from the bounty report."
                            }
                          </p>
                        </div>
                        <div>
                          <div className="text-slate-400 font-semibold mb-1">Downstream Exploitation</div>
                          <p className="text-slate-300 leading-relaxed">
                            {selectedItem.request_type === "structural_extraction"
                              ? "Feeds structural features to guide MCTS state selection and candidate generation for the smart contract fuzzer."
                              : "Classifies vulnerability targets in the relational taxonomy mapping layer to group combinatorial attack matrices."
                            }
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* ── PANEL 5: SIDE-SHEET PAYLOAD INSPECTOR ────────────────── */}
                    <Tabs defaultValue="system_prompt" className="w-full">
                      <TabsList className="bg-slate-900 border border-slate-800 w-full justify-start p-1 h-9 rounded-md overflow-x-auto">
                        <TabsTrigger value="system_prompt" className="text-xs font-mono data-[state=active]:bg-slate-800 rounded px-3 py-1">
                          System Prompt
                        </TabsTrigger>
                        <TabsTrigger value="user_prompt" className="text-xs font-mono data-[state=active]:bg-slate-800 rounded px-3 py-1">
                          User Prompt
                        </TabsTrigger>
                        <TabsTrigger value="refusal_prompt" className="text-xs font-mono data-[state=active]:bg-slate-800 rounded px-3 py-1 text-orange-400">
                          Refusal Guard
                        </TabsTrigger>
                        <TabsTrigger value="request_details" className="text-xs font-mono data-[state=active]:bg-slate-800 rounded px-3 py-1 text-sky-400">
                          Request Details
                        </TabsTrigger>
                        {selectedItem.response_payload && (
                          <TabsTrigger value="response_payload" className="text-xs font-mono data-[state=active]:bg-slate-800 rounded px-3 py-1 text-emerald-400">
                            LLM Response
                          </TabsTrigger>
                        )}
                        <TabsTrigger value="edit_prompts" className="text-xs font-mono data-[state=active]:bg-slate-800 rounded px-3 py-1 text-indigo-400">
                          Edit Prompts
                        </TabsTrigger>
                      </TabsList>
                      
                      <TabsContent value="user_prompt" className="mt-3">
                        <div className="flex flex-col gap-1.5">
                          <div className="text-[10px] text-slate-500 font-mono">HYDRATED USER PAYLOAD SNIPPET</div>
                          <HighlightSolidityCode code={selectedItem.user_prompt_payload} />
                        </div>
                      </TabsContent>
                      
                      <TabsContent value="system_prompt" className="mt-3">
                        <div className="flex flex-col gap-1.5">
                          <div className="text-[10px] text-slate-500 font-mono">HYDRATED SYSTEM PAYLOAD SNIPPET</div>
                          <HighlightSolidityCode code={selectedItem.system_prompt_payload} />
                        </div>
                      </TabsContent>

                      <TabsContent value="request_details" className="mt-3">
                        <RequestDetailsView item={selectedItem} maxTokens={maxTokens} />
                      </TabsContent>

                      <TabsContent value="refusal_prompt" className="mt-3">
                        <div className="flex flex-col gap-2">
                          <div className="flex items-center gap-2 mb-1">
                            <ShieldAlert className="w-3.5 h-3.5 text-orange-400" />
                            <span className="text-[10px] text-orange-400 font-mono uppercase tracking-wider font-bold">Refusal Guard Instruction</span>
                          </div>
                          <div className="bg-orange-950/20 border border-orange-900/30 rounded-lg p-4">
                            <pre className="font-mono text-[11px] leading-relaxed text-orange-200 whitespace-pre-wrap break-words select-text">
                              {selectedItem.refusal_prompt_payload || "IMPORTANT INSTRUCTION: If the input provided above does not contain valid source code or relevant data for your analysis task, or if you cannot extract the requested information because it is simply not present in the input, respond with exactly the words 'invalid input' at the end of your response. Do not attempt to fabricate, hallucinate, or infer information that is not present in the input."}
                            </pre>
                          </div>
                          <p className="text-[10px] text-slate-500 font-mono mt-1">
                            Sent as <code className="text-orange-300">role: &quot;user&quot;</code> after the user prompt. Responses ending with &quot;invalid input&quot; → <code className="text-orange-300">INVALID</code> status.
                          </p>
                        </div>
                      </TabsContent>

                      {selectedItem.response_payload && (
                        <TabsContent value="response_payload" className="mt-3">
                          <ResponseDetailsView responsePayload={selectedItem.response_payload} />
                        </TabsContent>
                      )}

                      <TabsContent value="edit_prompts" className="mt-3">
                        <EditItemPromptsView
                          item={selectedItem}
                          onSaveAndRequeue={handleSaveItemPromptsAndRequeue}
                        />
                      </TabsContent>
                    </Tabs>
                  </div>

                  {/* Action buttons footer */}
                  <div className="border-t border-slate-900 pt-4 mt-6 flex justify-between gap-3 bg-slate-950 py-3">
                    <Button
                      variant="outline"
                      size="sm"
                      className="border-slate-800 bg-slate-900 text-slate-300 hover:bg-slate-950 font-mono"
                      onClick={() => setSelectedItem(null)}
                    >
                      Close Pane
                    </Button>

                    {selectedItem.dispatch_status.toUpperCase() !== "FAILED" && (
                      <Button
                        size="sm"
                        className="bg-sky-600 hover:bg-sky-700 text-white font-mono flex items-center gap-1"
                        disabled={isRequeuing === selectedItem.id}
                        onClick={() => handleRequeueItem(selectedItem.id)}
                      >
                        {isRequeuing === selectedItem.id ? (
                          <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                        ) : (
                          <Terminal className="w-3.5 h-3.5" />
                        )}
                        Force Re-Run Task
                      </Button>
                    )}
                  </div>
                </>
              )}
            </SheetContent>
          </Sheet>
        </div>
      )}
    </div>
  )
}
