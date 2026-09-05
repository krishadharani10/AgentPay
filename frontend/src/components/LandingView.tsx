import React from 'react'
import {
  Shield,
  CheckCircle2,
  Lock,
  ArrowRight,
  ShieldCheck,
  CreditCard,
  FileText,
  RotateCcw,
  Sliders,
  Sparkles,
} from 'lucide-react'
import { PaymentFlowDiagram } from './PaymentFlowDiagram'

interface LandingViewProps {
  onGoToDashboard: () => void
  onExploreTasks: () => void
}

export const LandingView: React.FC<LandingViewProps> = ({
  onGoToDashboard,
  onExploreTasks,
}) => {
  const scrollToHowItWorks = () => {
    const el = document.getElementById('how-it-works-section')
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' })
    }
  }

  return (
    <div className="space-y-16 pb-12">
      {/* ── HERO SECTION (Req 12) ─────────────────────────────────────────── */}
      <section className="pt-8 sm:pt-14 pb-8 max-w-4xl mx-auto text-center space-y-6">
        {/* Subtle pill tag */}
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-blue-50 border border-blue-100 text-xs font-medium text-[#305EFF]">
          <Shield className="w-3.5 h-3.5" />
          <span>Permissioned Infrastructure for AI Agents</span>
        </div>

        {/* Hero Title */}
        <h1 className="text-3xl sm:text-4xl md:text-5xl font-bold tracking-tight text-slate-900 leading-[1.15]">
          Permissioned autonomous payments for AI agents.
        </h1>

        {/* Hero Subtitle */}
        <p className="text-base sm:text-lg text-slate-600 max-w-2xl mx-auto font-normal leading-relaxed">
          AgentPay lets AI agents execute payments within human-defined spending limits,
          policies, and security controls.
        </p>

        {/* CTAs */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-3 pt-3">
          <button
            type="button"
            onClick={onGoToDashboard}
            className="w-full sm:w-auto px-6 py-2.5 rounded-lg bg-[#305EFF] hover:bg-[#254cd4] text-white text-sm font-medium shadow-xs transition-colors flex items-center justify-center gap-2 cursor-pointer"
          >
            <span>View Dashboard</span>
            <ArrowRight className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={scrollToHowItWorks}
            className="w-full sm:w-auto px-6 py-2.5 rounded-lg bg-white hover:bg-slate-50 text-slate-700 text-sm font-medium border border-slate-200 transition-colors flex items-center justify-center gap-1.5 cursor-pointer"
          >
            <span>How It Works</span>
          </button>
        </div>

        {/* Trust Guarantee Micro-Bar */}
        <div className="pt-6 flex flex-wrap items-center justify-center gap-6 text-xs text-slate-500">
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span>Deterministic Policy Engine</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span>Zero Unrestricted Card Access</span>
          </div>
          <div className="flex items-center gap-1.5">
            <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            <span>Razorpay Test Mode & Mock Rails</span>
          </div>
        </div>
      </section>

      {/* ── VALUE PROPOSITIONS (Req 13) ───────────────────────────────────── */}
      <section className="space-y-6">
        <div className="text-center max-w-xl mx-auto space-y-2">
          <h2 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
            Built for Secure Agentic Commerce
          </h2>
          <p className="text-xs sm:text-sm text-slate-500 font-normal">
            Three core pillars designed to keep financial authority strictly deterministic.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          {/* 1. Policy Control */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)] flex flex-col justify-between hover:border-slate-300 transition-colors">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-[#305EFF]">
                <Sliders className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-slate-900">
                Policy Control
              </h3>
              <p className="text-xs sm:text-sm text-slate-600 leading-relaxed font-normal">
                Every payment is evaluated against deterministic human-defined rules before execution.
                Limits, categories, and whitelists are enforced outside the LLM.
              </p>
            </div>
            <div className="pt-4 mt-4 border-t border-slate-100 flex items-center gap-2 text-xs font-medium text-emerald-700">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>Deterministic Enforcement</span>
            </div>
          </div>

          {/* 2. Payment Reliability */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)] flex flex-col justify-between hover:border-slate-300 transition-colors">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-[#305EFF]">
                <RotateCcw className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-slate-900">
                Payment Reliability
              </h3>
              <p className="text-xs sm:text-sm text-slate-600 leading-relaxed font-normal">
                Provider abstraction, retries, idempotency, and fallback handling improve payment reliability
                when upstream provider rails experience transient drops.
              </p>
            </div>
            <div className="pt-4 mt-4 border-t border-slate-100 flex items-center gap-2 text-xs font-medium text-[#305EFF]">
              <CreditCard className="w-4 h-4" />
              <span>Multi-Rail Fallback Engine</span>
            </div>
          </div>

          {/* 3. Audit & Trust */}
          <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)] flex flex-col justify-between hover:border-slate-300 transition-colors">
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-[#305EFF]">
                <FileText className="w-5 h-5" />
              </div>
              <h3 className="text-base font-semibold text-slate-900">
                Audit & Trust
              </h3>
              <p className="text-xs sm:text-sm text-slate-600 leading-relaxed font-normal">
                Every decision and transaction is traceable through the transaction state machine and audit trail,
                offering complete explainability for compliance.
              </p>
            </div>
            <div className="pt-4 mt-4 border-t border-slate-100 flex items-center gap-2 text-xs font-medium text-slate-700">
              <Lock className="w-4 h-4 text-slate-500" />
              <span>Immutable State Records</span>
            </div>
          </div>
        </div>
      </section>

      {/* ── HOW AGENTPAY WORKS (Req 10, 11) ───────────────────────────────── */}
      <section id="how-it-works-section" className="space-y-6 pt-4">
        <div className="text-center max-w-xl mx-auto space-y-2">
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-700 text-[11px] font-medium">
            <span>Architecture & Process</span>
          </div>
          <h2 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight">
            How AgentPay Works
          </h2>
          <p className="text-xs sm:text-sm text-slate-500 font-normal">
            The six distinct stages of the permissioned autonomous payment lifecycle.
          </p>
        </div>

        <PaymentFlowDiagram />
      </section>

      {/* ── TRUST DASHBOARD CALLOUT (Req 14) ──────────────────────────────── */}
      <section className="bg-white border border-slate-200 rounded-xl p-6 sm:p-8 shadow-[0_1px_3px_rgba(15,23,42,0.04)] space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="space-y-2 max-w-xl">
            <span className="text-xs font-semibold text-[#305EFF] uppercase tracking-wider">
              Core Security Invariant
            </span>
            <h3 className="text-xl sm:text-2xl font-bold text-slate-900">
              “The AI is autonomous, but the money is controlled.”
            </h3>
            <p className="text-xs sm:text-sm text-slate-600 leading-relaxed font-normal">
              Autonomous agents can research flights, book meeting venues, or order office supplies.
              AgentPay ensures no funds are released unless all spending caps, category guardrails, and
              merchant rules verify cleanly.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row md:flex-col gap-3 shrink-0">
            <button
              type="button"
              onClick={onGoToDashboard}
              className="px-5 py-2.5 rounded-lg bg-[#305EFF] hover:bg-[#254cd4] text-white text-xs sm:text-sm font-medium shadow-xs transition-colors flex items-center justify-center gap-2 cursor-pointer"
            >
              <span>Open Trust Dashboard</span>
              <ArrowRight className="w-4 h-4" />
            </button>
            <button
              type="button"
              onClick={onExploreTasks}
              className="px-5 py-2.5 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs sm:text-sm font-medium border border-slate-200 transition-colors flex items-center justify-center gap-2 cursor-pointer"
            >
              <Sparkles className="w-4 h-4 text-[#305EFF]" />
              <span>Try Autonomous Tasks</span>
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
