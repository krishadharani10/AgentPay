import { useState, useEffect } from 'react'
import {
  ShieldCheck,
  Server,
  Database,
  Cpu,
  RefreshCw,
  CheckCircle2,
  AlertCircle,
  Lock,
  Layers,
  Terminal,
  Activity
} from 'lucide-react'

interface HealthData {
  status: string
  app: string
  environment: string
  database: string
  version: string
  details?: Record<string, unknown>
}

export function App() {
  const [health, setHealth] = useState<HealthData | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [error, setError] = useState<string | null>(null)
  const [lastChecked, setLastChecked] = useState<Date | null>(null)

  const checkHealth = async () => {
    setLoading(true)
    setError(null)
    try {
      // Attempt to query via Vite proxy or direct relative path / direct backend URL
      let res: Response
      try {
        res = await fetch('/api/health')
      } catch {
        res = await fetch('http://127.0.0.1:8000/health')
      }

      if (!res.ok) {
        throw new Error(`Server returned status ${res.status}`)
      }
      const data: HealthData = await res.json()
      setHealth(data)
      setLastChecked(new Date())
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to connect to backend'
      setError(msg)
      setHealth(null)
      setLastChecked(new Date())
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    checkHealth()
  }, [])

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col justify-between">
      {/* Background glow effects */}
      <div className="fixed inset-0 overflow-hidden pointer-events-none -z-10">
        <div className="absolute -top-40 left-1/2 -translate-x-1/2 w-[700px] h-[350px] bg-indigo-600/15 blur-[120px] rounded-full" />
        <div className="absolute top-1/3 -right-40 w-[400px] h-[400px] bg-blue-600/10 blur-[100px] rounded-full" />
        <div className="absolute bottom-10 left-10 w-[350px] h-[350px] bg-emerald-600/10 blur-[100px] rounded-full" />
      </div>

      {/* Header / Navbar */}
      <header className="border-b border-slate-800/80 bg-slate-900/40 backdrop-blur-md sticky top-0 z-50">
        <div className="max-w-6xl mx-auto px-6 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-violet-500 flex items-center justify-center shadow-lg shadow-indigo-500/20 ring-1 ring-white/20">
              <ShieldCheck className="w-6 h-6 text-white" />
            </div>
            <div>
              <div className="font-bold text-lg tracking-tight bg-gradient-to-r from-white via-slate-200 to-slate-400 bg-clip-text text-transparent">
                AgentPay
              </div>
              <div className="text-[11px] text-slate-400 font-medium tracking-wide uppercase">
                Foundation MVP
              </div>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              Frontend Active
            </span>
            <button
              id="refresh-health-btn"
              onClick={checkHealth}
              disabled={loading}
              className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 active:scale-95 border border-slate-700 text-slate-200 transition-all cursor-pointer disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-indigo-400' : ''}`} />
              Sync Status
            </button>
          </div>
        </div>
      </header>

      {/* Main Body */}
      <main className="max-w-6xl mx-auto px-6 py-10 flex-1 w-full space-y-8">
        {/* Hero Section */}
        <div className="text-center max-w-3xl mx-auto space-y-4 pt-4">
          <div className="inline-flex items-center gap-2 px-3.5 py-1 rounded-full text-xs font-medium bg-indigo-500/10 text-indigo-300 border border-indigo-500/20">
            <Lock className="w-3.5 h-3.5" />
            Permissioned Payment Infrastructure for AI Agents
          </div>
          <h1 className="text-4xl sm:text-5xl font-extrabold tracking-tight text-white leading-tight">
            System Foundation Ready
          </h1>
          <p className="text-slate-400 text-base sm:text-lg">
            FastAPI backend, React + Vite + TypeScript frontend, PostgreSQL container, and SQLAlchemy 2.x initialized with strict policy guardrails.
          </p>
        </div>

        {/* Status Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
          {/* Frontend Card */}
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 shadow-xl backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition-all">
            <div className="flex items-center justify-between mb-4">
              <div className="p-3 bg-blue-500/10 border border-blue-500/20 rounded-xl text-blue-400">
                <Cpu className="w-5 h-5" />
              </div>
              <span className="text-xs px-2.5 py-1 rounded-md font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
                <CheckCircle2 className="w-3.5 h-3.5" /> Running
              </span>
            </div>
            <h3 className="text-lg font-semibold text-white">Frontend Service</h3>
            <p className="text-xs text-slate-400 mt-1">React 18/19 • Vite • TypeScript • Tailwind CSS</p>
            <div className="mt-4 pt-4 border-t border-slate-800/80 text-xs text-slate-400 flex justify-between">
              <span>Port</span>
              <span className="font-mono text-slate-200">5173</span>
            </div>
          </div>

          {/* Backend Card */}
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 shadow-xl backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition-all">
            <div className="flex items-center justify-between mb-4">
              <div className="p-3 bg-indigo-500/10 border border-indigo-500/20 rounded-xl text-indigo-400">
                <Server className="w-5 h-5" />
              </div>
              {health?.status === 'ok' ? (
                <span className="text-xs px-2.5 py-1 rounded-md font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Connected
                </span>
              ) : loading ? (
                <span className="text-xs px-2.5 py-1 rounded-md font-medium bg-yellow-500/10 text-yellow-400 border border-yellow-500/20 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 animate-pulse" /> Connecting...
                </span>
              ) : (
                <span className="text-xs px-2.5 py-1 rounded-md font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20 flex items-center gap-1.5">
                  <AlertCircle className="w-3.5 h-3.5" /> Offline
                </span>
              )}
            </div>
            <h3 className="text-lg font-semibold text-white">FastAPI Backend</h3>
            <p className="text-xs text-slate-400 mt-1">Python • Uvicorn • Pydantic Settings</p>
            <div className="mt-4 pt-4 border-t border-slate-800/80 text-xs text-slate-400 flex justify-between">
              <span>Endpoint</span>
              <span className="font-mono text-slate-200">/health (Port 8000)</span>
            </div>
          </div>

          {/* Database Card */}
          <div className="bg-slate-900/60 border border-slate-800/80 rounded-2xl p-6 shadow-xl backdrop-blur-sm relative overflow-hidden group hover:border-slate-700 transition-all">
            <div className="flex items-center justify-between mb-4">
              <div className="p-3 bg-violet-500/10 border border-violet-500/20 rounded-xl text-violet-400">
                <Database className="w-5 h-5" />
              </div>
              {health?.database === 'connected' ? (
                <span className="text-xs px-2.5 py-1 rounded-md font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center gap-1.5">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Ready
                </span>
              ) : (
                <span className="text-xs px-2.5 py-1 rounded-md font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20 flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5" /> Docker Compose
                </span>
              )}
            </div>
            <h3 className="text-lg font-semibold text-white">PostgreSQL Engine</h3>
            <p className="text-xs text-slate-400 mt-1">SQLAlchemy 2.x • Alembic Migrations</p>
            <div className="mt-4 pt-4 border-t border-slate-800/80 text-xs text-slate-400 flex justify-between">
              <span>Database URL</span>
              <span className="font-mono text-slate-200 text-[11px]">localhost:5432/agentpay</span>
            </div>
          </div>
        </div>

        {/* Backend Health Check Details */}
        <div className="bg-slate-900/40 border border-slate-800/80 rounded-2xl p-6 backdrop-blur-sm">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2.5">
              <Terminal className="w-5 h-5 text-indigo-400" />
              <h2 className="text-base font-semibold text-white">Backend Health Diagnostics</h2>
            </div>
            {lastChecked && (
              <span className="text-xs text-slate-500 font-mono">
                Last checked: {lastChecked.toLocaleTimeString()}
              </span>
            )}
          </div>

          {loading ? (
            <div className="py-8 text-center text-slate-400 flex flex-col items-center justify-center gap-2">
              <RefreshCw className="w-6 h-6 animate-spin text-indigo-500" />
              <p className="text-sm">Querying /health endpoint...</p>
            </div>
          ) : error ? (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-sm flex items-start gap-3">
              <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5 text-rose-400" />
              <div>
                <p className="font-semibold">Backend Unreachable</p>
                <p className="text-xs text-rose-400 mt-1">{error}</p>
                <p className="text-xs text-slate-400 mt-2">
                  Ensure the FastAPI backend is running on <code className="text-slate-200">http://127.0.0.1:8000</code>.
                </p>
              </div>
            </div>
          ) : health ? (
            <div className="space-y-4">
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
                  <span className="text-xs text-slate-400 block">Status</span>
                  <span className="text-sm font-semibold text-emerald-400 font-mono">{health.status}</span>
                </div>
                <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
                  <span className="text-xs text-slate-400 block">Application</span>
                  <span className="text-sm font-semibold text-white font-mono">{health.app}</span>
                </div>
                <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
                  <span className="text-xs text-slate-400 block">Environment</span>
                  <span className="text-sm font-semibold text-indigo-300 font-mono">{health.environment}</span>
                </div>
                <div className="bg-slate-950/60 p-3 rounded-xl border border-slate-800/80">
                  <span className="text-xs text-slate-400 block">Database</span>
                  <span className="text-sm font-semibold text-violet-300 font-mono">{health.database}</span>
                </div>
              </div>
              <pre className="bg-slate-950 p-4 rounded-xl text-xs font-mono text-slate-300 overflow-x-auto border border-slate-800/80">
                {JSON.stringify(health, null, 2)}
              </pre>
            </div>
          ) : null}
        </div>

        {/* Core Architecture Rules Banner */}
        <div className="bg-gradient-to-r from-slate-900/80 via-indigo-950/30 to-slate-900/80 border border-indigo-500/20 rounded-2xl p-6">
          <div className="flex items-center gap-2 mb-3">
            <Layers className="w-5 h-5 text-indigo-400" />
            <h3 className="text-base font-semibold text-white">AgentPay Core Invariants</h3>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
            <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/60">
              <span className="font-semibold text-indigo-300 block mb-1">1. LLM Request Only</span>
              <span className="text-slate-400">LLM may request payments, but never directly authorizes or executes them.</span>
            </div>
            <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/60">
              <span className="font-semibold text-indigo-300 block mb-1">2. Deterministic Policy</span>
              <span className="text-slate-400">All financial authorizations pass through the deterministic Policy Engine.</span>
            </div>
            <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/60">
              <span className="font-semibold text-indigo-300 block mb-1">3. Strict Idempotency</span>
              <span className="text-slate-400">Every single payment transaction enforces a unique idempotency key.</span>
            </div>
            <div className="bg-slate-950/60 p-3.5 rounded-xl border border-slate-800/60">
              <span className="font-semibold text-indigo-300 block mb-1">4. Complete Audit Trail</span>
              <span className="text-slate-400">Every decision, success, fallback, and rejection produces an immutable audit record.</span>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="border-t border-slate-900 py-6 text-center text-xs text-slate-500">
        AgentPay • Permissioned Autonomous AI Payment Infrastructure • Hackathon MVP
      </footer>
    </div>
  )
}

export default App
