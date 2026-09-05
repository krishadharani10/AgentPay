import React, { useState, useEffect, useCallback, useRef } from 'react'
import {
  Bot,
  Send,
  Sparkles,
  Plane,
  Utensils,
  CreditCard,
  ExternalLink,
  CheckCircle2,
  ShieldAlert,
  Zap,
  Tv,
  Check,
  ArrowRight,
  ShieldCheck,
  Clock,
  RotateCw,
  RefreshCw,
} from 'lucide-react'
import type {
  TaskRunResponse,
  PaymentProviderConfig,
  AgentRunResponse,
  TaskPrepareResponse,
} from '../types'
import { api } from '../api/client'
import { launchRazorpayCheckout } from '../utils/razorpay'
import { TaskExecutionTimeline } from './TaskExecutionTimeline'
import type { ExecutionStage } from './TaskExecutionTimeline'
import { AutonomousResultCard } from './AutonomousResultCard'

interface AgentConsoleProps {
  onRunAgent?: (
    message: string,
    options?: { force_failure?: boolean; retry_if_failed?: boolean }
  ) => Promise<AgentRunResponse | null>
  onRunTask?: (
    message: string,
    options?: { force_failure?: boolean; retry_if_failed?: boolean; idempotency_key?: string; demo_run_id?: string }
  ) => Promise<TaskRunResponse | null>
  loading: boolean
  onPaymentVerified?: () => void
  onInspectTransaction?: (txId: string) => void
}

