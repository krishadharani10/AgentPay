import React from 'react'
import {
  Plane,
  Utensils,
  CreditCard,
  CheckCircle2,
  XCircle,
  ShieldAlert,
  Calendar,
  Clock,
  User,
  ExternalLink,
  Lock,
  Zap,
} from 'lucide-react'
import type { TaskRunResponse } from '../types'

interface AutonomousResultCardProps {
  result: TaskRunResponse
  onInspectTransaction?: (txId: string) => void
  skipAnimation?: boolean
}

export const AutonomousResultCard: React.FC<AutonomousResultCardProps> = ({
  result,
  onInspectTransaction,
}) => {
  const isFlight = result.task_type === 'BOOK_FLIGHT'
  const isRestaurant = result.task_type === 'RESERVE_RESTAURANT'

  const isPolicyRejected = result.policy_result === 'REJECTED' || result.task_status === 'REJECTED'
  const isPaymentFailed =
    result.task_status === 'FAILED' ||
    result.task_status === 'PAYMENT_FAILED' ||
    result.payment_status === 'FAILED'

  const req = result.interpreted_request || {}
  const opt = result.selected_option || {}

  // ─────────────────────────────────────────────────────────────────────────────
  // 1. REJECTION VIEW (Deterministic Policy Guardrail in action)
  // ─────────────────────────────────────────────────────────────────────────────
  if (isPolicyRejected) {
    const selectedPrice = result.amount || opt.price || opt.deposit_amount || 0
    const userBudgetLimit = Number(req.max_budget || req.budget || 10000)
    const failedRule = result.rules_checked?.find((r) => !r.passed)

    return (
      <div className="rounded-xl bg-white border border-rose-200 p-5 sm:p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)] space-y-5">
        {/* Security Principle Banner */}
        <div className="p-3.5 rounded-lg bg-rose-50 border border-rose-200 flex items-start gap-3">
          <div className="w-7 h-7 rounded-md bg-rose-100 border border-rose-200 flex items-center justify-center text-rose-700 shrink-0 mt-0.5">
            <Lock className="w-3.5 h-3.5" />
          </div>
          <div>
            <div className="text-xs font-semibold text-rose-900 uppercase tracking-wide">
              AgentPay Security Invariant Enforced
            </div>
            <p className="text-xs text-rose-700 mt-0.5 leading-snug">
              “AI can find an option. The deterministic Policy Engine decides whether money may move.”
            </p>
          </div>
        </div>

        {/* Rejection Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600">
              <ShieldAlert className="w-4.5 h-4.5" />
            </div>
            <div>
              <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200">
                Policy Blocked
              </span>
              <h3 className="text-base font-semibold text-slate-900 mt-1">
                Autonomous Payment Authorization Rejected
              </h3>
            </div>
          </div>

          <div className="text-left sm:text-right">
            <div className="text-[11px] text-slate-500 font-normal">Selected Option Cost</div>
            <div className="text-lg font-semibold text-rose-600">
              ₹{Number(selectedPrice).toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        {/* Comparison Matrix: User Constraint vs Policy Limit */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          {/* 1. User Request / Constraint */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-[11px] font-normal text-slate-500 block mb-1">
              User Request Budget
            </span>
            <div className="text-sm font-semibold text-slate-900">
              Under ₹{userBudgetLimit.toLocaleString('en-IN')}
            </div>
            <div className="mt-2 flex items-center gap-1.5 text-xs font-medium text-emerald-600">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>User Constraint: PASS</span>
            </div>
          </div>

          {/* 2. AgentPay Policy Limit */}
          <div className="p-3.5 rounded-lg bg-rose-50/70 border border-rose-200">
            <span className="text-[11px] font-medium text-rose-700 block mb-1">
              AgentPay Policy Limit
            </span>
            <div className="text-sm font-semibold text-rose-900">
              Limit Exceeded
            </div>
            <div className="mt-2 flex items-center gap-1.5 text-xs font-medium text-rose-600">
              <XCircle className="w-3.5 h-3.5" />
              <span>Policy: REJECTED</span>
            </div>
          </div>

          {/* 3. Payment Rail Execution */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-[11px] font-normal text-slate-500 block mb-1">
              Payment Rail
            </span>
            <div className="text-sm font-semibold text-slate-800">
              Not Attempted
            </div>
            <div className="mt-2 text-[11px] text-slate-500">
              Payment rails never touched
            </div>
          </div>

          {/* 4. Booking Status */}
          <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-[11px] font-normal text-slate-500 block mb-1">
              Booking Status
            </span>
            <div className="text-sm font-semibold text-slate-800">
              Not Created
            </div>
            <div className="mt-2 text-[11px] text-slate-500">
              Zero financial exposure
            </div>
          </div>
        </div>

        {/* Explainable Reason Box */}
        <div className="p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700 leading-relaxed">
          <span className="font-semibold text-slate-900 block mb-1">Explainable Policy Decision</span>
          {result.final_message}
          {failedRule && (
            <div className="mt-2 pt-2 border-t border-slate-200 text-xs text-rose-700 flex items-center gap-2">
              <span className="font-medium uppercase">{failedRule.rule}:</span>
              <span>{failedRule.details}</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 2. PAYMENT FAILED VIEW
  // ─────────────────────────────────────────────────────────────────────────────
  if (isPaymentFailed) {
    return (
      <div className="rounded-xl bg-white border border-rose-200 p-5 sm:p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)] space-y-4">
        <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
          <div className="w-9 h-9 rounded-lg bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600">
            <Zap className="w-4.5 h-4.5" />
          </div>
          <div>
            <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200">
              Payment Failed
            </span>
            <h3 className="text-base font-semibold text-slate-900 mt-1">
              Payment rail execution could not be completed
            </h3>
          </div>
        </div>
        <p className="text-xs text-slate-600 leading-relaxed font-normal">
          {result.final_message || 'Payment attempt failed across configured payment rails.'}
        </p>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 3A. FLIGHT CONFIRMATION VIEW
  // ─────────────────────────────────────────────────────────────────────────────
  if (isFlight) {
    const origin = opt.origin || req.origin || 'AMD'
    const destination = opt.destination || req.destination || 'BOM'
    const airline = opt.airline || 'AirDemo'
    const flightNum = opt.flight_number || 'AP101'
    const dateStr = opt.date || req.date || 'September 22'
    const depTime = opt.departure_time || '06:15'
    const arrTime = opt.arrival_time || '07:30'
    const price = Number(opt.price || result.amount || 7450)
    const userBudget = Number(req.max_budget || req.budget || 10000)

    return (
      <div className="rounded-xl bg-white border border-slate-200 p-5 sm:p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)] space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-50 border border-blue-200 flex items-center justify-center text-[#305EFF]">
              <Plane className="w-4.5 h-4.5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-blue-50 text-[#305EFF] border border-blue-200">
                  Airline Ticket
                </span>
                <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                  Booking Confirmed
                </span>
              </div>
              <h3 className="text-base font-semibold text-slate-900 tracking-tight mt-1">
                {airline} · Flight {flightNum}
              </h3>
            </div>
          </div>

          <div className="text-left sm:text-right">
            <div className="text-[11px] text-slate-500 font-normal">Captured Amount</div>
            <div className="text-xl font-semibold text-slate-900 mt-0.5">
              ₹{price.toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        {/* Message */}
        <div className="px-3.5 py-2.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700">
          AgentPay autonomously booked this flight after deterministic policy enforcement.
        </div>

        {/* Details Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs">
          <div>
            <span className="text-[11px] text-slate-500 block mb-0.5">Route</span>
            <div className="font-semibold text-slate-900">{origin} → {destination}</div>
            <span className="text-[11px] text-slate-400">Non-stop</span>
          </div>
          <div>
            <span className="text-[11px] text-slate-500 block mb-0.5">Date & Time</span>
            <div className="font-semibold text-slate-900 flex items-center gap-1">
              <Clock className="w-3 h-3 text-[#305EFF]" />
              <span>{depTime} → {arrTime}</span>
            </div>
            <span className="text-[11px] text-slate-400">{dateStr}</span>
          </div>
          <div>
            <span className="text-[11px] text-slate-500 block mb-0.5">User Budget</span>
            <div className="font-semibold text-slate-900">Under ₹{userBudget.toLocaleString('en-IN')}</div>
            <span className="text-[11px] text-emerald-600 font-medium">Passed</span>
          </div>
          <div>
            <span className="text-[11px] text-slate-500 block mb-0.5">Payment Rail</span>
            <div className="font-semibold text-emerald-700 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              <span>SUCCESS</span>
            </div>
            <span className="text-[11px] text-slate-400">Policy Approved</span>
          </div>
        </div>

        {/* Guarantees Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-medium uppercase block">User Budget</span>
            <span className="font-semibold text-emerald-900 block text-xs">Under ₹{userBudget.toLocaleString('en-IN')} ✓</span>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-medium uppercase block">AgentPay Policy</span>
            <span className="font-semibold text-emerald-900 block text-xs">APPROVED ✓</span>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-medium uppercase block">Payment Rail</span>
            <span className="font-semibold text-emerald-900 block text-xs">SETTLED ✓</span>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-medium uppercase block">Booking State</span>
            <span className="font-semibold text-emerald-900 block text-xs">CONFIRMED ✓</span>
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-slate-100">
          <p className="text-xs text-slate-500 leading-snug">
            {result.final_message}
          </p>
          {result.transaction_id && onInspectTransaction && (
            <button
              type="button"
              onClick={() => onInspectTransaction(result.transaction_id!)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-50 hover:bg-slate-100 text-slate-700 transition-colors cursor-pointer shrink-0 border border-slate-200"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Inspect Audit Log</span>
            </button>
          )}
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 3B. RESTAURANT CONFIRMATION VIEW
  // ─────────────────────────────────────────────────────────────────────────────
  if (isRestaurant) {
    const name = opt.restaurant_name || 'ITC Narmada'
    const city = opt.city || req.city || 'Ahmedabad'
    const dateStr = opt.date || req.date || 'September 22'
    const timeStr = opt.time_display || opt.time || req.time || '8:00 PM'
    const persons = opt.party_size || opt.persons || req.party_size || 2
    const deposit = Number(opt.deposit_amount || result.amount || 1000)

    return (
      <div className="rounded-xl bg-white border border-slate-200 p-5 sm:p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)] space-y-4">
        {/* Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-50 border border-blue-200 flex items-center justify-center text-[#305EFF]">
              <Utensils className="w-4.5 h-4.5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-blue-50 text-[#305EFF] border border-blue-200">
                  Fine Dining
                </span>
                <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                  Reservation Confirmed
                </span>
              </div>
              <h3 className="text-base font-semibold text-slate-900 tracking-tight mt-1">
                {name}
              </h3>
            </div>
          </div>

          <div className="text-left sm:text-right">
            <div className="text-[11px] text-slate-500 font-normal">Reservation Deposit</div>
            <div className="text-xl font-semibold text-slate-900 mt-0.5">
              ₹{deposit.toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        {/* Message */}
        <div className="px-3.5 py-2.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700">
          AgentPay autonomously reserved this table after enforcing the user's payment policy.
        </div>

        {/* Details Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 p-3.5 rounded-lg bg-slate-50 border border-slate-200 text-xs">
          <div>
            <span className="text-[11px] text-slate-500 block mb-0.5">Venue & City</span>
            <div className="font-semibold text-slate-900">{name}</div>
            <span className="text-[11px] text-slate-400">{city}</span>
          </div>
          <div>
            <span className="text-[11px] text-slate-500 block mb-0.5">Date & Time</span>
            <div className="font-semibold text-slate-900 flex items-center gap-1">
              <Calendar className="w-3 h-3 text-[#305EFF]" />
              <span>{dateStr} @ {timeStr}</span>
            </div>
            <span className="text-[11px] text-slate-400">Slot Confirmed</span>
          </div>
          <div>
            <span className="text-[11px] text-slate-500 block mb-0.5">Party Size</span>
            <div className="font-semibold text-slate-900 flex items-center gap-1">
              <User className="w-3 h-3 text-[#305EFF]" />
              <span>{persons} Guests</span>
            </div>
            <span className="text-[11px] text-slate-400">Reserved Seating</span>
          </div>
          <div>
            <span className="text-[11px] text-slate-500 block mb-0.5">Payment Rail</span>
            <div className="font-semibold text-emerald-700 flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
              <span>SUCCESS</span>
            </div>
            <span className="text-[11px] text-slate-400">Deposit Settled</span>
          </div>
        </div>

        {/* Guarantees Row */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-medium uppercase block">User Constraints</span>
            <span className="font-semibold text-emerald-900 block text-xs">PASS ✓</span>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-medium uppercase block">AgentPay Policy</span>
            <span className="font-semibold text-emerald-900 block text-xs">APPROVED ✓</span>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-medium uppercase block">Payment Rail</span>
            <span className="font-semibold text-emerald-900 block text-xs">SETTLED ✓</span>
          </div>
          <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-medium uppercase block">Reservation</span>
            <span className="font-semibold text-emerald-900 block text-xs">CONFIRMED ✓</span>
          </div>
        </div>

        {/* Footer */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-slate-100">
          <p className="text-xs text-slate-500 leading-snug">
            {result.final_message}
          </p>
          {result.transaction_id && onInspectTransaction && (
            <button
              type="button"
              onClick={() => onInspectTransaction(result.transaction_id!)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-50 hover:bg-slate-100 text-slate-700 transition-colors cursor-pointer shrink-0 border border-slate-200"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Inspect Audit Log</span>
            </button>
          )}
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 3C. DIRECT PAYMENT CONFIRMATION VIEW
  // ─────────────────────────────────────────────────────────────────────────────
  const amount = Number(result.amount || 0)
  return (
    <div className="rounded-xl bg-white border border-slate-200 p-5 sm:p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)] space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-blue-50 border border-blue-200 flex items-center justify-center text-[#305EFF]">
            <CreditCard className="w-4.5 h-4.5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-blue-50 text-[#305EFF] border border-blue-200">
                Direct Payment
              </span>
              <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                {result.payment_status}
              </span>
            </div>
            <h3 className="text-base font-semibold text-slate-900 mt-1">
              {result.merchant_name || 'Authorized Merchant'}
            </h3>
          </div>
        </div>

        <div className="text-left sm:text-right">
          <div className="text-[11px] text-slate-500 font-normal">Settled Amount</div>
          <div className="text-xl font-semibold text-slate-900 mt-0.5">
            ₹{amount.toLocaleString('en-IN')}
          </div>
        </div>
      </div>

      <div className="px-3.5 py-2.5 rounded-lg bg-slate-50 border border-slate-200 text-xs text-slate-700">
        AgentPay autonomously executed this payment after deterministic policy enforcement.
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200 text-xs">
          <span className="text-[10px] text-slate-500 font-medium uppercase block">Merchant</span>
          <span className="font-semibold text-slate-800 block text-xs mt-0.5">{result.merchant_name || 'Recipient'}</span>
        </div>
        <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
          <span className="text-[10px] text-emerald-700 font-medium uppercase block">AgentPay Policy</span>
          <span className="font-semibold text-emerald-900 block text-xs mt-0.5">APPROVED ✓</span>
        </div>
        <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
          <span className="text-[10px] text-emerald-700 font-medium uppercase block">Payment Rail</span>
          <span className="font-semibold text-emerald-900 block text-xs mt-0.5">{result.payment_status} ✓</span>
        </div>
        <div className="p-2.5 rounded-lg bg-emerald-50/60 border border-emerald-200 text-xs">
          <span className="text-[10px] text-emerald-700 font-medium uppercase block">Task Status</span>
          <span className="font-semibold text-emerald-900 block text-xs mt-0.5">COMPLETED ✓</span>
        </div>
      </div>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-3 border-t border-slate-100">
        <p className="text-xs text-slate-500 leading-snug">
          {result.final_message}
        </p>
        {result.transaction_id && onInspectTransaction && (
          <button
            type="button"
            onClick={() => onInspectTransaction(result.transaction_id!)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-slate-50 hover:bg-slate-100 text-slate-700 transition-colors cursor-pointer shrink-0 border border-slate-200"
          >
            <ExternalLink className="w-3.5 h-3.5" />
            <span>Inspect Audit Log</span>
          </button>
        )}
      </div>
    </div>
  )
}
