import type {
  HealthResponse,
  WalletSummary,
  Transaction,
  TransactionDetail,
  AuditLog,
  Merchant,
  Policy,
  AgentRunRequest,
  AgentRunResponse,
  PaymentProviderConfig,
  RazorpayVerifyRequest,
  RazorpayVerifyResponse,
  TaskRunRequest,
  TaskRunResponse,
  TaskPrepareRequest,
  TaskPrepareResponse,
} from '../types'


// Use VITE_API_BASE_URL or fallback to relative '/api' proxy or localhost
const API_BASE = import.meta.env.VITE_API_BASE_URL || '/api'

class ApiError extends Error {
  status?: number
  detail?: string
  constructor(message: string, status?: number, detail?: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

async function request<T>(endpoint: string, options: RequestInit = {}): Promise<T> {
  const url = `${API_BASE}${endpoint}`
  const headers = {
    'Content-Type': 'application/json',
    ...(options.headers || {}),
  }

  let res: Response
  try {
    res = await fetch(url, { ...options, headers })
  } catch {
    // If proxy failed, attempt direct backend fallback if on localhost
    try {
      const fallbackUrl = `http://127.0.0.1:8000${endpoint.startsWith('/api') ? endpoint : `/api${endpoint}`}`
      res = await fetch(fallbackUrl, { ...options, headers })
    } catch {
      throw new ApiError(`Unable to connect to AgentPay backend service at ${url}.`)
    }
  }

  if (!res.ok) {
    let errorDetail = `Request failed with status ${res.status}`
    try {
      const errorJson = await res.json()
      if (errorJson.detail) {
        errorDetail = typeof errorJson.detail === 'string' ? errorJson.detail : JSON.stringify(errorJson.detail)
      } else if (errorJson.message) {
        errorDetail = errorJson.message
      }
    } catch {
      // Body not json
    }
    throw new ApiError(errorDetail, res.status, errorDetail)
  }

  return res.json()
}

export const api = {
  getHealth: async (): Promise<HealthResponse> => {
    // Health endpoint is mounted at /health on backend root and accessible via proxy
    try {
      const res = await fetch(`${API_BASE}/health`)
      if (res.ok) return res.json()
    } catch {
      // try root or port 8000
    }
    try {
      const res = await fetch('http://127.0.0.1:8000/health')
      if (res.ok) return res.json()
    } catch {
      // proceed to throw
    }
    return request<HealthResponse>('/health')
  },

  getWallet: async (agentId?: string): Promise<WalletSummary> => {
    const params = agentId ? `?agent_id=${agentId}` : ''
    return request<WalletSummary>(`/wallet${params}`)
  },

  resetDailySpend: async (agentId?: string): Promise<WalletSummary> => {
    const params = agentId ? `?agent_id=${agentId}` : ''
    return request<WalletSummary>(`/wallet/reset-daily-spend${params}`, {
      method: 'POST',
    })
  },

  getTransactions: async (status?: string, limit = 50): Promise<Transaction[]> => {
    const query = new URLSearchParams()
    if (status) query.append('status', status)
    if (limit) query.append('limit', limit.toString())
    const qStr = query.toString() ? `?${query.toString()}` : ''
    return request<Transaction[]>(`/transactions${qStr}`)
  },

  getTransaction: async (transactionId: string): Promise<TransactionDetail> => {
    return request<TransactionDetail>(`/transactions/${transactionId}`)
  },

  getAuditLogs: async (transactionId?: string, limit = 50): Promise<AuditLog[]> => {
    const query = new URLSearchParams()
    if (transactionId) query.append('transaction_id', transactionId)
    if (limit) query.append('limit', limit.toString())
    const qStr = query.toString() ? `?${query.toString()}` : ''
    return request<AuditLog[]>(`/audit-logs${qStr}`)
  },

  getMerchants: async (category?: string): Promise<Merchant[]> => {
    const params = category ? `?category=${category}` : ''
    return request<Merchant[]>(`/merchants${params}`)
  },

  getPolicies: async (agentId?: string): Promise<Policy[]> => {
    const params = agentId ? `?agent_id=${agentId}` : ''
    return request<Policy[]>(`/policies${params}`)
  },

  runAgent: async (payload: AgentRunRequest): Promise<AgentRunResponse> => {
    return request<AgentRunResponse>('/agent/run', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  getPaymentConfig: async (): Promise<PaymentProviderConfig> => {
    return request<PaymentProviderConfig>('/payments/config')
  },

  verifyRazorpayPayment: async (payload: RazorpayVerifyRequest): Promise<RazorpayVerifyResponse> => {
    return request<RazorpayVerifyResponse>('/payments/razorpay/verify', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  prepareTask: async (payload: TaskPrepareRequest): Promise<TaskPrepareResponse> => {
    return request<TaskPrepareResponse>('/tasks/prepare', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },

  executeTask: async (payload: TaskRunRequest): Promise<TaskRunResponse> => {
    return request<TaskRunResponse>('/tasks', {
      method: 'POST',
      body: JSON.stringify(payload),
    })
  },
}