export const AgentConsole: React.FC<AgentConsoleProps> = ({
  onRunTask,
  loading,
  onPaymentVerified,
  onInspectTransaction,
}) => {
  const [prompt, setPrompt] = useState('')
  const [lastTaskResult, setLastTaskResult] = useState<TaskRunResponse | null>(null)
  const [preparedTask, setPreparedTask] = useState<TaskPrepareResponse | null>(null)
  const [prepLoading, setPrepLoading] = useState<boolean>(false)
  const [executionStage, setExecutionStage] = useState<ExecutionStage>('IDLE')
  const [activeStep, setActiveStep] = useState<number>(0)
  const [paymentConfig, setPaymentConfig] = useState<PaymentProviderConfig | null>(null)
  const [checkoutLoading, setCheckoutLoading] = useState<boolean>(false)
  const [verificationSuccess, setVerificationSuccess] = useState<string | null>(null)
  const [activePreset, setActivePreset] = useState<string>('')
  const [forceFailPreset, setForceFailPreset] = useState<boolean>(false)
  const [completedBy, setCompletedBy] = useState<'AGENT' | 'RAZORPAY' | 'SYSTEM' | null>(null)
  const [demoRunId, setDemoRunId] = useState<string | null>(null)
  const resultCardRef = useRef<HTMLDivElement>(null)

  // Load payment config on mount
  useEffect(() => {
    api
      .getPaymentConfig()
      .then((cfg) => setPaymentConfig(cfg))
      .catch((e) => console.warn('Could not load payment config:', e))
  }, [])

  // Function to prepare task details (inspects domain inventory & checks completion state without paying)
  const handlePrepareTask = useCallback(async (taskPrompt: string, runIdOverride?: string | null) => {
    if (!taskPrompt.trim()) return
    setPrepLoading(true)
    try {
      const activeRunId = runIdOverride !== undefined ? runIdOverride : demoRunId
      const prep = await api.prepareTask({
        message: taskPrompt,
        demo_run_id: activeRunId || undefined,
      })
      setPreparedTask(prep)
      if (prep.already_completed) {
        if (prep.existing_payment_provider === 'RAZORPAY') {
          setCompletedBy('RAZORPAY')
        } else {
          setCompletedBy('AGENT')
        }
      } else {
        setCompletedBy(null)
      }
    } catch (err) {
      console.warn('Task preparation failed:', err)
      setPreparedTask(null)
    } finally {
      setPrepLoading(false)
    }
  }, [demoRunId])

  // Progressive execution stages during loading
  useEffect(() => {
    let interval: number | null = null
    if (loading || checkoutLoading) {
      setExecutionStage('STARTING')
      setActiveStep(1)
      const stages: ExecutionStage[] = [
        'STARTING',
        'UNDERSTANDING_REQUEST',
        'SEARCHING_OPTIONS',
        'OPTION_SELECTED',
        'CREATING_PAYMENT_INTENT',
        'POLICY_CHECK',
        'PAYMENT_PROCESSING',
        'FINALIZING_BOOKING',
      ]
      let stepIndex = 1
      interval = window.setInterval(() => {
        stepIndex += 1
        if (stepIndex <= 8) {
          setActiveStep(stepIndex)
          setExecutionStage(stages[stepIndex - 1])
        }
      }, 350)
    } else {
      if (lastTaskResult) {
        setActiveStep(8)
        if (lastTaskResult.task_status === 'COMPLETED') {
          setExecutionStage('SUCCESS')
        } else if (lastTaskResult.policy_result === 'REJECTED') {
          setExecutionStage('REJECTED')
        } else {
          setExecutionStage('FAILED')
        }
      } else {
        setExecutionStage('IDLE')
        setActiveStep(0)
      }
    }
    return () => {
      if (interval !== null) clearInterval(interval)
    }
  }, [loading, checkoutLoading, lastTaskResult])

  // Quick Action Handler: selects/populates task and prepares it WITHOUT executing payment
  const handleQuickAction = (presetKey: string, presetPrompt: string, forceFail = false) => {
    // Fresh demo run id allows replay without double-charging or mutating past transactions
    const newRunId = Math.random().toString(36).substring(2, 9)
    setDemoRunId(newRunId)
    setPrompt(presetPrompt)
    setActivePreset(presetKey)
    setForceFailPreset(forceFail)
    setLastTaskResult(null)
    setVerificationSuccess(null)
    setCompletedBy(null)
    handlePrepareTask(presetPrompt, newRunId)
  }

  // Run Again handler: creates a fresh demo execution scope leaving past transactions immutable
  const handleRunAgain = () => {
    if (!prompt.trim()) return
    const newRunId = Math.random().toString(36).substring(2, 9)
    setDemoRunId(newRunId)
    setLastTaskResult(null)
    setVerificationSuccess(null)
    setCompletedBy(null)
    handlePrepareTask(prompt, newRunId)
  }

  // Reset Demo handler (Req 11): completely clears active demo state for a clean slate
  const handleResetDemo = () => {
    const newRunId = Math.random().toString(36).substring(2, 9)
    setDemoRunId(newRunId)
    setPrompt('')
    setActivePreset('')
    setForceFailPreset(false)
    setPreparedTask(null)
    setLastTaskResult(null)
    setVerificationSuccess(null)
    setCompletedBy(null)
  }

  // Auto-scroll to result on completion (Req 5)
  useEffect(() => {
    if (lastTaskResult && !loading && !checkoutLoading) {
      const timer = setTimeout(() => {
        resultCardRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
      }, 80)
      return () => clearTimeout(timer)
    }
  }, [lastTaskResult, loading, checkoutLoading])

  // Determine if this task is authoritatively completed in backend database or current execution
  const isTaskCompleted =
    preparedTask?.already_completed === true ||
    lastTaskResult?.already_completed === true ||
    (lastTaskResult?.task_status === 'COMPLETED' && lastTaskResult?.payment_status === 'SUCCESS')

  const completedTransactionId =
    preparedTask?.existing_transaction_id ||
    lastTaskResult?.transaction_id ||
    ''

  // Execution Path 1: Run Autonomous Agent
  const handleRunAutonomousAgent = async () => {
    if (!prompt.trim() || loading || checkoutLoading) return
    if (isTaskCompleted) {
      if (completedTransactionId && onInspectTransaction) {
        onInspectTransaction(completedTransactionId)
      }
      return
    }
    setVerificationSuccess(null)

    const shouldForceFailure = forceFailPreset
    const idemKey = preparedTask?.idempotency_key

    let res: TaskRunResponse | null = null
    if (onRunTask) {
      res = await onRunTask(prompt, {
        force_failure: shouldForceFailure,
        retry_if_failed: true,
        idempotency_key: idemKey,
        demo_run_id: demoRunId || undefined,
      })
    } else {
      try {
        res = await api.executeTask({
          message: prompt,
          force_failure: shouldForceFailure,
          retry_if_failed: true,
          idempotency_key: idemKey,
          demo_run_id: demoRunId || undefined,
        })
      } catch (err) {
        console.error('Task run failed:', err)
      }
    }

    if (res) {
      setLastTaskResult(res)
      if (res.already_completed) {
        setCompletedBy('AGENT')
      } else if (res.task_status === 'COMPLETED' && res.payment_status === 'SUCCESS') {
        setCompletedBy('AGENT')
      }
      // Refresh prepared task state to update completion status from backend
      handlePrepareTask(prompt, demoRunId)
    }
  }

  // Execution Path 2: Pay with Razorpay
  const handleOpenRazorpayCheckout = async () => {
    if (loading || checkoutLoading) return
    if (isTaskCompleted) {
      if (completedTransactionId && onInspectTransaction) {
        onInspectTransaction(completedTransactionId)
      }
      return
    }

    setCheckoutLoading(true)
    setVerificationSuccess(null)

    try {
      let txId = lastTaskResult?.transaction_id || preparedTask?.existing_transaction_id
      let amt = lastTaskResult?.amount || preparedTask?.estimated_amount || 7450
      let merchant = lastTaskResult?.merchant_name || preparedTask?.merchant_name || 'AirDemo'
      let orderId = lastTaskResult?.provider_payment_id
      const idemKey = preparedTask?.idempotency_key

      // If we don't have a transaction ID yet, execute task to create the authorized TransactionIntent
      if (!txId) {
        let res: TaskRunResponse | null = null
        if (onRunTask) {
          res = await onRunTask(prompt, {
            force_failure: false,
            retry_if_failed: true,
            idempotency_key: idemKey,
            demo_run_id: demoRunId || undefined,
          })
        } else {
          res = await api.executeTask({
            message: prompt,
            force_failure: false,
            retry_if_failed: true,
            idempotency_key: idemKey,
            demo_run_id: demoRunId || undefined,
          })
        }

        if (res) {
          // Only show the result card immediately for terminal states.
          // For the happy path (Razorpay checkout is about to open), do NOT set
          // lastTaskResult here — the confirmation must only appear after the
          // backend verifies the Razorpay signature (see onSuccess handler below).
          if (res.already_completed) {
            setLastTaskResult(res)
            setCompletedBy('AGENT')
            handlePrepareTask(prompt, demoRunId)
            return
          }
          if (res.policy_result === 'REJECTED' || res.task_status === 'REJECTED') {
            setLastTaskResult(res)
            return
          }
          if (res.task_status === 'FAILED' || res.payment_status === 'FAILED') {
            setLastTaskResult(res)
            return
          }
          // Happy path: task authorized and transaction created — proceed to Razorpay.
          // Do NOT set lastTaskResult yet; it will be set after payment verification.
          txId = res.transaction_id || undefined
          amt = res.amount || amt
          merchant = res.merchant_name || merchant
          orderId = res.provider_payment_id
        }
      }

      if (txId && paymentConfig?.key_id) {
        openCheckoutForTransaction(txId, amt, merchant, orderId)
      } else {
        // In mock mode without Razorpay credentials, execution completed via direct provider
        setCompletedBy('RAZORPAY')
        handlePrepareTask(prompt)
        if (onPaymentVerified) onPaymentVerified()
      }
    } finally {
      setCheckoutLoading(false)
    }
  }

  const openCheckoutForTransaction = (
    txId: string,
    amount: number,
    merchantName: string,
    orderId?: string | null
  ) => {
    if (!paymentConfig?.key_id) {
      alert('Razorpay public Key ID not configured on server.')
      return
    }

    launchRazorpayCheckout({
      keyId: paymentConfig.key_id,
      amountInRupees: amount,
      merchantName: `AgentPay → ${merchantName}`,
      description: `Autonomous Policy-Guarded Payment #${txId.substring(0, 8)}`,
      orderId: orderId?.startsWith('order_') ? orderId : undefined,
      onSuccess: async (rzpRes) => {
        setCheckoutLoading(true)
        try {
          const verifyResult = await api.verifyRazorpayPayment({
            transaction_id: txId,
            razorpay_order_id: rzpRes.razorpay_order_id || (orderId || ''),
            razorpay_payment_id: rzpRes.razorpay_payment_id,
            razorpay_signature: rzpRes.razorpay_signature || '',
          })
          if (verifyResult.success) {
            setVerificationSuccess(
              `Razorpay payment ${rzpRes.razorpay_payment_id} verified & captured!`
            )
            setCompletedBy('RAZORPAY')
            setLastTaskResult({
              task_type: preparedTask?.task_type || 'BOOK_FLIGHT',
              interpreted_request: preparedTask?.interpreted_request || {},
              selected_option: preparedTask?.selected_option || null,
              task_constraint_result: 'PASS',
              policy_result: 'APPROVED',
              transaction_id: txId,
              payment_status: 'SUCCESS',
              task_status: 'COMPLETED',
              final_message: `Razorpay payment ${rzpRes.razorpay_payment_id} verified and captured!`,
              amount: amount,
              merchant_name: merchantName,
              already_completed: false,
              payment_provider: 'RAZORPAY',
            })
            // Re-prepare and refresh backend state
            handlePrepareTask(prompt, demoRunId)
            if (onPaymentVerified) onPaymentVerified()
          }
        } catch (err: unknown) {
          console.error('Signature verification failed:', err)
          alert('Signature verification failed on backend.')
        } finally {
          setCheckoutLoading(false)
        }
      },
      onError: (err) => {
        console.error('Razorpay checkout error:', err)
      },
    })
  }

  // ── 6-State Resolution for Execution Buttons ──
  type ButtonStateType = 'AVAILABLE' | 'PROCESSING' | 'COMPLETED' | 'ALREADY_PAID' | 'REJECTED' | 'FAILED'
  interface ButtonStateInfo {
    type: ButtonStateType
    title: string
    subtitle: string
    txId?: string
  }

  const getAgentButtonState = (): ButtonStateInfo => {
    if (loading) {
      return {
        type: 'PROCESSING',
        title: 'Executing Autonomous Task...',
        subtitle: 'Running policy checks & commerce tools',
      }
    }
    if (isTaskCompleted) {
      if (completedBy === 'AGENT') {
        return {
          type: 'COMPLETED',
          title: '✓ Autonomous Payment Completed',
          subtitle: 'Booking confirmed & verified in ledger',
          txId: completedTransactionId,
        }
      } else if (completedBy === 'RAZORPAY') {
        return {
          type: 'ALREADY_PAID',
          title: 'Payment Already Completed',
          subtitle: 'This task was already paid through Razorpay.',
          txId: completedTransactionId,
        }
      } else {
        return {
          type: 'ALREADY_PAID',
          title: 'Payment Already Completed',
          subtitle: 'This task was already paid.',
          txId: completedTransactionId,
        }
      }
    }
    if (lastTaskResult?.policy_result === 'REJECTED' || lastTaskResult?.task_status === 'REJECTED') {
      return {
        type: 'REJECTED',
        title: 'Policy Rejected — No Payment',
        subtitle: 'Blocked by deterministic policy rules',
      }
    }
    if (
      lastTaskResult?.task_status === 'FAILED' ||
      lastTaskResult?.task_status === 'PAYMENT_FAILED' ||
      lastTaskResult?.payment_status === 'FAILED'
    ) {
      return {
        type: 'FAILED',
        title: 'Payment Failed',
        subtitle: lastTaskResult?.final_message || 'Autonomous execution failed — retries exhausted',
      }
    }
    return {
      type: 'AVAILABLE',
      title: 'Run Autonomous Agent',
      subtitle: 'Full 8-stage verified autonomous booking',
    }
  }

  const getRazorpayButtonState = (): ButtonStateInfo => {
    if (checkoutLoading) {
      return {
        type: 'PROCESSING',
        title: 'Preparing Razorpay Checkout...',
        subtitle: 'Opening official payment gateway',
      }
    }
    if (isTaskCompleted) {
      if (completedBy === 'RAZORPAY') {
        return {
          type: 'COMPLETED',
          title: '✓ Razorpay Payment Verified',
          subtitle: 'Booking confirmed & signature verified',
          txId: completedTransactionId,
        }
      } else if (completedBy === 'AGENT') {
        return {
          type: 'ALREADY_PAID',
          title: 'Payment Already Completed',
          subtitle: 'This task was already paid through Autonomous Agent.',
          txId: completedTransactionId,
        }
      } else {
        return {
          type: 'ALREADY_PAID',
          title: 'Payment Already Completed',
          subtitle: 'This task was already paid.',
          txId: completedTransactionId,
        }
      }
    }
    if (lastTaskResult?.policy_result === 'REJECTED' || lastTaskResult?.task_status === 'REJECTED') {
      return {
        type: 'REJECTED',
        title: 'Policy Rejected — No Payment',
        subtitle: 'Blocked by deterministic policy rules',
      }
    }
    if (
      lastTaskResult?.task_status === 'FAILED' ||
      lastTaskResult?.task_status === 'PAYMENT_FAILED' ||
      lastTaskResult?.payment_status === 'FAILED'
    ) {
      return {
        type: 'FAILED',
        title: 'Payment Failed',
        subtitle: lastTaskResult?.final_message || 'Payment attempt failed across configured rails',
      }
    }
    return {
      type: 'AVAILABLE',
      title: 'Pay with Razorpay',
      subtitle: 'Official Razorpay Test Mode checkout modal',
    }
  }

  const agentBtn = getAgentButtonState()
  const rzpBtn = getRazorpayButtonState()
  const isRazorpayActive = paymentConfig?.provider === 'RAZORPAY_TEST' || paymentConfig?.provider === 'RAZORPAY' || !!paymentConfig?.key_id

  return (
    <div className="space-y-6">
      {/* ─────────────────────────────────────────────────────────────────────────────
          MAIN HERO CONSOLE: "What would you like your agent to do?"
      ───────────────────────────────────────────────────────────────────────────── */}
      <div className="bg-white border border-slate-200 rounded-xl p-5 sm:p-6 shadow-[0_1px_3px_rgba(15,23,42,0.04)] space-y-6">
        {/* Top Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-[#305EFF] shrink-0">
              <Bot className="w-4.5 h-4.5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-blue-50 text-[#305EFF] border border-blue-100">
                  Autonomous Commerce Layer
                </span>
                <span className="text-[11px] font-medium px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200/80">
                  Deterministic Policy Guard
                </span>
              </div>
              <h2 className="text-lg sm:text-xl font-semibold text-slate-900 tracking-tight mt-1">
                What would you like your agent to do?
              </h2>
            </div>
          </div>

          {/* Header Controls: Reset Demo + Provider Badge */}
          <div className="flex items-center gap-2.5 self-start sm:self-auto flex-wrap">
            <button
              type="button"
              id="reset-demo-btn"
              onClick={handleResetDemo}
              disabled={loading || checkoutLoading}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white hover:bg-slate-50 border border-slate-200 text-slate-700 text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
              title="Reset current demo state for a fresh task run without altering historical records"
            >
              <RefreshCw className="w-3.5 h-3.5 text-[#305EFF]" />
              <span>Reset Demo</span>
            </button>

            {isRazorpayActive && (
              <div className="flex items-center gap-2 px-2.5 py-1.5 rounded-lg bg-blue-50/70 border border-blue-100 text-xs shrink-0">
                <span className="w-2 h-2 rounded-full bg-[#305EFF] animate-pulse" />
                <div>
                  <div className="text-[10px] font-semibold text-slate-800">
                    Razorpay Test Mode
                  </div>
                  <div className="text-[10px] text-slate-500 font-mono">
                    {paymentConfig?.key_id ? `${paymentConfig.key_id.substring(0, 14)}...` : 'Connected'}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Verification Success Banner */}
        {verificationSuccess && (
          <div className="p-3 rounded-lg bg-emerald-50 border border-emerald-200 text-emerald-800 text-xs flex items-center gap-2 animate-in fade-in">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span className="font-semibold">{verificationSuccess}</span>
          </div>
        )}

        {/* ── QUICK ACTIONS: Split into Flagship Autonomous Tasks vs Guardrail Demos (Req 9) ── */}
        <div className="space-y-4">
          {/* Section 1: PRIMARY TASKS */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-900">
                Primary Tasks
              </span>
              <span className="text-xs text-slate-500 font-normal">
                Flagship Autonomous Commerce Demos
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {/* 1. Book a Flight */}
              <button
                type="button"
                id="action-book-flight"
                disabled={loading || checkoutLoading}
                onClick={() =>
                  handleQuickAction(
                    'flight',
                    'Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22'
                  )
                }
                className={`p-3.5 rounded-xl border text-left transition-colors cursor-pointer group disabled:opacity-50 relative ${
                  activePreset === 'flight'
                    ? 'bg-blue-50/70 border-[#305EFF] ring-1 ring-[#305EFF]'
                    : 'bg-white hover:bg-slate-50 border-slate-200'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-[#305EFF]">
                    <Plane className="w-4 h-4 text-[#305EFF]" />
                    <span>Book a flight</span>
                  </div>
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-blue-50 text-[#305EFF] border border-blue-100">
                    AMD → BOM
                  </span>
                </div>
                <div className="text-xs font-semibold text-slate-900">Ahmedabad to Mumbai under ₹10k</div>
                <div className="text-[11px] text-slate-500 mt-0.5 font-normal">AirDemo AP101 @ ₹7,450 · Approved</div>
              </button>

              {/* 2. Reserve a Restaurant */}
              <button
                type="button"
                id="action-reserve-restaurant"
                disabled={loading || checkoutLoading}
                onClick={() =>
                  handleQuickAction(
                    'restaurant',
                    'Reserve a table in ITC Narmada, Ahmedabad for 2 people at 8 PM on September 22 under ₹3,000'
                  )
                }
                className={`p-3.5 rounded-xl border text-left transition-colors cursor-pointer group disabled:opacity-50 relative ${
                  activePreset === 'restaurant'
                    ? 'bg-blue-50/70 border-[#305EFF] ring-1 ring-[#305EFF]'
                    : 'bg-white hover:bg-slate-50 border-slate-200'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
                    <Utensils className="w-4 h-4 text-amber-600" />
                    <span>Reserve restaurant</span>
                  </div>
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-50 text-amber-700 border border-amber-200">
                    ITC Narmada
                  </span>
                </div>
                <div className="text-xs font-semibold text-slate-900">ITC Narmada, 2 people @ 8 PM</div>
                <div className="text-[11px] text-slate-500 mt-0.5 font-normal">Deposit ₹1,000 · Approved</div>
              </button>

              {/* 3. Make a Payment */}
              <button
                type="button"
                id="action-make-payment"
                disabled={loading || checkoutLoading}
                onClick={() =>
                  handleQuickAction(
                    'payment',
                    'Pay ₹899 to Amazon for office supplies'
                  )
                }
                className={`p-3.5 rounded-xl border text-left transition-colors cursor-pointer group disabled:opacity-50 relative ${
                  activePreset === 'payment'
                    ? 'bg-blue-50/70 border-[#305EFF] ring-1 ring-[#305EFF]'
                    : 'bg-white hover:bg-slate-50 border-slate-200'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-slate-800">
                    <CreditCard className="w-4 h-4 text-emerald-600" />
                    <span>Make payment</span>
                  </div>
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200">
                    Direct
                  </span>
                </div>
                <div className="text-xs font-semibold text-slate-900">Amazon ₹899</div>
                <div className="text-[11px] text-slate-500 mt-0.5 font-normal">Office supplies · Primary UPI</div>
              </button>
            </div>
          </div>

          {/* Section 2: GUARDRAIL DEMOS */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-semibold text-slate-600">
                Test AgentPay's Guardrails
              </span>
              <span className="text-xs text-slate-400 font-normal">
                Policy Enforcement & Rail Fallback
              </span>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
              {/* 4. Policy Rejection Demo */}
              <button
                type="button"
                id="action-policy-block"
                disabled={loading || checkoutLoading}
                onClick={() =>
                  handleQuickAction(
                    'policy_block',
                    'Book a flight from Ahmedabad to Mumbai under ₹15,000 on September 8'
                  )
                }
                className={`p-3.5 rounded-xl border text-left transition-colors cursor-pointer group disabled:opacity-50 relative ${
                  activePreset === 'policy_block'
                    ? 'bg-rose-50/70 border-rose-400 ring-1 ring-rose-400'
                    : 'bg-white hover:bg-slate-50 border-slate-200'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-rose-700">
                    <ShieldAlert className="w-4 h-4 text-rose-600" />
                    <span>Policy Block</span>
                  </div>
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200">
                    REJECTED
                  </span>
                </div>
                <div className="text-xs font-semibold text-slate-900">Flight exceeding limit</div>
                <div className="text-[11px] text-slate-500 mt-0.5 font-normal">Selects AP420 @ ₹11,500 &gt; Limit ₹8k</div>
              </button>

              {/* 5. Auto-Fallback Demo */}
              <button
                type="button"
                id="action-fallback-demo"
                disabled={loading || checkoutLoading}
                onClick={() =>
                  handleQuickAction(
                    'fallback',
                    'Pay ₹1,240 to Torrent Power',
                    true
                  )
                }
                className={`p-3.5 rounded-xl border text-left transition-colors cursor-pointer group disabled:opacity-50 relative ${
                  activePreset === 'fallback'
                    ? 'bg-blue-50/70 border-[#305EFF] ring-1 ring-[#305EFF]'
                    : 'bg-white hover:bg-slate-50 border-slate-200'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-[#305EFF]">
                    <Zap className="w-4 h-4 text-[#305EFF]" />
                    <span>Auto Fallback</span>
                  </div>
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-blue-50 text-[#305EFF] border border-blue-100">
                    FALLBACK
                  </span>
                </div>
                <div className="text-xs font-semibold text-slate-900">Torrent Power (₹1,240)</div>
                <div className="text-[11px] text-slate-500 mt-0.5 font-normal">UPI decl → Policy check → Card</div>
              </button>

              {/* 6. Blocked Category Demo */}
              <button
                type="button"
                id="action-netflix-block"
                disabled={loading || checkoutLoading}
                onClick={() =>
                  handleQuickAction(
                    'netflix',
                    'Pay ₹3,000 for Netflix subscription'
                  )
                }
                className={`p-3.5 rounded-xl border text-left transition-colors cursor-pointer group disabled:opacity-50 relative ${
                  activePreset === 'netflix'
                    ? 'bg-rose-50/70 border-rose-400 ring-1 ring-rose-400'
                    : 'bg-white hover:bg-slate-50 border-slate-200'
                }`}
              >
                <div className="flex items-center justify-between mb-1">
                  <div className="flex items-center gap-2 text-xs font-semibold text-rose-700">
                    <Tv className="w-4 h-4 text-rose-600" />
                    <span>Category Block</span>
                  </div>
                  <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200">
                    ENTERTAINMENT
                  </span>
                </div>
                <div className="text-xs font-semibold text-slate-900">Netflix ₹3,000</div>
                <div className="text-[11px] text-slate-500 mt-0.5 font-normal">Entertainment category blocked</div>
              </button>
            </div>
          </div>
        </div>

        {/* Natural Language Prompt Input */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-semibold text-slate-700">
              Natural Language Task Input
            </span>
            {prepLoading && (
              <span className="flex items-center gap-1.5 text-xs text-[#305EFF] font-normal">
                <Sparkles className="w-3.5 h-3.5 animate-spin" />
                Preparing task details...
              </span>
            )}
          </div>
          <div className="flex items-center bg-white border border-slate-200 rounded-lg p-1.5 focus-within:border-[#305EFF] focus-within:ring-1 focus-within:ring-[#305EFF] transition-colors">
            <input
              type="text"
              id="agent-prompt-input"
              placeholder="e.g. 'Book a flight from Ahmedabad to Mumbai under ₹10,000 on September 22'..."
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value)
                setLastTaskResult(null)
              }}
              onBlur={() => handlePrepareTask(prompt)}
              disabled={loading || checkoutLoading}
              className="flex-1 px-3 py-2 bg-transparent text-sm text-slate-900 placeholder-slate-400 focus:outline-hidden disabled:opacity-50 font-normal"
            />
          </div>
        </div>

        {/* ─────────────────────────────────────────────────────────────────────────────
            PREPARED TASK DETAILS & DUAL EXECUTION CHOICES
        ───────────────────────────────────────────────────────────────────────────── */}
        {preparedTask && (
          <div className="p-5 rounded-xl bg-slate-50 border border-slate-200 space-y-4">
            {/* Header / Summary */}
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-200">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-200 flex items-center justify-center text-[#305EFF]">
                  <Plane className="w-4 h-4" />
                </div>
                <div>
                  <div className="text-xs font-semibold text-slate-900">Prepared Task Details</div>
                  <div className="text-xs text-slate-500 font-normal">{preparedTask.summary}</div>
                </div>
              </div>

              {/* Status Badge & Run Again */}
              <div className="flex items-center gap-2">
                {isTaskCompleted && (
                  <button
                    type="button"
                    onClick={handleRunAgain}
                    disabled={loading || checkoutLoading}
                    className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-white border border-slate-200 hover:bg-slate-50 text-slate-700 text-xs font-medium transition-colors cursor-pointer disabled:opacity-50"
                    title="Prepare a fresh demo run (leaves past transactions immutable)"
                  >
                    <RotateCw className="w-3.5 h-3.5 text-[#305EFF]" />
                    <span>Run Again</span>
                  </button>
                )}
                {isTaskCompleted ? (
                  <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs font-medium">
                    <Check className="w-3.5 h-3.5" />
                    Payment Completed
                  </span>
                ) : lastTaskResult?.policy_result === 'REJECTED' || lastTaskResult?.task_status === 'REJECTED' ? (
                  <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-rose-50 border border-rose-200 text-rose-700 text-xs font-medium">
                    <ShieldAlert className="w-3.5 h-3.5" />
                    Policy Blocked
                  </span>
                ) : lastTaskResult?.task_status === 'FAILED' || lastTaskResult?.task_status === 'PAYMENT_FAILED' || lastTaskResult?.payment_status === 'FAILED' ? (
                  <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-rose-50 border border-rose-200 text-rose-700 text-xs font-medium">
                    <Zap className="w-3.5 h-3.5" />
                    Payment Failed
                  </span>
                ) : loading || checkoutLoading ? (
                  <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-50 border border-blue-200 text-[#305EFF] text-xs font-medium">
                    <Sparkles className="w-3.5 h-3.5 animate-spin" />
                    Processing...
                  </span>
                ) : (
                  <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-100 border border-slate-200 text-slate-700 text-xs font-medium">
                    <Clock className="w-3.5 h-3.5" />
                    Ready to Execute
                  </span>
                )}
              </div>
            </div>

            {/* Task Parameter Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs">
              <div className="p-3 rounded-lg bg-white border border-slate-200">
                <div className="text-[11px] text-slate-400 font-normal">Route / Target</div>
                <div className="text-slate-900 font-semibold mt-0.5 truncate">
                  {preparedTask.interpreted_request.origin && preparedTask.interpreted_request.destination
                    ? `${preparedTask.interpreted_request.origin} → ${preparedTask.interpreted_request.destination}`
                    : preparedTask.interpreted_request.city || preparedTask.merchant_name || 'Commercial'}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-white border border-slate-200">
                <div className="text-[11px] text-slate-400 font-normal">Target Date</div>
                <div className="text-slate-900 font-semibold mt-0.5">
                  {preparedTask.interpreted_request.date || '2026-09-22'}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-white border border-slate-200">
                <div className="text-[11px] text-slate-400 font-normal">Estimated Amount</div>
                <div className="text-[#305EFF] font-semibold mt-0.5">
                  ₹{Number(preparedTask.estimated_amount || 7450).toLocaleString('en-IN')}
                </div>
              </div>

              <div className="p-3 rounded-lg bg-white border border-slate-200">
                <div className="text-[11px] text-slate-400 font-normal">Policy Preview</div>
                <div className="flex items-center gap-1 text-emerald-700 font-semibold mt-0.5">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                  <span>Compliant</span>
                </div>
              </div>
            </div>

            {/* Already Completed Notification */}
            {isTaskCompleted && (
              <div className="p-3.5 rounded-lg bg-emerald-50 border border-emerald-200 text-xs flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-7 h-7 rounded-md bg-emerald-100 text-emerald-700 flex items-center justify-center shrink-0">
                    <CheckCircle2 className="w-4 h-4" />
                  </div>
                  <div>
                    <div className="font-semibold text-emerald-900">
                      Payment Already Completed for this Task
                    </div>
                    <div className="text-[11px] text-emerald-700 mt-0.5">
                      {completedBy === 'AGENT' ? (
                        <span className="font-semibold mr-2">Paid via Autonomous Agent</span>
                      ) : completedBy === 'RAZORPAY' ? (
                        <span className="font-semibold mr-2">Paid via Razorpay Checkout</span>
                      ) : null}
                      Tx ID:{' '}
                      <span className="font-mono font-semibold">
                        {completedTransactionId ? completedTransactionId.substring(0, 8) : 'Verified'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={handleRunAgain}
                    disabled={loading || checkoutLoading}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-white hover:bg-slate-50 text-slate-700 border border-slate-200 font-medium text-xs transition-colors cursor-pointer shrink-0"
                    title="Prepare a fresh demo run (leaves past transactions immutable)"
                  >
                    <RotateCw className="w-3.5 h-3.5 text-[#305EFF]" />
                    <span>Run Again</span>
                  </button>
                  {completedTransactionId && onInspectTransaction && (
                    <button
                      type="button"
                      onClick={() => onInspectTransaction(completedTransactionId)}
                      className="flex items-center gap-1.5 px-3 py-1.5 rounded-md bg-emerald-600 hover:bg-emerald-700 text-white font-medium text-xs transition-colors cursor-pointer shrink-0"
                    >
                      <span>Inspect Tx</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* Execution Method Selection */}
            <div className="pt-2">
              <span className="text-xs font-semibold text-slate-700 block mb-2.5">
                Choose Execution Method
              </span>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {/* Method A: Run Autonomous Agent */}
                <button
                  type="button"
                  id="execute-agent-btn"
                  disabled={agentBtn.type !== 'AVAILABLE' || !prompt.trim()}
                  onClick={handleRunAutonomousAgent}
                  className={`p-3.5 rounded-lg border text-left transition-colors flex items-center justify-between gap-3 relative ${
                    agentBtn.type === 'AVAILABLE'
                      ? 'bg-[#305EFF] hover:bg-[#254cd4] border-[#305EFF] text-white shadow-xs cursor-pointer'
                      : agentBtn.type === 'PROCESSING'
                      ? 'bg-blue-50 border-blue-200 text-blue-800 cursor-wait'
                      : agentBtn.type === 'COMPLETED'
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800 cursor-default'
                      : agentBtn.type === 'ALREADY_PAID'
                      ? 'bg-slate-100 border-slate-200 text-slate-500 cursor-not-allowed opacity-90'
                      : agentBtn.type === 'REJECTED'
                      ? 'bg-rose-50 border-rose-200 text-rose-700 cursor-not-allowed opacity-80'
                      : 'bg-amber-50 border-amber-200 text-amber-700 cursor-not-allowed opacity-80'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-8 h-8 rounded-md flex items-center justify-center shrink-0 ${
                        agentBtn.type === 'AVAILABLE' ? 'bg-white/20 text-white' : 'bg-white'
                      }`}
                    >
                      {agentBtn.type === 'PROCESSING' ? (
                        <Sparkles className="w-4 h-4 animate-spin text-[#305EFF]" />
                      ) : agentBtn.type === 'COMPLETED' ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      ) : agentBtn.type === 'ALREADY_PAID' ? (
                        <Check className="w-4 h-4 text-slate-400" />
                      ) : agentBtn.type === 'REJECTED' ? (
                        <ShieldAlert className="w-4 h-4 text-rose-600" />
                      ) : agentBtn.type === 'FAILED' ? (
                        <Zap className="w-4 h-4 text-rose-600" />
                      ) : (
                        <Send className="w-4 h-4 text-white" />
                      )}
                    </div>
                    <div>
                      <div className="text-xs font-semibold">
                        {agentBtn.title}
                      </div>
                      <div
                        className={`text-[11px] ${
                          agentBtn.type === 'AVAILABLE'
                            ? 'text-blue-100'
                            : agentBtn.type === 'COMPLETED'
                            ? 'text-emerald-700'
                            : agentBtn.type === 'ALREADY_PAID'
                            ? 'text-slate-500'
                            : agentBtn.type === 'REJECTED'
                            ? 'text-rose-600'
                            : 'text-amber-600'
                        }`}
                      >
                        {agentBtn.subtitle}
                      </div>
                    </div>
                  </div>

                  {agentBtn.type === 'AVAILABLE' ? (
                    <ArrowRight className="w-4 h-4 text-white shrink-0" />
                  ) : agentBtn.type === 'PROCESSING' ? (
                    <Sparkles className="w-4 h-4 animate-spin text-[#305EFF] shrink-0" />
                  ) : agentBtn.type === 'COMPLETED' ? (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-200 shrink-0">
                      SUCCESS
                    </span>
                  ) : agentBtn.type === 'ALREADY_PAID' ? (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-200 text-slate-700 border border-slate-300 shrink-0">
                      PAID
                    </span>
                  ) : agentBtn.type === 'REJECTED' ? (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-rose-100 text-rose-700 border border-rose-200 shrink-0">
                      BLOCKED
                    </span>
                  ) : (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200 shrink-0">
                      FAILED
                    </span>
                  )}
                </button>

                {/* Method B: Pay with Razorpay */}
                <button
                  type="button"
                  id="execute-razorpay-btn"
                  disabled={rzpBtn.type !== 'AVAILABLE' || !prompt.trim()}
                  onClick={handleOpenRazorpayCheckout}
                  className={`p-3.5 rounded-lg border text-left transition-colors flex items-center justify-between gap-3 relative ${
                    rzpBtn.type === 'AVAILABLE'
                      ? 'bg-slate-900 hover:bg-slate-800 border-slate-900 text-white shadow-xs cursor-pointer'
                      : rzpBtn.type === 'PROCESSING'
                      ? 'bg-slate-100 border-slate-200 text-slate-800 cursor-wait'
                      : rzpBtn.type === 'COMPLETED'
                      ? 'bg-emerald-50 border-emerald-200 text-emerald-800 cursor-default'
                      : rzpBtn.type === 'ALREADY_PAID'
                      ? 'bg-slate-100 border-slate-200 text-slate-500 cursor-not-allowed opacity-90'
                      : rzpBtn.type === 'REJECTED'
                      ? 'bg-rose-50 border-rose-200 text-rose-700 cursor-not-allowed opacity-80'
                      : 'bg-amber-50 border-amber-200 text-amber-700 cursor-not-allowed opacity-80'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-8 h-8 rounded-md flex items-center justify-center shrink-0 ${
                        rzpBtn.type === 'AVAILABLE' ? 'bg-white/15 text-white' : 'bg-white'
                      }`}
                    >
                      {rzpBtn.type === 'PROCESSING' ? (
                        <Sparkles className="w-4 h-4 animate-spin text-slate-900" />
                      ) : rzpBtn.type === 'COMPLETED' ? (
                        <CheckCircle2 className="w-4 h-4 text-emerald-600" />
                      ) : rzpBtn.type === 'ALREADY_PAID' ? (
                        <Check className="w-4 h-4 text-slate-400" />
                      ) : rzpBtn.type === 'REJECTED' ? (
                        <ShieldAlert className="w-4 h-4 text-rose-600" />
                      ) : rzpBtn.type === 'FAILED' ? (
                        <Zap className="w-4 h-4 text-rose-600" />
                      ) : (
                        <ExternalLink className="w-4 h-4 text-white" />
                      )}
                    </div>
                    <div>
                      <div className="text-xs font-semibold">
                        {rzpBtn.title}
                      </div>
                      <div
                        className={`text-[11px] ${
                          rzpBtn.type === 'AVAILABLE'
                            ? 'text-slate-300'
                            : rzpBtn.type === 'COMPLETED'
                            ? 'text-emerald-700'
                            : rzpBtn.type === 'ALREADY_PAID'
                            ? 'text-slate-500'
                            : rzpBtn.type === 'REJECTED'
                            ? 'text-rose-600'
                            : 'text-amber-600'
                        }`}
                      >
                        {rzpBtn.subtitle}
                      </div>
                    </div>
                  </div>

                  {rzpBtn.type === 'AVAILABLE' ? (
                    <ArrowRight className="w-4 h-4 text-white shrink-0" />
                  ) : rzpBtn.type === 'PROCESSING' ? (
                    <Sparkles className="w-4 h-4 animate-spin text-slate-900 shrink-0" />
                  ) : rzpBtn.type === 'COMPLETED' ? (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-emerald-100 text-emerald-800 border border-emerald-200 shrink-0">
                      SUCCESS
                    </span>
                  ) : rzpBtn.type === 'ALREADY_PAID' ? (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-slate-200 text-slate-700 border border-slate-300 shrink-0">
                      PAID
                    </span>
                  ) : rzpBtn.type === 'REJECTED' ? (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-rose-100 text-rose-700 border border-rose-200 shrink-0">
                      BLOCKED
                    </span>
                  ) : (
                    <span className="text-[10px] font-medium px-2 py-0.5 rounded bg-amber-100 text-amber-700 border border-amber-200 shrink-0">
                      FAILED
                    </span>
                  )}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* ─────────────────────────────────────────────────────────────────────────────
          RICH RESULT CARDS (Flight, Restaurant, Policy Rejection, Direct Payment)
          Rendered directly under active task controls so result is immediately visible! (Req 5)
      ───────────────────────────────────────────────────────────────────────────── */}
      {lastTaskResult && !loading && !checkoutLoading && (
        <div ref={resultCardRef} className="scroll-mt-6">
          <AutonomousResultCard
            result={lastTaskResult}
            onInspectTransaction={onInspectTransaction}
          />
        </div>
      )}

      {/* ─────────────────────────────────────────────────────────────────────────────
          AUTONOMOUS EXECUTION TIMELINE (8 Verified Stages)
      ───────────────────────────────────────────────────────────────────────────── */}
      {(loading || checkoutLoading || lastTaskResult) && (
        <TaskExecutionTimeline
          taskResult={lastTaskResult}
          loading={loading || checkoutLoading}
          activeStep={activeStep}
          currentStage={executionStage}
          userPrompt={prompt}
        />
      )}
    </div>
  )
}
