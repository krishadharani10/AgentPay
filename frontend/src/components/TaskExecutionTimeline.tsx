import React from 'react'
import {
  BrainCircuit,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Loader2,
  Clock,
} from 'lucide-react'
import type { TaskRunResponse } from '../types'

export type ExecutionStage =
  | 'IDLE'
  | 'STARTING'
  | 'UNDERSTANDING_REQUEST'
  | 'SEARCHING_OPTIONS'
  | 'OPTION_SELECTED'
  | 'CREATING_PAYMENT_INTENT'
  | 'POLICY_CHECK'
  | 'PAYMENT_PROCESSING'
  | 'FINALIZING_BOOKING'
  | 'SUCCESS'
  | 'REJECTED'
  | 'FAILED'

export type StepStatus = 'pending' | 'running' | 'success' | 'rejected' | 'failed'

export interface TimelineStepItem {
  id: number
  key: string
  stage: ExecutionStage
  title: string
  description?: string
  status: StepStatus
  detail?: string
}

interface TaskExecutionTimelineProps {
  taskResult: TaskRunResponse | null
  loading: boolean
  activeStep?: number
  currentStage?: ExecutionStage
  userPrompt?: string
}

export const TaskExecutionTimeline: React.FC<TaskExecutionTimelineProps> = ({
  taskResult,
  loading,
  activeStep = 0,
  currentStage = 'IDLE',
  userPrompt = '',
}) => {
  // Determine step states based on real taskResult or progressive execution stage
  const computeSteps = (): TimelineStepItem[] => {
    const isFlight = taskResult?.task_type === 'BOOK_FLIGHT'
    const isRestaurant = taskResult?.task_type === 'RESERVE_RESTAURANT'

    const policyPassed = taskResult?.policy_result === 'APPROVED'
    const policyRejected = taskResult?.policy_result === 'REJECTED'
    const toolFailed =
      taskResult?.task_status === 'TOOL_FAILED' || taskResult?.task_constraint_result === 'FAIL'
    const paymentSuccess = taskResult?.payment_status === 'SUCCESS'
    const paymentFailed = taskResult?.payment_status === 'FAILED'
    const isAlreadyCompleted = taskResult?.already_completed || false

    if (loading) {
      return [
        {
          id: 1,
          key: 'starting',
          stage: 'STARTING',
          title: 'Starting pipeline',
          status: activeStep >= 1 ? (activeStep === 1 ? 'running' : 'success') : 'pending',
          detail: userPrompt
            ? `Prompt: "${userPrompt.substring(0, 42)}..."`
            : 'Autonomous pipeline starting',
        },
        {
          id: 2,
          key: 'understanding',
          stage: 'UNDERSTANDING_REQUEST',
          title: 'Understanding request',
          status: activeStep >= 2 ? (activeStep === 2 ? 'running' : 'success') : 'pending',
          detail: 'Extracting structured TaskIntent (constraints, budget, dates)',
        },
        {
          id: 3,
          key: 'searching',
          stage: 'SEARCHING_OPTIONS',
          title: 'Searching options',
          status: activeStep >= 3 ? (activeStep === 3 ? 'running' : 'success') : 'pending',
          detail: 'Scanning deterministic mock commerce inventory',
        },
        {
          id: 4,
          key: 'selected',
          stage: 'OPTION_SELECTED',
          title: 'Option selected',
          status: activeStep >= 4 ? (activeStep === 4 ? 'running' : 'success') : 'pending',
          detail: 'Comparing prices against user constraints',
        },
        {
          id: 5,
          key: 'intent',
          stage: 'CREATING_PAYMENT_INTENT',
          title: 'Creating payment intent',
          status: activeStep >= 5 ? (activeStep === 5 ? 'running' : 'success') : 'pending',
          detail: 'Generating authoritative TransactionIntent for Policy Engine',
        },
        {
          id: 6,
          key: 'policy',
          stage: 'POLICY_CHECK',
          title: 'Policy Engine check',
          status: activeStep >= 6 ? (activeStep === 6 ? 'running' : 'success') : 'pending',
          detail: 'Evaluating spending limits, merchant whitelist & category rules',
        },
        {
          id: 7,
          key: 'payment',
          stage: 'PAYMENT_PROCESSING',
          title: 'Payment processing',
          status: activeStep >= 7 ? (activeStep === 7 ? 'running' : 'success') : 'pending',
          detail: 'Calling PaymentService & settlement rail (Razorpay / Mock)',
        },
        {
          id: 8,
          key: 'finalizing',
          stage: 'FINALIZING_BOOKING',
          title: 'Finalizing booking',
          status: activeStep >= 8 ? (activeStep === 8 ? 'running' : 'success') : 'pending',
          detail: 'Persisting confirmation & immutable audit events',
        },
      ]
    }

    if (!taskResult) {
      // IDLE state before user clicks an execution method
      return [
        {
          id: 1,
          key: 'starting',
          stage: 'STARTING',
          title: 'Starting pipeline',
          status: 'pending',
          detail: 'Ready for autonomous execution',
        },
        {
          id: 2,
          key: 'understanding',
          stage: 'UNDERSTANDING_REQUEST',
          title: 'Understanding request',
          status: 'pending',
          detail: 'Will parse natural language into structured parameters',
        },
        {
          id: 3,
          key: 'searching',
          stage: 'SEARCHING_OPTIONS',
          title: 'Searching options',
          status: 'pending',
          detail: 'Will search real-time available inventory',
        },
        {
          id: 4,
          key: 'selected',
          stage: 'OPTION_SELECTED',
          title: 'Option selected',
          status: 'pending',
          detail: 'Will evaluate optimal option matching criteria',
        },
        {
          id: 5,
          key: 'intent',
          stage: 'CREATING_PAYMENT_INTENT',
          title: 'Creating payment intent',
          status: 'pending',
          detail: 'Will create TransactionIntent payload',
        },
        {
          id: 6,
          key: 'policy',
          stage: 'POLICY_CHECK',
          title: 'Policy Engine check',
          status: 'pending',
          detail: 'Will run deterministic policy checks before payment',
        },
        {
          id: 7,
          key: 'payment',
          stage: 'PAYMENT_PROCESSING',
          title: 'Payment processing',
          status: 'pending',
          detail: 'Will settle via Primary or Fallback rail',
        },
        {
          id: 8,
          key: 'finalizing',
          stage: 'FINALIZING_BOOKING',
          title: 'Finalizing booking',
          status: 'pending',
          detail: 'Will issue booking confirmation & update audit log',
        },
      ]
    }

    // Populated state from real backend taskResult
    const req = taskResult.interpreted_request || {}
    const sel = taskResult.selected_option || {}

    // Step 1: Starting pipeline
    const s1: TimelineStepItem = {
      id: 1,
      key: 'starting',
      stage: 'STARTING',
      title: 'Starting pipeline',
      status: 'success',
      detail: `Task initiated: ${taskResult.task_type.replace('_', ' ')}`,
    }

    // Step 2: Understanding request
    let parsedSummary = ''
    if (isFlight) {
      parsedSummary = `${req.origin || 'AMD'} → ${req.destination || 'BOM'} · ${req.date || 'Any Date'} (Budget: ₹${Number(req.max_budget || 10000).toLocaleString('en-IN')})`
    } else if (isRestaurant) {
      parsedSummary = `${req.restaurant_name || req.city || 'Ahmedabad'} · ${req.party_size || 2} guests · ${req.time || '8:00 PM'} (Deposit budget: ₹${Number(req.max_budget || 3000).toLocaleString('en-IN')})`
    } else {
      parsedSummary = `Direct payment: ₹${Number(taskResult.amount || req.budget || req.max_budget || 0).toLocaleString('en-IN')} to ${taskResult.merchant_name || 'Merchant'}`
    }

    const s2: TimelineStepItem = {
      id: 2,
      key: 'understanding',
      stage: 'UNDERSTANDING_REQUEST',
      title: 'Understanding request',
      status: 'success',
      detail: parsedSummary,
    }

    // Step 3: Searching options
    const s3: TimelineStepItem = {
      id: 3,
      key: 'searching',
      stage: 'SEARCHING_OPTIONS',
      title: 'Searching options',
      status: toolFailed ? 'failed' : 'success',
      detail: toolFailed
        ? 'No matching options found within user criteria'
        : isFlight
        ? `Found inventory matches on route ${req.origin || 'AMD'}→${req.destination || 'BOM'}`
        : isRestaurant
        ? `Found reservation slots in ${req.city || 'Ahmedabad'}`
        : 'Payment recipient verified',
    }

    // Step 4: Option selected
    let selectedSummary = ''
    if (sel.flight_number) {
      selectedSummary = `${sel.airline || 'AirDemo'} ${sel.flight_number} (${sel.origin || 'AMD'}→${sel.destination || 'BOM'}) @ ₹${Number(sel.price || 7450).toLocaleString('en-IN')}`
    } else if (sel.restaurant_name) {
      selectedSummary = `${sel.restaurant_name} · ${sel.time_display || sel.time || '8:00 PM'} (Deposit ₹${Number(sel.deposit_amount || 1000).toLocaleString('en-IN')})`
    } else if (taskResult.merchant_name) {
      selectedSummary = `${taskResult.merchant_name} · ₹${Number(taskResult.amount || 0).toLocaleString('en-IN')}`
    } else {
      selectedSummary = 'No valid option selected'
    }

    const s4: TimelineStepItem = {
      id: 4,
      key: 'selected',
      stage: 'OPTION_SELECTED',
      title: 'Option selected',
      status: toolFailed ? 'failed' : 'success',
      detail: toolFailed ? 'Search criteria could not be met' : `Selected: ${selectedSummary}`,
    }

    // Step 5: Creating payment intent
    const s5: TimelineStepItem = {
      id: 5,
      key: 'intent',
      stage: 'CREATING_PAYMENT_INTENT',
      title: 'Creating payment intent',
      status: toolFailed ? 'pending' : 'success',
      detail: toolFailed
        ? 'Payment intent omitted'
        : `TransactionIntent: ₹${Number(taskResult.amount || sel.price || sel.deposit_amount || 0).toLocaleString('en-IN')} to ${taskResult.merchant_name || sel.merchant || 'Merchant'}`,
    }

    // Step 6: Policy Engine check
    let policyDetail = ''
    if (isAlreadyCompleted) {
      policyDetail = 'Idempotent Replay: Policy check was approved on initial execution'
    } else if (policyPassed) {
      policyDetail = 'Approved: All limits, categories, and wallet constraints satisfied'
    } else if (policyRejected) {
      const failedRule = taskResult.rules_checked?.find((r) => !r.passed)
      policyDetail = failedRule
        ? `Rejected by ${failedRule.rule}: ${failedRule.details}`
        : 'Rejected by Policy Engine rule limit'
    } else {
      policyDetail = 'Policy evaluation skipped (no valid option)'
    }

    const s6: TimelineStepItem = {
      id: 6,
      key: 'policy',
      stage: 'POLICY_CHECK',
      title: 'Policy Engine check',
      status:
        isAlreadyCompleted || policyPassed
          ? 'success'
          : policyRejected
          ? 'rejected'
          : toolFailed
          ? 'pending'
          : 'failed',
      detail: policyDetail,
    }

    // Step 7: Payment processing
    let paymentDetail = ''
    if (isAlreadyCompleted) {
      paymentDetail = `Already Completed: Reused existing Tx #${(taskResult.transaction_id || '').substring(0, 8)} (No duplicate charge)`
    } else if (paymentSuccess) {
      paymentDetail = `Success: Settled via PaymentService (Tx #${(taskResult.transaction_id || '').substring(0, 8)})`
    } else if (paymentFailed) {
      paymentDetail = 'Failed: Payment provider rail declined transaction'
    } else if (policyRejected) {
      paymentDetail = 'Not attempted: Blocked by Policy Engine invariant'
    } else {
      paymentDetail = 'Not executed'
    }

    const s7: TimelineStepItem = {
      id: 7,
      key: 'payment',
      stage: 'PAYMENT_PROCESSING',
      title: 'Payment processing',
      status:
        isAlreadyCompleted || paymentSuccess
          ? 'success'
          : paymentFailed
          ? 'failed'
          : policyRejected
          ? 'rejected'
          : 'pending',
      detail: paymentDetail,
    }

    // Step 8: Finalizing booking
    let finalizingStatus: StepStatus = 'pending'
    let finalizingDetail = ''
    if (taskResult.task_status === 'COMPLETED') {
      finalizingStatus = 'success'
      finalizingDetail = isAlreadyCompleted
        ? 'Payment Already Completed: Verified immutable transaction and audit trail'
        : isFlight
        ? 'Flight booking confirmed with verified payment'
        : isRestaurant
        ? 'Restaurant reservation confirmed & deposit captured'
        : 'Task completed successfully'
    } else if (policyRejected) {
      finalizingStatus = 'rejected'
      finalizingDetail = 'Task rejected by AgentPay Policy Engine (Money never moved)'
    } else if (toolFailed) {
      finalizingStatus = 'failed'
      finalizingDetail = 'Task stopped: User criteria could not be fulfilled'
    } else if (paymentFailed) {
      finalizingStatus = 'failed'
      finalizingDetail = 'Task failed: Payment rail error'
    }

    const s8: TimelineStepItem = {
      id: 8,
      key: 'finalizing',
      stage: 'FINALIZING_BOOKING',
      title: policyRejected
        ? 'Task rejected by Policy'
        : toolFailed
        ? 'Task stopped'
        : isAlreadyCompleted
        ? 'Payment Already Completed'
        : 'Finalizing booking',
      status: finalizingStatus,
      detail: finalizingDetail,
    }

    return [s1, s2, s3, s4, s5, s6, s7, s8]
  }

  const steps = computeSteps()

  const getStepIcon = (status: StepStatus, isCurrentRunning: boolean) => {
    if (isCurrentRunning) {
      return <Loader2 className="w-3.5 h-3.5 text-[#305EFF] animate-spin" />
    }
    switch (status) {
      case 'success':
        return <CheckCircle className="w-3.5 h-3.5 text-emerald-600" />
      case 'rejected':
        return <XCircle className="w-3.5 h-3.5 text-rose-600" />
      case 'failed':
        return <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
      case 'running':
        return <Loader2 className="w-3.5 h-3.5 text-[#305EFF] animate-spin" />
      case 'pending':
      default:
        return <Clock className="w-3.5 h-3.5 text-slate-400" />
    }
  }

  const getStepTheme = (status: StepStatus) => {
    switch (status) {
      case 'success':
        return {
          node: 'border-emerald-200 bg-emerald-50 text-emerald-700 shadow-xs',
          text: 'text-slate-900 font-semibold',
          badge: 'bg-emerald-50 text-emerald-700 border-emerald-200',
          badgeText: 'SUCCESS',
        }
      case 'rejected':
        return {
          node: 'border-rose-200 bg-rose-50 text-rose-700 shadow-xs',
          text: 'text-rose-900 font-semibold',
          badge: 'bg-rose-50 text-rose-700 border-rose-200',
          badgeText: 'REJECTED',
        }
      case 'failed':
        return {
          node: 'border-amber-200 bg-amber-50 text-amber-700 shadow-xs',
          text: 'text-amber-900 font-semibold',
          badge: 'bg-amber-50 text-amber-700 border-amber-200',
          badgeText: 'FAILED',
        }
      case 'running':
        return {
          node: 'border-blue-500 bg-blue-50 text-blue-700 ring-2 ring-blue-500/20 animate-pulse',
          text: 'text-blue-900 font-semibold',
          badge: 'bg-blue-50 text-blue-700 border-blue-200',
          badgeText: 'RUNNING',
        }
      case 'pending':
      default:
        return {
          node: 'border-slate-200 bg-slate-100 text-slate-400',
          text: 'text-slate-500 font-normal',
          badge: 'bg-slate-100 text-slate-500 border-slate-200',
          badgeText: 'PENDING',
        }
    }
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-[0_1px_3px_rgba(15,23,42,0.04)]">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-4 pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-blue-50 border border-blue-100 flex items-center justify-center text-[#305EFF]">
            <BrainCircuit className="w-4 h-4" />
          </div>
          <div>
            <h4 className="text-xs font-semibold text-slate-900 uppercase tracking-wider flex items-center gap-2">
              Autonomous Execution Timeline
              {loading && (
                <span className="flex items-center gap-1 text-[10px] text-[#305EFF] lowercase font-normal">
                  <span className="w-1.5 h-1.5 rounded-full bg-[#305EFF] animate-ping" />
                  executing steps...
                </span>
              )}
            </h4>
            <p className="text-[11px] text-slate-500 font-normal mt-0.5">
              Deterministic verification state: IDLE → INTENT → POLICY → SETTLEMENT → AUDIT
            </p>
          </div>
        </div>

        {taskResult ? (
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-blue-50 text-[#305EFF] border border-blue-100 uppercase">
              {currentStage}
            </span>
            {taskResult.already_completed && (
              <span className="text-[11px] font-medium px-2 py-0.5 rounded-md bg-slate-100 text-slate-700 border border-slate-200 uppercase">
                IDEMPOTENT REPLAY
              </span>
            )}
            <span
              className={`text-[11px] font-medium px-2.5 py-1 rounded-md border uppercase tracking-wide ${
                taskResult.task_status === 'COMPLETED'
                  ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                  : taskResult.policy_result === 'REJECTED'
                  ? 'bg-rose-50 text-rose-700 border-rose-200'
                  : 'bg-amber-50 text-amber-700 border-amber-200'
              }`}
            >
              {taskResult.task_status}
            </span>
          </div>
        ) : (
          <span className="text-[11px] font-medium px-2.5 py-1 rounded-md bg-slate-100 text-slate-600 border border-slate-200 uppercase tracking-wide">
            {currentStage} · Ready
          </span>
        )}
      </div>

      {/* Grid of Steps */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
        {steps.map((step) => {
          const theme = getStepTheme(step.status)
          return (
            <div
              key={step.id}
              className={`p-3 rounded-lg border transition-colors relative flex flex-col justify-between ${
                step.status === 'running'
                  ? 'bg-blue-50/50 border-blue-200 shadow-xs'
                  : step.status === 'success'
                  ? 'bg-slate-50/60 border-slate-200 hover:border-slate-300'
                  : step.status === 'rejected'
                  ? 'bg-rose-50/40 border-rose-200'
                  : step.status === 'failed'
                  ? 'bg-amber-50/40 border-amber-200'
                  : 'bg-slate-50/30 border-slate-100 opacity-60'
              }`}
            >
              <div>
                <div className="flex items-center justify-between gap-2 mb-1.5">
                  <div className="flex items-center gap-2">
                    <div
                      className={`w-5 h-5 rounded-md border flex items-center justify-center shrink-0 ${theme.node}`}
                    >
                      {getStepIcon(step.status, step.status === 'running')}
                    </div>
                    <span className="text-[10px] font-mono text-slate-400">
                      0{step.id}
                    </span>
                  </div>
                  <span
                    className={`text-[9px] font-medium px-1.5 py-0.5 rounded border uppercase ${theme.badge}`}
                  >
                    {theme.badgeText}
                  </span>
                </div>

                <div className={`text-xs ${theme.text} leading-tight`}>
                  {step.title}
                </div>
              </div>

              {step.detail && (
                <p className="text-[10px] text-slate-500 mt-2 line-clamp-2 leading-tight bg-white p-1.5 rounded border border-slate-200">
                  {step.detail}
                </p>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}
