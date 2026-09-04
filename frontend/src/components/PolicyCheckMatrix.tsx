import React from 'react'
import { CheckCircle2, XCircle, Shield } from 'lucide-react'
import type { PolicyRuleCheck } from '../types'

interface PolicyCheckMatrixProps {
  rulesChecked?: PolicyRuleCheck[] | null
  decisionReason?: string | null
  decisionCode?: string | null
  isApproved?: boolean
}

export const PolicyCheckMatrix: React.FC<PolicyCheckMatrixProps> = ({
  rulesChecked,
  decisionReason,
  decisionCode,
  isApproved,
}) => {
  if (!rulesChecked || rulesChecked.length === 0) {
    if (!decisionReason) return null

    return (
      <div className="bg-slate-50/80 border border-slate-200/80 rounded-xl p-4">
        <div className="flex items-center gap-2 mb-2">
          <Shield className="w-4 h-4 text-[#305EFF]" />
          <span className="text-xs font-bold text-[#0d1b3e] uppercase tracking-wider">
            Deterministic Policy Engine Evaluation
          </span>
        </div>
        <div className="flex items-start gap-2.5 mt-2 text-xs">
          {isApproved ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
          ) : (
            <XCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          )}
          <div>
            <div className="font-bold text-[#0d1b3e]">
              {decisionCode || (isApproved ? 'APPROVED' : 'REJECTED')}
            </div>
            <div className="text-slate-600 mt-0.5 font-medium">{decisionReason}</div>
          </div>
        </div>
      </div>
    )
  }

  const formatRuleName = (rule: string) => {
    switch (rule.toUpperCase()) {
      case 'WALLET_STATUS':
        return 'Wallet Active Status'
      case 'TRANSACTION_LIMIT':
        return 'Per-Transaction Ceiling'
      case 'DAILY_SPENDING_LIMIT':
        return 'Daily Budget Limit'
      case 'CATEGORY_CHECK':
        return 'Merchant Category Allowed'
      case 'MERCHANT_CHECK':
        return 'Merchant Whitelist / Blocklist'
      default:
        return rule.replace(/_/g, ' ')
    }
  }

  return (
    <div className="bg-slate-50/80 border border-slate-200/80 rounded-xl p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <Shield className="w-4 h-4 text-[#305EFF]" />
          <span className="text-xs font-bold text-[#0d1b3e] uppercase tracking-wider">
            Deterministic Policy Engine Evaluation
          </span>
        </div>
        {decisionCode && (
          <span
            className={`text-[10px] font-bold px-2 py-0.5 rounded-md border ${
              isApproved
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-rose-50 text-rose-700 border-rose-200'
            }`}
          >
            {decisionCode}
          </span>
        )}
      </div>

      <div className="space-y-2">
        {rulesChecked.map((check, idx) => (
          <div
            key={idx}
            className={`flex items-start justify-between gap-3 p-2.5 rounded-lg border text-xs transition-all ${
              check.passed
                ? 'bg-white border-slate-200/80 text-slate-800'
                : 'bg-rose-50/80 border-rose-200 text-rose-900'
            }`}
          >
            <div className="flex items-start gap-2.5">
              {check.passed ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0 mt-0.5" />
              ) : (
                <XCircle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
              )}
              <div>
                <div className="font-bold text-slate-900">{formatRuleName(check.rule)}</div>
                <div className={`text-[11px] mt-0.5 font-medium ${check.passed ? 'text-slate-600' : 'text-rose-700'}`}>
                  {check.details}
                </div>
              </div>
            </div>

            <span
              className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded shrink-0 ${
                check.passed
                  ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                  : 'bg-rose-100 text-rose-800 border border-rose-200'
              }`}
            >
              {check.passed ? 'PASS' : 'FAIL'}
            </span>
          </div>
        ))}
      </div>

      {decisionReason && (
        <div className="pt-2 border-t border-slate-200/70 text-[11px] text-slate-600 leading-relaxed font-medium">
          <span className="font-bold text-slate-800">Policy Verdict: </span>
          {decisionReason}
        </div>
      )}
    </div>
  )
}
