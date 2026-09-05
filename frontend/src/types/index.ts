export interface HealthResponse {
  status: string
  app: string
  environment: string
  database: string
  version: string
  provider?: string
  policy_engine?: string
  details?: Record<string, unknown>
}

export interface PaymentMethodItem {
  id: string
  wallet_id?: string
  type: string
  provider: string
  token_or_alias: string
  is_primary: boolean
  is_active: boolean
  priority: number
  created_at?: string
  updated_at?: string
}

export interface WalletSummary {
  id: string
  agent_id: string
  status: string
  daily_spending_limit: number
  per_transaction_limit: number
  currency: string
  payment_methods: PaymentMethodItem[]
  created_at: string
  updated_at: string
  current_daily_spent: number
  remaining_daily_budget: number
}

export type TransactionStatusType =
  | 'REQUESTED'
  | 'POLICY_CHECK'
  | 'APPROVED'
  | 'REJECTED'
  | 'PAYMENT_PENDING'
  | 'SUCCESS'
  | 'FAILED'
  | string

export interface Transaction {
  id: string
  idempotency_key: string
  agent_id: string
  wallet_id: string
  merchant_id?: string | null
  merchant_name: string
  category: string
  amount: number
  currency: string
  status: TransactionStatusType
  decision_reason?: string | null
  payment_method_id?: string | null
  payment_method_type?: string | null
  payment_method_alias?: string | null
  payment_provider?: string | null
  provider_payment_id?: string | null
  created_at: string
  updated_at: string
}

export interface PaymentAttempt {
  id: string
  transaction_id: string
  payment_method_id?: string | null
  payment_method_type?: string | null
  payment_method_alias?: string | null
  attempt_number: number
  status: 'PENDING' | 'SUCCESS' | 'FAILED' | 'TIMEOUT' | string
  provider_payment_id?: string | null
  error_code?: string | null
  error_message?: string | null
  response_payload?: Record<string, unknown> | null
  created_at: string
  updated_at: string
}

export interface PolicyRuleCheck {
  rule: string
  passed: boolean
  details: string
}

export interface AuditLog {
  id: string
  agent_id?: string | null
  transaction_id?: string | null
  event_type: string
  action: string
  decision: string
  reason: string
  rules_checked?: PolicyRuleCheck[] | null
  metadata_payload?: Record<string, unknown> | null
  created_at: string
}

export interface TransactionDetail extends Transaction {
  payment_attempts: PaymentAttempt[]
  audit_logs: AuditLog[]
  merchant_description?: string | null
  merchant_website?: string | null
}

export interface AgentRunRequest {
  message: string
  agent_id?: string
  bill_id?: string
  merchant_name?: string
  amount?: number
  category?: string
  force_failure?: boolean
  retry_if_failed?: boolean
}

export interface AgentRunResponse {
  success: boolean
  decision: string
  decision_code: string
  message: string
  payment_id?: string | null
  provider_payment_id?: string | null
  payment_status?: string | null
  amount?: number | null
  merchant_name?: string | null
  rules_checked?: PolicyRuleCheck[] | null
  remaining_daily_budget?: number | null
  audit_trail?: Array<Record<string, unknown>> | null
}

export interface Merchant {
  id: string
  name: string
  category: string
  description?: string | null
  website?: string | null
  is_active: boolean
}

export interface Policy {
  id: string
  agent_id: string
  name: string
  description?: string | null
  max_transaction_amount: number
  daily_spending_limit: number
  allowed_categories: string[]
  blocked_categories: string[]
  allowed_merchants: string[]
  blocked_merchants: string[]
  wallet_enabled: boolean
  is_active: boolean
}

export interface PaymentProviderConfig {
  provider: 'MOCK' | 'RAZORPAY' | string
  key_id?: string | null
  currency: string
  is_test_mode: boolean
  features: {
    checkout_js: boolean
    direct_upi: boolean
    card_tokenization: boolean
    policy_guard: boolean
  }
}

export interface RazorpayVerifyRequest {
  transaction_id: string
  razorpay_order_id: string
  razorpay_payment_id: string
  razorpay_signature: string
}

export interface RazorpayVerifyResponse {
  success: boolean
  verified: boolean
  transaction_id: string
  status: string
  provider_payment_id: string
  message: string
  details?: Record<string, unknown> | null
}

export interface RazorpayCheckoutOptions {
  key: string
  amount: number
  currency: string
  name: string
  description?: string
  image?: string
  order_id?: string
  handler: (response: {
    razorpay_payment_id: string
    razorpay_order_id: string
    razorpay_signature: string
  }) => void
  prefill?: {
    name?: string
    email?: string
    contact?: string
    method?: string
  }
  notes?: Record<string, string>
  theme?: {
    color?: string
  }
  modal?: {
    ondismiss?: () => void
    confirm_close?: boolean
    escape?: boolean
  }
}

export type TaskType = 'BOOK_FLIGHT' | 'RESERVE_RESTAURANT' | 'DIRECT_PAYMENT'

export interface TaskRunRequest {
  message: string
  agent_id?: string
  force_failure?: boolean
  retry_if_failed?: boolean
  idempotency_key?: string
  demo_run_id?: string
}

export interface TaskRunResponse {
  task_type: TaskType
  interpreted_request: {
    origin?: string
    destination?: string
    city?: string
    date?: string
    time?: string
    party_size?: number
    max_budget?: number
    budget?: number
    merchant?: string
    category?: string
    [key: string]: unknown
  }
  selected_option?: Record<string, any> | null
  task_constraint_result: 'PASS' | 'FAIL' | 'NOT_APPLICABLE' | string
  policy_result: 'APPROVED' | 'REJECTED' | 'NOT_EVALUATED' | string
  transaction_id?: string | null
  payment_status: 'SUCCESS' | 'FAILED' | 'NOT_ATTEMPTED' | 'REJECTED' | string
  task_status: 'COMPLETED' | 'REJECTED' | 'TOOL_FAILED' | 'INVALID_INTENT' | 'PAYMENT_FAILED' | string
  final_message: string
  rules_checked?: PolicyRuleCheck[] | null
  amount?: number | null
  merchant_name?: string | null
  audit_trail?: Array<Record<string, unknown>> | null
  already_completed?: boolean
  payment_provider?: string | null
}

export interface TaskPrepareRequest {
  message: string
  agent_id?: string
  demo_run_id?: string
}

export interface TaskPrepareResponse {
  task_type: TaskType
  interpreted_request: {
    origin?: string
    destination?: string
    city?: string
    date?: string
    time?: string
    party_size?: number
    max_budget?: number
    budget?: number
    merchant?: string
    category?: string
    [key: string]: unknown
  }
  selected_option?: Record<string, any> | null
  idempotency_key: string
  already_completed: boolean
  existing_transaction_id?: string | null
  existing_payment_status?: string | null
  existing_payment_provider?: string | null
  estimated_amount?: number | null
  merchant_name?: string | null
  policy_compliant: boolean
  summary: string
}

