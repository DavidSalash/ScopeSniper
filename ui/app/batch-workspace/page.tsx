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
  Scale
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
      // Fallback mock dataset if API starting up
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

  return (
    <div className="flex flex-col gap-6 text-slate-100 pb-12">
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
          <Card className="bg-slate-950/70 border border-slate-800/80 backdrop-blur-xs p-6">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Activity className="w-6 h-6 text-emerald-400" />
                <div>
                  <h2 className="text-lg font-bold text-white">Live Batch Completion Engine</h2>
                  <p className="text-xs text-slate-400">NVIDIA RTX 5090 cluster Autopilot Queue Manager</p>
                </div>
              </div>
              <Link href="/api/ingestion/stream" target="_blank">
                <Button variant="outline" size="sm" className="border-slate-800 font-mono text-xs text-sky-400">
                  SSE Stream Telemetry
                </Button>
              </Link>
            </div>
          </Card>

          <TargetProfitabilityMatrixView />
        </div>
      )}
    </div>
  )
}
