import React, { useState } from 'react'
import {
  Wallet as WalletIcon,
  CreditCard,
  QrCode,
  CheckCircle2,
  RotateCcw,
  Layers,
  Check,
} from 'lucide-react'
import type { WalletSummary, PaymentMethodItem } from '../types'
import { api } from '../api/client'

interface WalletCardProps {
  wallet: WalletSummary | null
  loading?: boolean
  onWalletUpdated?: () => void
}

export const WalletCard: React.FC<WalletCardProps> = ({
  wallet,
  onWalletUpdated,
}) => {
  const [resetting, setResetting] = useState(false)
  const [resetSuccess, setResetSuccess] = useState(false)

  const currentSpent = wallet?.current_daily_spent ?? 0
  const dailyLimit = wallet?.daily_spending_limit ?? 15000
  const remainingBudget =
    wallet?.remaining_daily_budget ?? Math.max(0, dailyLimit - currentSpent)
  const perTxLimit = wallet?.per_transaction_limit ?? 8000

  const spentPercentage = Math.min(
    100,
    Math.round((currentSpent / (dailyLimit || 1)) * 100)
  )

  const handleResetDailySpend = async () => {
    setResetting(true)
    setResetSuccess(false)
    try {
      await api.resetDailySpend(wallet?.agent_id)
      setResetSuccess(true)
      if (onWalletUpdated) onWalletUpdated()
      setTimeout(() => setResetSuccess(false), 3000)
    } catch (err) {
      console.error('Failed to reset daily spend:', err)
      alert('Could not reset daily spend.')
    } finally {
      setResetting(false)
    }
  }

  // Helper to format masked display for rails
  const formatRailDisplay = (pm: PaymentMethodItem) => {
    if (pm.token_or_alias.includes('@')) {
      return pm.token_or_alias
    }
    if (pm.token_or_alias.includes('ending_')) {
      const last4 = pm.token_or_alias.split('ending_')[1]
      return `HDFC Corp •••• ${last4}`
    }
    if (pm.type === 'CARD_TOKEN') {
      return 'Corporate Visa •••• 4082'
    }
    return pm.token_or_alias
  }

  const paymentMethods: PaymentMethodItem[] = wallet?.payment_methods?.length
    ? wallet.payment_methods
    : [
        {
          id: '00000000-0000-0000-0000-000000000001',
          wallet_id: wallet?.id || '00000000-0000-0000-0000-000000000002',
          type: 'UPI_VPA',
          provider: 'mock',
          token_or_alias: 'krisha.agent@icici',
          is_primary: true,
          is_active: true,
          priority: 1,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
        {
          id: '00000000-0000-0000-0000-000000000002',
          wallet_id: wallet?.id || '00000000-0000-0000-0000-000000000002',
          type: 'CARD_TOKEN',
          provider: 'mock',
          token_or_alias: 'tok_hdfc_corp_ending_4082',
          is_primary: false,
          is_active: true,
          priority: 2,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        },
      ]

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)] space-y-5">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-[#305EFF] shrink-0">
            <WalletIcon className="w-4.5 h-4.5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-semibold text-slate-900 tracking-tight">
                Autonomous Wallet
              </h2>
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200/80">
                <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                {wallet?.status || 'ACTIVE'}
              </span>
            </div>
            <p className="text-xs text-slate-500 font-normal mt-0.5">
              Deterministic Spending Limits & Guardrails
            </p>
          </div>
        </div>

        {/* Per-transaction ceiling badge */}
        <div className="flex items-center gap-2 self-start sm:self-auto">
          <span className="px-2.5 py-1 rounded-md text-xs font-medium bg-slate-50 text-slate-700 border border-slate-200 whitespace-nowrap">
            Per-Tx Cap: ₹{perTxLimit.toLocaleString('en-IN')}
          </span>
        </div>
      </div>

      {/* 1. DAILY SPENDING METRICS */}
      <div className="bg-[#F8FAFC] border border-slate-200 rounded-xl p-4 space-y-3.5">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-slate-600">
            Daily Spending Summary
          </span>

          {/* Renew / Refresh Daily Spending Limit Option */}
          <button
            type="button"
            disabled={resetting}
            onClick={handleResetDailySpend}
            title="Renew daily spending limit (resets spent amount to ₹0 for testing)"
            className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium transition-colors cursor-pointer border ${
              resetSuccess
                ? 'bg-emerald-50 border-emerald-300 text-emerald-700'
                : 'bg-white hover:bg-slate-50 border-slate-200 text-slate-700'
            }`}
          >
            {resetting ? (
              <RotateCcw className="w-3 h-3 animate-spin text-[#305EFF]" />
            ) : resetSuccess ? (
              <Check className="w-3 h-3 text-emerald-600" />
            ) : (
              <RotateCcw className="w-3 h-3 text-slate-500" />
            )}
            <span>{resetSuccess ? 'Limit Renewed' : 'Renew Limit'}</span>
          </button>
        </div>

        {/* 3 Metric Columns */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 text-left">
          {/* Daily Spending */}
          <div className="bg-white p-3 rounded-lg border border-slate-200">
            <span className="text-[11px] font-normal text-slate-500 block mb-0.5">
              Daily Spent
            </span>
            <div className="text-base font-semibold text-slate-900 leading-tight whitespace-nowrap">
              ₹{currentSpent.toLocaleString('en-IN')}
            </div>
            <span className="text-[11px] text-slate-400 block mt-1">
              {spentPercentage}% of limit
            </span>
          </div>

          {/* Daily Limit */}
          <div className="bg-white p-3 rounded-lg border border-slate-200">
            <span className="text-[11px] font-normal text-slate-500 block mb-0.5">
              Daily Limit
            </span>
            <div className="text-base font-semibold text-[#305EFF] leading-tight whitespace-nowrap">
              ₹{dailyLimit.toLocaleString('en-IN')}
            </div>
            <span className="text-[11px] text-slate-400 block mt-1">
              Policy ceiling
            </span>
          </div>

          {/* Remaining */}
          <div className="bg-white p-3 rounded-lg border border-slate-200">
            <span className="text-[11px] font-normal text-slate-500 block mb-0.5">
              Remaining
            </span>
            <div
              className={`text-base font-semibold leading-tight whitespace-nowrap ${
                remainingBudget > 0 ? 'text-emerald-700' : 'text-rose-600'
              }`}
            >
              ₹{remainingBudget.toLocaleString('en-IN')}
            </div>
            <span className="text-[11px] text-slate-400 block mt-1">
              Available today
            </span>
          </div>
        </div>

        {/* Progress Bar */}
        <div className="space-y-1 pt-1">
          <div className="w-full bg-slate-200 rounded-full h-1.5 overflow-hidden">
            <div
              className={`h-full rounded-full transition-all duration-500 ease-out ${
                spentPercentage >= 90
                  ? 'bg-rose-500'
                  : spentPercentage >= 60
                  ? 'bg-amber-500'
                  : 'bg-[#305EFF]'
              }`}
              style={{ width: `${spentPercentage}%` }}
            />
          </div>
        </div>
      </div>

      {/* 2. CONFIGURED PAYMENT RAILS SECTION */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-[#305EFF]" />
            <h3 className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
              Configured Payment Rails
            </h3>
          </div>
          <span className="text-xs text-slate-500 font-normal">
            {paymentMethods.length} Active Rails
          </span>
        </div>

        {/* Single-column full width rail cards */}
        <div className="space-y-2.5">
          {paymentMethods.map((pm, index) => {
            const isPrimary = pm.is_primary || pm.priority === 1
            const isUPI = pm.type === 'UPI_VPA'
            const displayMasked = formatRailDisplay(pm)

            return (
              <div
                key={pm.id || index}
                className={`p-3.5 rounded-xl border transition-colors ${
                  isPrimary
                    ? 'bg-white border-blue-200 shadow-xs ring-1 ring-blue-100'
                    : 'bg-white border-slate-200'
                }`}
              >
                {/* Line 1: Type + Role Badge */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-6 h-6 rounded-md flex items-center justify-center shrink-0 ${
                        isUPI
                          ? 'bg-emerald-50 text-emerald-600 border border-emerald-100'
                          : 'bg-blue-50 text-[#305EFF] border border-blue-100'
                      }`}
                    >
                      {isUPI ? (
                        <QrCode className="w-3.5 h-3.5" />
                      ) : (
                        <CreditCard className="w-3.5 h-3.5" />
                      )}
                    </div>
                    <span className="text-xs font-semibold text-slate-900">
                      {isUPI ? 'UPI Virtual Address' : pm.type === 'CARD_TOKEN' ? 'Tokenized Card' : pm.type}
                    </span>
                  </div>

                  {/* Priority / Role Badge */}
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-medium shrink-0 ${
                      isPrimary
                        ? 'bg-blue-50 text-[#305EFF] border border-blue-100'
                        : 'bg-slate-100 text-slate-600 border border-slate-200'
                    }`}
                  >
                    {isPrimary ? 'Primary Rail' : 'Fallback Rail'}
                  </span>
                </div>

                {/* Line 2: Dedicated Alias Line */}
                <div className="mt-2 text-xs font-medium text-slate-800 bg-slate-50 px-2.5 py-1.5 rounded-md border border-slate-100">
                  <span title={displayMasked}>{displayMasked}</span>
                </div>

                {/* Line 3: Footer Status & ID */}
                <div className="mt-2 pt-2 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
                  <span>ID: {pm.id ? pm.id.substring(0, 8) : 'N/A'}</span>
                  <span className="flex items-center gap-1 font-medium text-emerald-600">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                    {pm.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
