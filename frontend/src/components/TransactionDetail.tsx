import React from 'react'
import {
  X,
  Bot,
  ShieldCheck,
  CreditCard,
  RotateCcw,
  XCircle,
  Zap,
  Layers,
  FileText,
} from 'lucide-react'
import { StatusBadge } from './StatusBadge'
import { PolicyCheckMatrix } from './PolicyCheckMatrix'
import { Timeline } from './Timeline'
import type { TransactionDetail as TransactionDetailType } from '../types'

interface TransactionDetailProps {
  transaction: TransactionDetailType | null
  loading?: boolean
  onClose: () => void
}

export const TransactionDetail: React.FC<TransactionDetailProps> = ({
  transaction,
  onClose,
}) => {
  if (!transaction) return null

  const isRejected = transaction.status === 'REJECTED'

  const attempts = transaction.payment_attempts || []
  const auditLogs = transaction.audit_logs || []

  // Extract policy checks from audit logs if available
  const policyLog = auditLogs.find((log) => log.event_type.includes('POLICY') && log.rules_checked)
  const rulesChecked = policyLog?.rules_checked || null

  // Fallback data
  const hasFallback = attempts.length > 1 || auditLogs.some((l) => l.event_type.includes('FALLBACK'))
  const fallbackAttempt = attempts.find((a) => a.attempt_number === 2)
  const primaryAttempt = attempts.find((a) => a.attempt_number === 1)

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-xs flex items-center justify-center p-3 sm:p-6 overflow-y-auto animate-in fade-in duration-200">
      <div className="bg-white border border-slate-200 rounded-xl shadow-xl max-w-4xl w-full max-h-[90vh] flex flex-col overflow-hidden relative">
        {/* Modal Header */}
        <div className="p-5 sm:p-6 border-b border-slate-100 flex items-center justify-between bg-white sticky top-0 z-20">
          <div className="flex items-center gap-3.5">
            <div className="w-9 h-9 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-[#305EFF] shrink-0">
              <Zap className="w-4.5 h-4.5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono font-medium text-slate-500">
                  TX #{transaction.id.substring(0, 8).toUpperCase()}
                </span>
                <StatusBadge status={transaction.status} size="sm" />
              </div>
              <h2 className="text-base sm:text-lg font-semibold text-slate-900 tracking-tight mt-0.5">
                {transaction.merchant_name} — ₹{transaction.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
              </h2>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 text-slate-500 hover:text-slate-800 transition-colors cursor-pointer"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Modal Body */}
        <div className="p-5 sm:p-6 overflow-y-auto space-y-6 flex-1 text-xs">
          {/* Architecture Visual Step-by-Step Flow */}
          <div className="p-4 rounded-xl bg-slate-50 border border-slate-200">
            <span className="text-xs font-semibold text-slate-700 block mb-2.5 uppercase tracking-wider">
              Payment Lifecycle Execution Flow
            </span>
            <div className="flex flex-wrap items-center gap-2 text-xs font-medium">
              <span className="px-2.5 py-1.5 rounded-lg bg-white text-slate-800 border border-slate-200 flex items-center gap-1.5">
                <Bot className="w-3.5 h-3.5 text-[#305EFF]" /> AI Agent
              </span>
              <span className="text-slate-300">→</span>
              <span className="px-2.5 py-1.5 rounded-lg bg-white text-slate-800 border border-slate-200 flex items-center gap-1.5">
                <FileText className="w-3.5 h-3.5 text-[#305EFF]" /> Structured Intent
              </span>
              <span className="text-slate-300">→</span>
              <span
                className={`px-2.5 py-1.5 rounded-lg border flex items-center gap-1.5 ${
                  isRejected
                    ? 'bg-rose-50 text-rose-800 border-rose-200'
                    : 'bg-emerald-50 text-emerald-800 border-emerald-200'
                }`}
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                Policy Engine ({isRejected ? 'REJECTED' : 'APPROVED'})
              </span>
              {hasFallback && (
                <>
                  <span className="text-slate-300">→</span>
                  <span className="px-2.5 py-1.5 rounded-lg bg-rose-50 text-rose-800 border border-rose-200 flex items-center gap-1.5">
                    <XCircle className="w-3.5 h-3.5 text-rose-600" /> UPI Declined
                  </span>
                  <span className="text-slate-300">→</span>
                  <span className="px-2.5 py-1.5 rounded-lg bg-blue-50 text-[#305EFF] border border-blue-200 flex items-center gap-1.5">
                    <RotateCcw className="w-3.5 h-3.5" /> Fallback Re-Check
                  </span>
                  <span className="text-slate-300">→</span>
                  <span className="px-2.5 py-1.5 rounded-lg bg-emerald-50 text-emerald-800 border border-emerald-200 flex items-center gap-1.5">
                    <CreditCard className="w-3.5 h-3.5 text-emerald-600" /> Card Settled
                  </span>
                </>
              )}
            </div>
          </div>

          {/* Section 1: AI Agent Request & Structured Intent */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-3">
            <div className="flex items-center gap-2">
              <Bot className="w-4 h-4 text-[#305EFF]" />
              <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider">
                1. AI Agent Request & Intent
              </h4>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 pt-1">
              <div className="p-3 bg-white rounded-lg border border-slate-200">
                <span className="text-slate-400 block text-[11px]">Merchant</span>
                <span className="font-semibold text-slate-900 text-xs mt-0.5 block">{transaction.merchant_name}</span>
              </div>
              <div className="p-3 bg-white rounded-lg border border-slate-200">
                <span className="text-slate-400 block text-[11px]">Requested Amount</span>
                <span className="font-semibold text-slate-900 text-xs mt-0.5 block">
                  ₹{transaction.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                </span>
              </div>
              <div className="p-3 bg-white rounded-lg border border-slate-200">
                <span className="text-slate-400 block text-[11px]">Spending Category</span>
                <span className="font-semibold text-slate-900 text-xs mt-0.5 block capitalize">{transaction.category}</span>
              </div>
              <div className="p-3 bg-white rounded-lg border border-slate-200">
                <span className="text-slate-400 block text-[11px]">Idempotency Key</span>
                <span className="font-mono text-slate-700 text-[11px] mt-0.5 block truncate" title={transaction.idempotency_key}>
                  {transaction.idempotency_key}
                </span>
              </div>
            </div>
          </div>

          {/* Section 2: Deterministic Policy Engine */}
          <div className="space-y-2">
            <PolicyCheckMatrix
              rulesChecked={rulesChecked}
              decisionReason={transaction.decision_reason}
              decisionCode={isRejected ? 'REJECTED' : 'APPROVED'}
              isApproved={!isRejected}
            />
          </div>

          {/* Section 3: Payment Execution Attempts & Fallback */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <CreditCard className="w-4 h-4 text-[#305EFF]" />
                <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider">
                  2. Payment Provider Execution & Attempts
                </h4>
              </div>
              <span className="text-xs text-slate-500 font-normal">
                Total Attempts: <span className="font-semibold text-slate-900">{attempts.length}</span>
              </span>
            </div>

            {isRejected && attempts.length === 0 ? (
              <div className="p-4 rounded-lg bg-rose-50 border border-rose-200 text-rose-800">
                <div className="flex items-center gap-2 font-semibold text-xs">
                  <ShieldCheck className="w-4 h-4 text-rose-600" />
                  Policy Engine Guard Triggered
                </div>
                <p className="mt-1 text-xs text-rose-700 leading-relaxed font-normal">
                  The payment request was blocked by the Policy Engine. As per security invariants, payment providers were NEVER invoked and zero provider attempts were executed.
                </p>
              </div>
            ) : attempts.length === 0 ? (
              <div className="py-4 text-center text-slate-400 text-xs">
                No payment attempts recorded for this transaction.
              </div>
            ) : (
              <div className="space-y-3">
                {/* Attempt 1 / Primary Rail */}
                {primaryAttempt && (
                  <div
                    className={`p-3.5 rounded-lg border ${
                      primaryAttempt.status === 'SUCCESS'
                        ? 'bg-emerald-50/60 border-emerald-200'
                        : 'bg-rose-50/60 border-rose-200'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2 mb-2">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-900 text-xs">
                          {hasFallback ? 'Primary Rail' : 'Payment Rail'}: {transaction.payment_provider === 'RAZORPAY' ? 'Razorpay Gateway' : primaryAttempt.payment_method_type || 'UPI_VPA'}
                        </span>
                        {transaction.payment_provider === 'RAZORPAY' && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-blue-100 text-blue-800 border border-blue-200">
                            Razorpay Test Mode
                          </span>
                        )}
                        {hasFallback && (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-rose-100 text-rose-800 border border-rose-200">
                            DECLINED
                          </span>
                        )}
                      </div>
                      <StatusBadge status={primaryAttempt.status} size="sm" />
                    </div>

                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-slate-600">
                      <div>Configured Rail: <span className="text-slate-900 font-medium">{primaryAttempt.payment_method_type || 'UPI_VPA'}</span></div>
                      <div>Identifier / Alias: <span className="text-slate-900 font-medium">{primaryAttempt.payment_method_alias || primaryAttempt.payment_method_id || 'krisha.agent@icici'}</span></div>
                      <div>Provider Ref: <span className="text-[#305EFF] font-medium">{primaryAttempt.provider_payment_id || transaction.provider_payment_id || (primaryAttempt.status === 'FAILED' ? 'N/A' : 'Settled')}</span></div>
                      {primaryAttempt.error_code && (
                        <div className="col-span-full text-rose-600 font-mono text-[11px]">
                          Failure Reason: {primaryAttempt.error_code} ({primaryAttempt.error_message || 'Rail declined transaction'})
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Fallback & Attempt 2 */}
                {hasFallback && fallbackAttempt && (
                  <div className="space-y-2">
                    {/* Fallback Bridge Visual */}
                    <div className="flex items-center justify-center py-1.5 gap-2 text-xs font-medium text-slate-700 bg-slate-100 border border-slate-200 rounded-lg">
                      <RotateCcw className="w-3.5 h-3.5 text-[#305EFF]" />
                      <span>Primary Rail Declined ➔ Fallback Rail Policy Evaluated ➔ Settled</span>
                    </div>

                    <div className="p-3.5 rounded-lg border bg-emerald-50/60 border-emerald-200">
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="flex items-center gap-2">
                          <RotateCcw className="w-3.5 h-3.5 text-[#305EFF]" />
                          <span className="font-semibold text-slate-900 text-xs">
                            Fallback Rail: {fallbackAttempt.payment_method_type || 'CARD_TOKEN'} (Attempt #2)
                          </span>
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-medium bg-emerald-100 text-emerald-800 border border-emerald-200">
                            POLICY CHECK: ✓ APPROVED
                          </span>
                        </div>
                        <StatusBadge status={fallbackAttempt.status} size="sm" />
                      </div>

                      <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs text-slate-600">
                        <div>Configured Rail: <span className="text-slate-900 font-medium">{fallbackAttempt.payment_method_type || 'CARD_TOKEN'}</span></div>
                        <div>Identifier / Alias: <span className="text-slate-900 font-medium">{fallbackAttempt.payment_method_alias || fallbackAttempt.payment_method_id || 'HDFC Corp •••• 4082'}</span></div>
                        <div>Provider ID: <span className="text-emerald-700 font-medium">{fallbackAttempt.provider_payment_id || 'Settled'}</span></div>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Section 4: Audit Timeline */}
          <div className="bg-slate-50 border border-slate-200 rounded-xl p-4 space-y-4">
            <div className="flex items-center gap-2">
              <Layers className="w-4 h-4 text-[#305EFF]" />
              <h4 className="text-xs font-semibold text-slate-800 uppercase tracking-wider">
                3. Immutable Audit Log Trail
              </h4>
            </div>

            <Timeline auditLogs={auditLogs} paymentAttempts={attempts} />
          </div>
        </div>

        {/* Modal Footer */}
        <div className="p-4 border-t border-slate-100 bg-white flex items-center justify-between text-xs">
          <div className="text-slate-500 text-[11px]">
            Created: {new Date(transaction.created_at).toLocaleString('en-IN')}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="px-4 py-2 rounded-lg bg-slate-900 hover:bg-slate-800 text-white font-medium transition-colors cursor-pointer"
          >
            Close Detail
          </button>
        </div>
      </div>
    </div>
  )
}
