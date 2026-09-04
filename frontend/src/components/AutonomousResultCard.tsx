import React, { useState, useEffect } from 'react'
import {
  Plane,
  Utensils,
  CreditCard,
  CheckCircle2,
  XCircle,
  ArrowRight,
  ShieldAlert,
  Calendar,
  Clock,
  User,
  ExternalLink,
  Lock,
  Sparkles,
  Zap,
  Check,
  ShieldCheck,
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
  skipAnimation = false,
}) => {
  const isFlight = result.task_type === 'BOOK_FLIGHT'
  const isRestaurant = result.task_type === 'RESERVE_RESTAURANT'

  const isPolicyRejected = result.policy_result === 'REJECTED' || result.task_status === 'REJECTED'
  const isPaymentFailed =
    result.task_status === 'FAILED' ||
    result.task_status === 'PAYMENT_FAILED' ||
    result.payment_status === 'FAILED'

  const isSuccess =
    !isPolicyRejected &&
    !isPaymentFailed &&
    result.task_status === 'COMPLETED' &&
    result.payment_status === 'SUCCESS'

  // Finalizing step state:
  // 1: Payment verified (0s - 1.2s)
  // 2: Transaction secured (1.2s - 2.4s)
  // 3: Finalizing booking/reservation (2.4s - 3.7s)
  // 4: Confirmation received (3.7s - 4.8s)
  // 5: Final Confirmed Experience (4.8s+)
  const [finalizingStep, setFinalizingStep] = useState<number>(() => {
    if (!isSuccess || skipAnimation) return 5
    return 1
  })

  useEffect(() => {
    if (!isSuccess || skipAnimation) {
      setFinalizingStep(5)
      return
    }

    setFinalizingStep(1)

    const timer1 = setTimeout(() => {
      setFinalizingStep(2)
    }, 1200)

    const timer2 = setTimeout(() => {
      setFinalizingStep(3)
    }, 2400)

    const timer3 = setTimeout(() => {
      setFinalizingStep(4)
    }, 3700)

    const timer4 = setTimeout(() => {
      setFinalizingStep(5)
    }, 4800)

    return () => {
      clearTimeout(timer1)
      clearTimeout(timer2)
      clearTimeout(timer3)
      clearTimeout(timer4)
    }
  }, [result.transaction_id, isSuccess, skipAnimation])

  const req = result.interpreted_request || {}
  const opt = result.selected_option || {}

  // ─────────────────────────────────────────────────────────────────────────────
  // 1. REJECTION VIEW (Only for Policy Rejections — No Finalizing / Celebration)
  // ─────────────────────────────────────────────────────────────────────────────
  if (isPolicyRejected) {
    const selectedPrice = result.amount || opt.price || opt.deposit_amount || 0
    const userBudgetLimit = Number(req.max_budget || req.budget || 10000)
    const failedRule = result.rules_checked?.find((r) => !r.passed)

    return (
      <div className="rounded-2xl bg-white border-2 border-rose-200 p-6 shadow-xs animate-in fade-in slide-in-from-top-3 duration-300">
        {/* Security Principle Banner */}
        <div className="mb-5 p-3.5 rounded-xl bg-rose-50 border border-rose-200 flex items-start gap-3">
          <div className="w-8 h-8 rounded-lg bg-rose-100 border border-rose-200 flex items-center justify-center text-rose-700 shrink-0 mt-0.5">
            <Lock className="w-4 h-4" />
          </div>
          <div>
            <div className="text-xs font-bold text-rose-900 uppercase tracking-wide flex items-center gap-2">
              AgentPay Security Invariant Enforced
            </div>
            <p className="text-xs text-rose-700 font-medium mt-0.5 leading-snug">
              “AI can find an option. AgentPay decides whether money may move.”
            </p>
          </div>
        </div>

        {/* Rejection Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-rose-50 border border-rose-200 flex items-center justify-center text-rose-600">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div>
              <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-md bg-rose-50 text-rose-700 border border-rose-200">
                Policy Blocked
              </span>
              <h3 className="text-base font-bold text-slate-900 mt-1">
                Autonomous Payment Authorization Rejected
              </h3>
            </div>
          </div>

          <div className="text-right">
            <div className="text-[11px] text-slate-500">Selected Option Cost</div>
            <div className="text-lg font-mono font-bold text-rose-600">
              ₹{Number(selectedPrice).toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        {/* Comparison Matrix: User Constraint vs Policy Limit */}
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-3 my-5">
          {/* 1. User Request / Constraint */}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">
              User Request Budget
            </span>
            <div className="text-sm font-bold text-slate-900 font-mono">
              Under ₹{userBudgetLimit.toLocaleString('en-IN')}
            </div>
            <div className="mt-2 flex items-center gap-1.5 text-xs font-bold text-emerald-600">
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>User Constraint: PASS</span>
            </div>
          </div>

          {/* 2. AgentPay Policy Limit */}
          <div className="p-3.5 rounded-xl bg-rose-50/70 border border-rose-200">
            <span className="text-[10px] uppercase font-bold text-rose-700 block mb-1">
              AgentPay Policy Limit
            </span>
            <div className="text-sm font-bold text-rose-900 font-mono">
              Limit Exceeded
            </div>
            <div className="mt-2 flex items-center gap-1.5 text-xs font-bold text-rose-600">
              <XCircle className="w-3.5 h-3.5" />
              <span>Policy: REJECTED</span>
            </div>
          </div>

          {/* 3. Payment Rail Execution */}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">
              Payment Rail
            </span>
            <div className="text-sm font-bold text-slate-800">
              Not Attempted
            </div>
            <div className="mt-2 text-[11px] text-slate-500 font-medium">
              Payment rails never touched
            </div>
          </div>

          {/* 4. Booking Status */}
          <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
            <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">
              Booking / Reservation
            </span>
            <div className="text-sm font-bold text-slate-800">
              Not Created
            </div>
            <div className="mt-2 text-[11px] text-slate-500 font-medium">
              Zero financial exposure
            </div>
          </div>
        </div>

        {/* Explainable Reason Box */}
        <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 leading-relaxed">
          <span className="font-bold text-slate-900 block mb-1">Why was this rejected?</span>
          {result.final_message}
          {failedRule && (
            <div className="mt-2 pt-2 border-t border-slate-200 text-[11px] text-rose-700 flex items-center gap-2">
              <span className="font-mono font-bold uppercase">{failedRule.rule}</span>
              <span>— {failedRule.details}</span>
            </div>
          )}
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 2. PAYMENT FAILED VIEW (No Finalizing / Celebration)
  // ─────────────────────────────────────────────────────────────────────────────
  if (isPaymentFailed) {
    return (
      <div className="rounded-2xl bg-white border-2 border-amber-200 p-6 shadow-xs animate-in fade-in slide-in-from-top-3 duration-300">
        <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
          <div className="w-10 h-10 rounded-xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[10px] uppercase font-bold px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200">
              Payment Failed
            </span>
            <h3 className="text-base font-bold text-slate-900 mt-1">
              Payment rail execution could not be completed
            </h3>
          </div>
        </div>
        <p className="text-xs text-slate-600 mt-4 leading-relaxed">
          {result.final_message || 'Payment attempt failed across configured payment methods.'}
        </p>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 3. FINALIZING SEQUENCE (Steps 1 to 4: 4.8s Polished Fintech Animation)
  // ─────────────────────────────────────────────────────────────────────────────
  if (isSuccess && finalizingStep < 5) {
    const priceAmount = Number(result.amount || opt.price || opt.deposit_amount || 7450)
    const domainName = isFlight
      ? 'Flight AP101'
      : isRestaurant
      ? opt.restaurant_name || 'Restaurant Table'
      : result.merchant_name || 'Merchant'

    return (
      <div className="rounded-3xl bg-white border border-blue-200/90 p-6 sm:p-8 shadow-sm relative overflow-hidden animate-in fade-in duration-300">
        {/* Top Status Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-6">
          <div className="flex items-center gap-2.5">
            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-ping shrink-0" />
            <span className="text-xs font-mono font-bold uppercase tracking-wider text-emerald-700">
              Payment Authoritative & Verified
            </span>
          </div>
          <span className="text-[11px] font-mono text-slate-500 px-3 py-1 rounded-full bg-slate-100 border border-slate-200 shrink-0 self-start sm:self-auto">
            Securing Step {finalizingStep} of 4 · Finalizing Order
          </span>
        </div>

        {/* Center Animated Stage */}
        <div className="flex flex-col items-center justify-center my-6 sm:my-8 text-center">
          <div className="relative flex items-center justify-center mb-6">
            <div className="w-20 h-20 sm:w-24 sm:h-24 rounded-3xl bg-blue-50 border-2 border-blue-200 flex items-center justify-center text-blue-600 relative z-10 shadow-xs">
              {finalizingStep === 1 && <CreditCard className="w-10 h-10 text-blue-600 animate-pulse" />}
              {finalizingStep === 2 && <Lock className="w-10 h-10 text-emerald-600 animate-bounce" />}
              {finalizingStep === 3 && (
                isFlight ? (
                  <Plane className="w-10 h-10 text-blue-600 animate-pulse" />
                ) : isRestaurant ? (
                  <Utensils className="w-10 h-10 text-amber-600 animate-pulse" />
                ) : (
                  <ShieldCheck className="w-10 h-10 text-blue-600 animate-pulse" />
                )
              )}
              {finalizingStep === 4 && <Sparkles className="w-10 h-10 text-emerald-600 animate-spin" />}
            </div>
            {/* Pulsing radar waves */}
            <div className="absolute inset-0 rounded-3xl bg-blue-400/20 animate-ping opacity-30 scale-125 pointer-events-none" />
            <div className="absolute -inset-3 rounded-3xl border border-blue-200 animate-pulse pointer-events-none" />
          </div>

          <h3 className="text-lg sm:text-xl font-bold text-slate-900 tracking-tight">
            {finalizingStep === 1 && 'Payment Verified on Rails'}
            {finalizingStep === 2 && 'Transaction Secured in Ledger'}
            {finalizingStep === 3 && (
              isFlight
                ? 'Finalizing Flight Booking & E-Ticket...'
                : isRestaurant
                ? 'Finalizing Table Reservation Slot...'
                : 'Finalizing Direct Payment Settlement...'
            )}
            {finalizingStep === 4 && 'Confirmation Received & Validated'}
          </h3>

          <p className="text-xs text-slate-600 mt-1.5 max-w-md font-medium leading-relaxed">
            {finalizingStep === 1 &&
              `Deterministic policy check approved ₹${priceAmount.toLocaleString('en-IN')} with idempotency protection.`}
            {finalizingStep === 2 &&
              'Immutable audit record created and wallet ledger balance updated.'}
            {finalizingStep === 3 &&
              `Securing confirmed reservation for ${domainName} with verified merchant API.`}
            {finalizingStep === 4 &&
              'Merchant confirmed order successfully. Issuing official confirmation receipt...'}
          </p>
        </div>

        {/* Dynamic Progress Bar */}
        <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden mb-6 p-0.5 border border-slate-200">
          <div
            className="bg-gradient-to-r from-blue-600 via-sky-500 to-emerald-500 h-full rounded-full transition-all duration-700 ease-out shadow-xs"
            style={{ width: `${finalizingStep * 25}%` }}
          />
        </div>

        {/* 4-Step Checklist */}
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
          {/* 1. Payment verified */}
          <div
            className={`p-3.5 rounded-2xl border transition-all ${
              finalizingStep >= 1
                ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                : 'bg-slate-50 border-slate-200 text-slate-400'
            }`}
          >
            <div className="flex items-center gap-2">
              {finalizingStep >= 1 ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              ) : (
                <Clock className="w-4 h-4 text-slate-400 shrink-0" />
              )}
              <div className="text-xs font-bold">1. Payment verified</div>
            </div>
            <div className="text-[10px] text-slate-500 mt-1 pl-6">
              {finalizingStep >= 1 ? 'Approved by Policy' : 'Pending'}
            </div>
          </div>

          {/* 2. Transaction secured */}
          <div
            className={`p-3.5 rounded-2xl border transition-all ${
              finalizingStep >= 2
                ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                : 'bg-slate-50 border-slate-200 text-slate-400'
            }`}
          >
            <div className="flex items-center gap-2">
              {finalizingStep >= 2 ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              ) : (
                <Clock className="w-4 h-4 text-slate-400 shrink-0" />
              )}
              <div className="text-xs font-bold">2. Transaction secured</div>
            </div>
            <div className="text-[10px] text-slate-500 mt-1 pl-6">
              {finalizingStep >= 2 ? 'Audit Log Sealed' : 'Pending'}
            </div>
          </div>

          {/* 3. Finalizing booking/reservation */}
          <div
            className={`p-3.5 rounded-2xl border transition-all ${
              finalizingStep >= 3
                ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                : 'bg-slate-50 border-slate-200 text-slate-400'
            }`}
          >
            <div className="flex items-center gap-2">
              {finalizingStep >= 3 ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              ) : (
                <Clock className="w-4 h-4 text-slate-400 shrink-0" />
              )}
              <div className="text-xs font-bold">3. Finalizing booking</div>
            </div>
            <div className="text-[10px] text-slate-500 mt-1 pl-6">
              {finalizingStep >= 3 ? 'Inventory Reserved' : 'Pending'}
            </div>
          </div>

          {/* 4. Confirmation received */}
          <div
            className={`p-3.5 rounded-2xl border transition-all ${
              finalizingStep >= 4
                ? 'bg-emerald-50/70 border-emerald-200 text-emerald-900'
                : 'bg-slate-50 border-slate-200 text-slate-400'
            }`}
          >
            <div className="flex items-center gap-2">
              {finalizingStep >= 4 ? (
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
              ) : (
                <Clock className="w-4 h-4 text-slate-400 shrink-0" />
              )}
              <div className="text-xs font-bold">4. Confirmation received</div>
            </div>
            <div className="text-[10px] text-slate-500 mt-1 pl-6">
              {finalizingStep >= 4 ? 'Verified & Complete' : 'Pending'}
            </div>
          </div>
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 4. STEP 5: FINAL CONFIRMED EXPERIENCE ("YAY! 🎉 Your booking is confirmed")
  // ─────────────────────────────────────────────────────────────────────────────

  // ─────────────────────────────────────────────────────────────────────────────
  // 4A. FLIGHT CONFIRMATION TICKET VIEW
  // ─────────────────────────────────────────────────────────────────────────────
  if (isFlight && opt.flight_number) {
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
      <div className="space-y-4 animate-in fade-in zoom-in-95 duration-500">
        {/* YAY! Celebration Banner */}
        <div className="p-5 rounded-3xl bg-gradient-to-r from-emerald-600 via-teal-600 to-sky-600 text-white shadow-md flex flex-col sm:flex-row sm:items-center justify-between gap-4 relative overflow-hidden ring-2 ring-emerald-400/40">
          <div className="flex items-center gap-4 relative z-10">
            <div className="w-14 h-14 rounded-2xl bg-white/20 backdrop-blur-md border border-white/30 flex items-center justify-center text-3xl shadow-inner shrink-0">
              🎉
            </div>
            <div>
              <div className="text-xs font-mono font-bold tracking-widest uppercase text-emerald-100 opacity-90">
                Commercial Task Fulfilled
              </div>
              <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-white mt-0.5">
                YAY! 🎉 Your booking is confirmed
              </h2>
              <p className="text-xs text-emerald-50 mt-1 font-medium">
                Flight {flightNum} from {origin} to {destination} is booked and verified.
              </p>
            </div>
          </div>

          <div className="bg-black/25 backdrop-blur-md border border-white/20 px-4 py-2.5 rounded-2xl shrink-0 self-start sm:self-auto text-right">
            <div className="text-[10px] uppercase font-mono tracking-wider text-emerald-200">
              Payment Status
            </div>
            <div className="text-sm font-extrabold font-mono text-emerald-300 flex items-center gap-1.5 justify-end mt-0.5">
              <Check className="w-4 h-4 text-emerald-300" />
              SUCCESS
            </div>
          </div>
        </div>

        {/* Flight Ticket Boarding Pass Card */}
        <div className="rounded-3xl bg-white border border-slate-200/90 p-6 sm:p-8 shadow-xs relative overflow-hidden">
          {/* Header Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-5 border-b border-slate-100">
            <div className="flex items-center gap-3.5">
              <div className="w-11 h-11 rounded-2xl bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-600">
                <Plane className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-md bg-blue-50 text-blue-700 border border-blue-200">
                    {airline}
                  </span>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200">
                    CONFIRMED
                  </span>
                </div>
                <h3 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight flex items-center gap-2.5 mt-1">
                  <span>{origin}</span>
                  <ArrowRight className="w-5 h-5 text-blue-600" />
                  <span>{destination}</span>
                </h3>
              </div>
            </div>

            <div className="text-left sm:text-right">
              <div className="text-[11px] text-slate-500 font-mono">Amount Charged</div>
              <div className="text-2xl sm:text-3xl font-black font-mono text-slate-900 mt-0.5">
                ₹{price.toLocaleString('en-IN')}
              </div>
            </div>
          </div>

          {/* Core Flight Details Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 my-6 p-4.5 rounded-2xl bg-slate-50 border border-slate-200">
            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Flight Number</span>
              <div className="text-base font-extrabold text-slate-900 font-mono">{flightNum}</div>
              <span className="text-[11px] text-slate-500">{airline}</span>
            </div>

            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Travel Date</span>
              <div className="text-base font-extrabold text-slate-900 flex items-center gap-1.5">
                <Calendar className="w-4 h-4 text-blue-600 shrink-0" />
                <span>{dateStr}</span>
              </div>
              <span className="text-[11px] text-slate-500">Direct Flight</span>
            </div>

            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Departure / Arrival</span>
              <div className="text-base font-extrabold text-slate-900 font-mono flex items-center gap-1.5">
                <Clock className="w-4 h-4 text-blue-600 shrink-0" />
                <span>{depTime} → {arrTime}</span>
              </div>
              <span className="text-[11px] text-slate-500">75 mins duration</span>
            </div>

            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Payment Status</span>
              <div className="text-base font-extrabold text-emerald-700 font-mono flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>SUCCESS</span>
              </div>
              <span className="text-[11px] text-slate-500">Settled via Policy</span>
            </div>
          </div>

          {/* Four Guarantee Badges */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 mb-6">
            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
              <span className="text-[10px] text-emerald-700 font-bold uppercase block">User budget</span>
              <span className="font-bold text-emerald-900 mt-0.5 block">Under ₹{userBudget.toLocaleString('en-IN')} ✓</span>
            </div>

            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
              <span className="text-[10px] text-emerald-700 font-bold uppercase block">AgentPay policy</span>
              <span className="font-bold text-emerald-900 mt-0.5 block">APPROVED ✓</span>
            </div>

            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
              <span className="text-[10px] text-emerald-700 font-bold uppercase block">Payment Rail</span>
              <span className="font-bold text-emerald-900 mt-0.5 block">SUCCESS ✓</span>
            </div>

            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
              <span className="text-[10px] text-emerald-700 font-bold uppercase block">Booking State</span>
              <span className="font-bold text-emerald-900 mt-0.5 block">CONFIRMED ✓</span>
            </div>
          </div>

          {/* Footer & Audit Log link */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-slate-100">
            <p className="text-xs text-slate-600 leading-relaxed font-medium">
              {result.final_message}
            </p>

            {result.transaction_id && onInspectTransaction && (
              <button
                type="button"
                onClick={() => onInspectTransaction(result.transaction_id!)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-slate-100 hover:bg-slate-200 text-slate-800 transition-all cursor-pointer shrink-0 border border-slate-200 shadow-2xs"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Inspect Audit Log</span>
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 4B. RESTAURANT CONFIRMATION TICKET VIEW
  // ─────────────────────────────────────────────────────────────────────────────
  if (isRestaurant && opt.restaurant_name) {
    const name = opt.restaurant_name || 'ITC Narmada'
    const city = opt.city || req.city || 'Ahmedabad'
    const dateStr = opt.date || req.date || 'September 22'
    const timeStr = opt.time_display || opt.time || req.time || '8:00 PM'
    const persons = opt.party_size || opt.persons || req.party_size || 2
    const deposit = Number(opt.deposit_amount || result.amount || 1000)

    return (
      <div className="space-y-4 animate-in fade-in zoom-in-95 duration-500">
        {/* YAY! Celebration Banner */}
        <div className="p-5 rounded-3xl bg-gradient-to-r from-amber-600 via-orange-600 to-emerald-600 text-white shadow-md flex flex-col sm:flex-row sm:items-center justify-between gap-4 relative overflow-hidden ring-2 ring-amber-400/40">
          <div className="flex items-center gap-4 relative z-10">
            <div className="w-14 h-14 rounded-2xl bg-white/20 backdrop-blur-md border border-white/30 flex items-center justify-center text-3xl shadow-inner shrink-0">
              🎉
            </div>
            <div>
              <div className="text-xs font-mono font-bold tracking-widest uppercase text-amber-100 opacity-90">
                Commercial Task Fulfilled
              </div>
              <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-white mt-0.5">
                YAY! 🎉 Your booking is confirmed
              </h2>
              <p className="text-xs text-amber-50 mt-1 font-medium">
                Table for {persons} at {name} ({city}) is reserved.
              </p>
            </div>
          </div>

          <div className="bg-black/25 backdrop-blur-md border border-white/20 px-4 py-2.5 rounded-2xl shrink-0 self-start sm:self-auto text-right">
            <div className="text-[10px] uppercase font-mono tracking-wider text-amber-200">
              Payment Status
            </div>
            <div className="text-sm font-extrabold font-mono text-emerald-300 flex items-center gap-1.5 justify-end mt-0.5">
              <Check className="w-4 h-4 text-emerald-300" />
              SUCCESS
            </div>
          </div>
        </div>

        {/* Restaurant Reservation Ticket Card */}
        <div className="rounded-3xl bg-white border border-slate-200/90 p-6 sm:p-8 shadow-xs relative overflow-hidden">
          {/* Header Bar */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-5 border-b border-slate-100">
            <div className="flex items-center gap-3.5">
              <div className="w-11 h-11 rounded-2xl bg-amber-50 border border-amber-200 flex items-center justify-center text-amber-600">
                <Utensils className="w-6 h-6" />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-md bg-amber-50 text-amber-700 border border-amber-200">
                    FINE DINING
                  </span>
                  <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200">
                    RESERVATION CONFIRMED
                  </span>
                </div>
                <h3 className="text-xl sm:text-2xl font-bold text-slate-900 tracking-tight mt-1">
                  {name.toUpperCase()}
                </h3>
              </div>
            </div>

            <div className="text-left sm:text-right">
              <div className="text-[11px] text-slate-500 font-mono">Reservation Deposit</div>
              <div className="text-2xl sm:text-3xl font-black font-mono text-slate-900 mt-0.5">
                ₹{deposit.toLocaleString('en-IN')}
              </div>
            </div>
          </div>

          {/* Reservation Details Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3.5 my-6 p-4.5 rounded-2xl bg-slate-50 border border-slate-200">
            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">City & Venue</span>
              <div className="text-base font-extrabold text-slate-900">{city}</div>
              <span className="text-[11px] text-slate-500">{name}</span>
            </div>

            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Date & Time</span>
              <div className="text-base font-extrabold text-slate-900 flex items-center gap-1.5 font-mono">
                <Calendar className="w-4 h-4 text-amber-600 shrink-0" />
                <span>{dateStr} @ {timeStr}</span>
              </div>
              <span className="text-[11px] text-slate-500">Confirmed Slot</span>
            </div>

            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Party Size</span>
              <div className="text-base font-extrabold text-slate-900 flex items-center gap-1.5">
                <User className="w-4 h-4 text-amber-600 shrink-0" />
                <span>{persons} Guests</span>
              </div>
              <span className="text-[11px] text-slate-500">Reserved Seating</span>
            </div>

            <div>
              <span className="text-[10px] uppercase font-bold text-slate-500 block mb-1">Payment Status</span>
              <div className="text-base font-extrabold text-emerald-700 font-mono flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
                <span>SUCCESS</span>
              </div>
              <span className="text-[11px] text-slate-500">Deposit Settled</span>
            </div>
          </div>

          {/* Four Guarantee Badges */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 mb-6">
            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
              <span className="text-[10px] text-emerald-700 font-bold uppercase block">User constraints</span>
              <span className="font-bold text-emerald-900 mt-0.5 block">PASS ✓</span>
            </div>

            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
              <span className="text-[10px] text-emerald-700 font-bold uppercase block">AgentPay policy</span>
              <span className="font-bold text-emerald-900 mt-0.5 block">APPROVED ✓</span>
            </div>

            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
              <span className="text-[10px] text-emerald-700 font-bold uppercase block">Payment Rail</span>
              <span className="font-bold text-emerald-900 mt-0.5 block">SUCCESS ✓</span>
            </div>

            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
              <span className="text-[10px] text-emerald-700 font-bold uppercase block">Reservation</span>
              <span className="font-bold text-emerald-900 mt-0.5 block">CONFIRMED ✓</span>
            </div>
          </div>

          {/* Footer & Audit Log link */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-slate-100">
            <p className="text-xs text-slate-600 leading-relaxed font-medium">
              {result.final_message}
            </p>

            {result.transaction_id && onInspectTransaction && (
              <button
                type="button"
                onClick={() => onInspectTransaction(result.transaction_id!)}
                className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-slate-100 hover:bg-slate-200 text-slate-800 transition-all cursor-pointer shrink-0 border border-slate-200 shadow-2xs"
              >
                <ExternalLink className="w-3.5 h-3.5" />
                <span>Inspect Audit Log</span>
              </button>
            )}
          </div>
        </div>
      </div>
    )
  }

  // ─────────────────────────────────────────────────────────────────────────────
  // 4C. DIRECT PAYMENT CONFIRMATION VIEW
  // ─────────────────────────────────────────────────────────────────────────────
  const amount = Number(result.amount || 0)
  return (
    <div className="space-y-4 animate-in fade-in zoom-in-95 duration-500">
      {/* YAY! Celebration Banner */}
      <div className="p-5 rounded-3xl bg-gradient-to-r from-blue-600 via-indigo-600 to-emerald-600 text-white shadow-md flex flex-col sm:flex-row sm:items-center justify-between gap-4 relative overflow-hidden ring-2 ring-blue-400/40">
        <div className="flex items-center gap-4 relative z-10">
          <div className="w-14 h-14 rounded-2xl bg-white/20 backdrop-blur-md border border-white/30 flex items-center justify-center text-3xl shadow-inner shrink-0">
            🎉
          </div>
          <div>
            <div className="text-xs font-mono font-bold tracking-widest uppercase text-blue-100 opacity-90">
              Commercial Task Fulfilled
            </div>
            <h2 className="text-2xl sm:text-3xl font-black tracking-tight text-white mt-0.5">
              YAY! 🎉 Your booking is confirmed
            </h2>
            <p className="text-xs text-blue-50 mt-1 font-medium">
              Direct payment to {result.merchant_name || 'Merchant'} of ₹{amount.toLocaleString('en-IN')} is settled.
            </p>
          </div>
        </div>

        <div className="bg-black/25 backdrop-blur-md border border-white/20 px-4 py-2.5 rounded-2xl shrink-0 self-start sm:self-auto text-right">
          <div className="text-[10px] uppercase font-mono tracking-wider text-blue-200">
            Payment Status
          </div>
          <div className="text-sm font-extrabold font-mono text-emerald-300 flex items-center gap-1.5 justify-end mt-0.5">
            <Check className="w-4 h-4 text-emerald-300" />
            SUCCESS
          </div>
        </div>
      </div>

      <div className="rounded-3xl bg-white border border-slate-200/90 p-6 sm:p-8 shadow-xs">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3.5">
            <div className="w-11 h-11 rounded-2xl bg-blue-50 border border-blue-200 flex items-center justify-center text-blue-600">
              <CreditCard className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-blue-700 tracking-wider uppercase">
                  Direct Payment
                </span>
                <span className="text-[10px] font-semibold px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200">
                  {result.payment_status}
                </span>
              </div>
              <h3 className="text-xl font-bold text-slate-900 mt-0.5">
                {result.merchant_name || 'Authorized Merchant'}
              </h3>
            </div>
          </div>

          <div className="text-left sm:text-right">
            <div className="text-[11px] text-slate-500">Settled Amount</div>
            <div className="text-3xl font-black font-mono text-slate-900">
              ₹{amount.toLocaleString('en-IN')}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-2 lg:grid-cols-4 gap-2.5 my-6">
          <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs">
            <span className="text-[10px] text-slate-500 font-bold uppercase block">Merchant</span>
            <span className="font-bold text-slate-800 mt-0.5 block">{result.merchant_name || 'Recipient'}</span>
          </div>

          <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-bold uppercase block">AgentPay policy</span>
            <span className="font-bold text-emerald-900 mt-0.5 block">APPROVED ✓</span>
          </div>

          <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-bold uppercase block">Payment Rail</span>
            <span className="font-bold text-emerald-900 mt-0.5 block">{result.payment_status} ✓</span>
          </div>

          <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-xs">
            <span className="text-[10px] text-emerald-700 font-bold uppercase block">Task Status</span>
            <span className="font-bold text-emerald-900 mt-0.5 block">COMPLETED ✓</span>
          </div>
        </div>

        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-4 border-t border-slate-100">
          <p className="text-xs text-slate-600 leading-snug">
            {result.final_message}
          </p>

          {result.transaction_id && onInspectTransaction && (
            <button
              type="button"
              onClick={() => onInspectTransaction(result.transaction_id!)}
              className="flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-slate-100 hover:bg-slate-200 text-slate-800 transition-all cursor-pointer shrink-0 border border-slate-200 shadow-2xs"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Inspect Audit Log</span>
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
