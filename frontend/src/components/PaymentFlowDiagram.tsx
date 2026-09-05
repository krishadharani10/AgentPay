import React from 'react'
import {
  Bot,
  ShieldCheck,
  Cpu,
  CreditCard,
  CheckCircle2,
  FileText,
  ArrowRight,
} from 'lucide-react'

interface PaymentFlowDiagramProps {
  currentStage?: 'AGENT' | 'POLICY' | 'SERVICE' | 'PROVIDER' | 'RESULT' | 'AUDIT' | 'ALL'
  compact?: boolean
}

export const PaymentFlowDiagram: React.FC<PaymentFlowDiagramProps> = ({
  currentStage = 'ALL',
  compact = false,
}) => {
  const stages = [
    {
      id: 'AGENT',
      number: '1',
      title: 'AI Agent',
      desc: 'Formulates structured payment intent',
      icon: <Bot className="w-4 h-4" />,
    },
    {
      id: 'POLICY',
      number: '2',
      title: 'Policy Engine',
      desc: 'Evaluates deterministic spending rules',
      icon: <ShieldCheck className="w-4 h-4" />,
    },
    {
      id: 'SERVICE',
      number: '3',
      title: 'Payment Service',
      desc: 'Orchestrates idempotency & fallback rails',
      icon: <Cpu className="w-4 h-4" />,
    },
    {
      id: 'PROVIDER',
      number: '4',
      title: 'Payment Provider',
      desc: 'Executes transaction via Razorpay / Mock',
      icon: <CreditCard className="w-4 h-4" />,
    },
    {
      id: 'RESULT',
      number: '5',
      title: 'Transaction Result',
      desc: 'Confirms settlement or triggers fallback',
      icon: <CheckCircle2 className="w-4 h-4" />,
    },
    {
      id: 'AUDIT',
      number: '6',
      title: 'Audit Log',
      desc: 'Records immutable verification trail',
      icon: <FileText className="w-4 h-4" />,
    },
  ]

  if (compact) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-[0_1px_3px_rgba(15,23,42,0.04)]">
        <div className="text-xs font-semibold text-slate-900 mb-3 flex items-center justify-between">
          <span>AgentPay Payment Lifecycle</span>
          <span className="text-[11px] font-normal text-slate-500">6-Stage Deterministic Flow</span>
        </div>
        <div className="flex flex-wrap items-center gap-1.5 sm:gap-2">
          {stages.map((stage, idx) => {
            const isActive = currentStage === 'ALL' || currentStage === stage.id
            return (
              <React.Fragment key={stage.id}>
                <div
                  className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-colors ${
                    isActive
                      ? 'bg-blue-50/70 border-blue-200 text-slate-800'
                      : 'bg-slate-50 border-slate-200 text-slate-500'
                  }`}
                >
                  <span className="text-[#305EFF]">{stage.icon}</span>
                  <span>{stage.title}</span>
                </div>
                {idx < stages.length - 1 && (
                  <ArrowRight className="w-3.5 h-3.5 text-slate-300 shrink-0" />
                )}
              </React.Fragment>
            )
          })}
        </div>
      </div>
    )
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)]">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-4 mb-6 border-b border-slate-100">
        <div>
          <h3 className="text-base font-semibold text-slate-900">
            Payment Lifecycle Architecture
          </h3>
          <p className="text-xs text-slate-500 mt-0.5">
            How AgentPay enforces deterministic human control between AI decisions and money movement
          </p>
        </div>
        <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-blue-50 text-[#305EFF] border border-blue-100 self-start sm:self-auto">
          Deterministic Flow
        </span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3">
        {stages.map((stage, idx) => {
          const isActive = currentStage === 'ALL' || currentStage === stage.id
          return (
            <div
              key={stage.id}
              className={`relative p-4 rounded-xl border flex flex-col justify-between transition-colors ${
                isActive
                  ? 'bg-white border-slate-200 shadow-[0_1px_3px_rgba(15,23,42,0.04)] hover:border-blue-300'
                  : 'bg-slate-50/60 border-slate-200/70 opacity-70'
              }`}
            >
              <div>
                <div className="flex items-center justify-between mb-3">
                  <div className="w-7 h-7 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-[#305EFF]">
                    {stage.icon}
                  </div>
                  <span className="text-[11px] font-semibold font-mono text-slate-400">
                    0{stage.number}
                  </span>
                </div>
                <h4 className="text-sm font-semibold text-slate-900 mb-1">
                  {stage.title}
                </h4>
                <p className="text-xs text-slate-500 leading-relaxed font-normal">
                  {stage.desc}
                </p>
              </div>

              {idx < stages.length - 1 && (
                <div className="hidden xl:block absolute -right-2 top-1/2 -translate-y-1/2 z-10">
                  <div className="w-4 h-4 rounded-full bg-white border border-slate-200 flex items-center justify-center shadow-xs">
                    <ArrowRight className="w-2.5 h-2.5 text-slate-400" />
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
