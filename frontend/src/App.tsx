import { useState, useEffect, useCallback } from 'react'
import { Navbar, type NavigationTab } from './components/Navbar'
import { WalletCard } from './components/WalletCard'
import { AgentConsole } from './components/AgentConsole'
import { TransactionTable } from './components/TransactionTable'
import { TransactionDetail } from './components/TransactionDetail'
import { SystemActivity } from './components/SystemActivity'
import { PolicyCheckMatrix } from './components/PolicyCheckMatrix'
import { ErrorAlert } from './components/Common'
import { api } from './api/client'
import {
  CheckCircle2,
  Cpu,
  KeyRound,
  CreditCard,
  QrCode,
  Shield,
  RotateCw,
  User,
  Lock,
  Bell,
  ChevronRight,
} from 'lucide-react'
import type {
  HealthResponse,
  WalletSummary,
  Transaction,
  TransactionDetail as TransactionDetailType,
  AuditLog,
  AgentRunResponse,
  TaskRunResponse,
} from './types'

export function App() {
  const [activeTab, setActiveTab] = useState<NavigationTab>('dashboard')
  const [health, setHealth] = useState<HealthResponse | null>(null)
  const [wallet, setWallet] = useState<WalletSummary | null>(null)
  const [transactions, setTransactions] = useState<Transaction[]>([])
  const [auditLogs, setAuditLogs] = useState<AuditLog[]>([])
  const [selectedTransaction, setSelectedTransaction] = useState<TransactionDetailType | null>(null)
  const [loading, setLoading] = useState<boolean>(true)
  const [agentLoading, setAgentLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)

  const loadData = useCallback(async (showLoading = true) => {
    if (showLoading) setLoading(true)
    setError(null)
    try {
      const [healthData, walletData, txData, logsData] = await Promise.all([
        api.getHealth().catch((e) => {
          console.warn('Health check failed:', e)
          return null
        }),
        api.getWallet().catch((e) => {
          console.warn('Wallet fetch failed:', e)
          return null
        }),
        api.getTransactions().catch((e) => {
          console.warn('Transactions fetch failed:', e)
          return []
        }),
        api.getAuditLogs().catch((e) => {
          console.warn('Audit logs fetch failed:', e)
          return []
        }),
      ])

      setHealth(healthData)
      setWallet(walletData)
      setTransactions(txData)
      setAuditLogs(logsData)
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Failed to load AgentPay data.'
      setError(msg)
    } finally {
      if (showLoading) setLoading(false)
    }
  }, [])

  useEffect(() => {
    let ignore = false
    const init = async () => {
      try {
        const [healthData, walletData, txData, logsData] = await Promise.all([
          api.getHealth().catch(() => null),
          api.getWallet().catch(() => null),
          api.getTransactions().catch(() => []),
          api.getAuditLogs().catch(() => []),
        ])
        if (!ignore) {
          setHealth(healthData)
          setWallet(walletData)
          setTransactions(txData)
          setAuditLogs(logsData)
          setLoading(false)
        }
      } catch (err: unknown) {
        if (!ignore) {
          setError(err instanceof Error ? err.message : 'Failed to load data')
          setLoading(false)
        }
      }
    }
    init()
    return () => {
      ignore = true
    }
  }, [])

  const handleSelectTransaction = async (tx: Transaction) => {
    try {
      const detail = await api.getTransaction(tx.id)
      setSelectedTransaction(detail)
    } catch (err: unknown) {
      console.error('Failed to load transaction details:', err)
      setSelectedTransaction({
        ...tx,
        payment_attempts: [],
        audit_logs: [],
      })
    }
  }

  const handleRunAgent = async (
    message: string,
    options?: { force_failure?: boolean; retry_if_failed?: boolean }
  ): Promise<AgentRunResponse | null> => {
    setAgentLoading(true)
    setError(null)
    try {
      const response = await api.runAgent({
        message,
        force_failure: options?.force_failure,
        retry_if_failed: options?.retry_if_failed ?? true,
      })

      await loadData(false)

      if (response.payment_id) {
        try {
          const detail = await api.getTransaction(response.payment_id)
          setSelectedTransaction(detail)
        } catch (err) {
          console.warn('Could not load new transaction detail:', err)
        }
      }

      return response
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Agent execution failed.'
      setError(msg)
      return null
    } finally {
      setAgentLoading(false)
    }
  }

  const handleRunTask = async (
    message: string,
    options?: { force_failure?: boolean; retry_if_failed?: boolean }
  ): Promise<TaskRunResponse | null> => {
    setAgentLoading(true)
    setError(null)
    try {
      const response = await api.executeTask({
        message,
        force_failure: options?.force_failure,
        retry_if_failed: options?.retry_if_failed ?? true,
      })

      await loadData(false)

      return response
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Autonomous task execution failed.'
      setError(msg)
      return null
    } finally {
      setAgentLoading(false)
    }
  }

  const handleInspectTransactionById = async (txId: string) => {
    try {
      const detail = await api.getTransaction(txId)
      setSelectedTransaction(detail)
    } catch (err) {
      console.warn('Could not load transaction detail:', err)
    }
  }

  // Greeting helper
  const getGreeting = () => {
    const hour = new Date().getHours()
    if (hour < 12) return 'Good morning'
    if (hour < 17) return 'Good afternoon'
    return 'Good evening'
  }

  return (
    <div className="min-h-screen bg-white text-slate-900 flex flex-col antialiased">
      {/* ── Horizontal Navbar ────────────────────────────────────────────────── */}
      <Navbar activeTab={activeTab} onSelectTab={setActiveTab} />

      {/* ── Main Content ─────────────────────────────────────────────────────── */}
      <main className="flex-1 bg-[#F7F9FC]">
        <div className="max-w-screen-xl mx-auto px-4 sm:px-6 lg:px-8 py-8">

          {/* Error Alert */}
          {error && (
            <div className="mb-6">
              <ErrorAlert
                title="Backend Communication Error"
                message={error}
                onRetry={loadData}
              />
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              DASHBOARD
          ════════════════════════════════════════════════════════════════ */}
          {activeTab === 'dashboard' && (
            <div className="space-y-8">

              {/* Welcome Header */}
              <div className="flex items-start justify-between">
                <div>
                  <h1 className="text-2xl font-bold tracking-tight" style={{ color: '#0d1b3e' }}>
                    {getGreeting()}, Krisha 👋
                  </h1>
                  <p className="text-sm text-slate-500 mt-1">
                    Welcome to AgentPay — Payments infrastructure for AI agents
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => loadData()}
                  disabled={loading}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-slate-200 hover:border-slate-300 hover:bg-slate-50 text-slate-600 text-sm font-medium transition-colors cursor-pointer disabled:opacity-50"
                  title="Refresh data"
                >
                  <RotateCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                  <span className="hidden sm:inline">Refresh</span>
                </button>
              </div>

              {/* Row 1: Wallet + Agent Console */}
              <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
                <div className="lg:col-span-4">
                  <WalletCard
                    wallet={wallet}
                    loading={loading}
                    onWalletUpdated={loadData}
                  />
                </div>
                <div className="lg:col-span-8">
                  <AgentConsole
                    onRunAgent={handleRunAgent}
                    onRunTask={handleRunTask}
                    loading={agentLoading}
                    onPaymentVerified={loadData}
                    onInspectTransaction={handleInspectTransactionById}
                  />
                </div>
              </div>

              {/* Row 2: Recent Activity (compact — 5 rows, no search) */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-base font-semibold" style={{ color: '#0d1b3e' }}>
                    Recent Activity
                  </h2>
                  <button
                    type="button"
                    onClick={() => setActiveTab('transactions')}
                    className="text-sm font-medium transition-colors cursor-pointer"
                    style={{ color: '#305EFF' }}
                  >
                    View all →
                  </button>
                </div>
                <RecentActivity
                  transactions={transactions}
                  loading={loading}
                  onSelect={handleSelectTransaction}
                />
              </div>

              {/* Row 3: Trust Summary (compact) */}
              <div>
                <div className="flex items-center justify-between mb-4">
                  <h2 className="text-base font-semibold" style={{ color: '#0d1b3e' }}>
                    Audit & Trust
                  </h2>
                  <button
                    type="button"
                    onClick={() => setActiveTab('audit')}
                    className="text-sm font-medium transition-colors cursor-pointer"
                    style={{ color: '#305EFF' }}
                  >
                    View all →
                  </button>
                </div>
                <SystemActivity logs={auditLogs} loading={loading} />
              </div>
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              AUTONOMOUS TASKS
          ════════════════════════════════════════════════════════════════ */}
          {activeTab === 'tasks' && (
            <div className="space-y-6">
              <PageHeader
                title="Autonomous Tasks"
                description="Execute autonomous commerce workflows with deterministic policy enforcement."
              />
              <AgentConsole
                onRunAgent={handleRunAgent}
                onRunTask={handleRunTask}
                loading={agentLoading}
                onPaymentVerified={loadData}
                onInspectTransaction={handleInspectTransactionById}
              />
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              PAYMENTS
          ════════════════════════════════════════════════════════════════ */}
          {activeTab === 'payments' && (
            <div className="space-y-6">
              <PageHeader
                title="Payments"
                description="Primary and fallback payment rails with idempotency protection."
              />
              <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                <div className="lg:col-span-1">
                  <WalletCard wallet={wallet} loading={loading} onWalletUpdated={loadData} />
                </div>
                <div className="lg:col-span-2">
                  <TransactionTable
                    transactions={transactions}
                    loading={loading}
                    onSelectTransaction={handleSelectTransaction}
                  />
                </div>
              </div>
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              WALLET
          ════════════════════════════════════════════════════════════════ */}
          {activeTab === 'wallet' && (
            <div className="space-y-6">
              <PageHeader
                title="Wallet"
                description="Real-time spending limits, balance, and configured payment rails."
              />
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
                <WalletCard wallet={wallet} loading={loading} onWalletUpdated={loadData} />

                {/* Wallet Security Guarantees */}
                <div className="bg-white border border-slate-200 rounded-xl p-6 space-y-4">
                  <h3 className="text-sm font-semibold" style={{ color: '#0d1b3e' }}>
                    Security Guarantees
                  </h3>
                  <p className="text-xs text-slate-500">
                    Deterministic controls enforced by the AgentPay policy engine:
                  </p>
                  <div className="space-y-3">
                    {[
                      {
                        title: 'Daily Spending Cap',
                        detail: `Limits autonomous agent spend to ₹${(wallet?.daily_spending_limit ?? 15000).toLocaleString('en-IN')} per 24-hour cycle.`,
                      },
                      {
                        title: 'Per-Transaction Ceiling',
                        detail: `Caps single autonomous authorization at ₹${(wallet?.per_transaction_limit ?? 8000).toLocaleString('en-IN')}.`,
                      },
                      {
                        title: 'Atomic Idempotency',
                        detail: 'Replays duplicate task intents without creating secondary charges.',
                      },
                    ].map((item) => (
                      <div
                        key={item.title}
                        className="flex items-start gap-3 p-3 rounded-lg bg-slate-50 border border-slate-100"
                      >
                        <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0 mt-0.5" />
                        <div>
                          <div className="text-xs font-semibold text-slate-800">{item.title}</div>
                          <div className="text-xs text-slate-500 mt-0.5">{item.detail}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                  <div className="pt-3 border-t border-slate-100 text-xs text-slate-400">
                    Policy Engine Active · Single-Tenant Vault
                  </div>
                </div>
              </div>
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              POLICIES
          ════════════════════════════════════════════════════════════════ */}
          {activeTab === 'policies' && (
            <div className="space-y-6">
              <PageHeader
                title="Policies"
                description="Deterministic rules evaluated on every agent payment intent before execution."
              />

              {/* Policy rules matrix */}
              <div className="bg-white border border-slate-200 rounded-xl p-6">
                <PolicyCheckMatrix
                  rulesChecked={[
                    { rule: 'Daily Limit Check', passed: true, details: 'Total today under daily limit' },
                    { rule: 'Per-Transaction Limit', passed: true, details: `Amount ≤ ₹${(wallet?.per_transaction_limit ?? 8000).toLocaleString('en-IN')}` },
                    { rule: 'Merchant Allowed Check', passed: true, details: 'Recipient is on approved merchant whitelist' },
                    { rule: 'Category Check', passed: true, details: 'Allowed categories: Travel, Dining, Utilities' },
                    { rule: 'Wallet Balance Check', passed: true, details: 'Adequate balance in AgentPay ledger' },
                    { rule: 'Idempotency Protection', passed: true, details: 'Unique idempotency key verified' },
                  ]}
                  isApproved={true}
                  decisionCode="ALL_POLICIES_PASSING"
                />
              </div>

              {/* Policy limits overview */}
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {[
                  {
                    label: 'Per-Transaction Limit',
                    value: `₹${(wallet?.per_transaction_limit ?? 8000).toLocaleString('en-IN')}`,
                    color: 'text-[#305EFF]',
                  },
                  {
                    label: 'Daily Spending Limit',
                    value: `₹${(wallet?.daily_spending_limit ?? 15000).toLocaleString('en-IN')}`,
                    color: 'text-[#305EFF]',
                  },
                  {
                    label: 'Allowed Categories',
                    value: 'Travel, Dining, Utilities',
                    color: 'text-emerald-600',
                    small: true,
                  },
                  {
                    label: 'Blocked Categories',
                    value: 'Gambling, Crypto, Adult',
                    color: 'text-rose-500',
                    small: true,
                  },
                ].map((item) => (
                  <div key={item.label} className="bg-white border border-slate-200 rounded-xl p-4">
                    <div className="text-xs text-slate-500 mb-1">{item.label}</div>
                    <div className={`font-semibold text-sm ${item.color}`}>{item.value}</div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              TRANSACTIONS
          ════════════════════════════════════════════════════════════════ */}
          {activeTab === 'transactions' && (
            <div className="space-y-6">
              <PageHeader
                title="Transactions"
                description="Search, filter, and inspect immutable transaction records."
              />
              <TransactionTable
                transactions={transactions}
                loading={loading}
                onSelectTransaction={handleSelectTransaction}
              />
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              AUDIT & TRUST
          ════════════════════════════════════════════════════════════════ */}
          {activeTab === 'audit' && (
            <div className="space-y-6">
              <PageHeader
                title="Audit & Trust"
                description="Verifiable event stream recording all agent decisions and payment attempts."
              />

              {/* Core principle callout */}
              <div
                className="rounded-xl border p-5"
                style={{ backgroundColor: '#EFF4FF', borderColor: '#c7d8ff' }}
              >
                <div className="flex items-start gap-3">
                  <Shield className="w-5 h-5 mt-0.5 shrink-0" style={{ color: '#305EFF' }} />
                  <div>
                    <div className="text-sm font-semibold" style={{ color: '#0d1b3e' }}>
                      The AgentPay Trust Principle
                    </div>
                    <div className="text-sm text-slate-600 mt-1 leading-relaxed">
                      The AI agent may <strong>request</strong> a payment.{' '}
                      <strong>AgentPay's Policy Engine</strong> decides whether money may move —
                      never the LLM alone.
                    </div>
                  </div>
                </div>
              </div>

              <SystemActivity logs={auditLogs} loading={loading} />
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              PROFILE
          ════════════════════════════════════════════════════════════════ */}
          {activeTab === 'profile' && (
            <div className="space-y-6 max-w-2xl">
              <PageHeader
                title="Profile"
                description="Your account and payment preferences."
              />

              {/* Identity card */}
              <div className="bg-white border border-slate-200 rounded-xl p-6">
                <div className="flex items-center gap-4 pb-5 border-b border-slate-100">
                  <div
                    className="w-14 h-14 rounded-full flex items-center justify-center text-white font-bold text-xl shrink-0"
                    style={{ backgroundColor: '#305EFF' }}
                  >
                    K
                  </div>
                  <div>
                    <div className="text-lg font-bold" style={{ color: '#0d1b3e' }}>
                      Krisha
                    </div>
                    <div className="text-sm text-slate-500">Personal Account</div>
                    <div className="inline-flex items-center gap-1.5 mt-1.5 px-2 py-0.5 bg-emerald-50 border border-emerald-200 rounded-full">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                      <span className="text-xs font-medium text-emerald-700">Active</span>
                    </div>
                  </div>
                </div>

                <div className="pt-5 space-y-4">
                  <ProfileRow icon={<User className="w-4 h-4" />} label="Name" value="Krisha" />
                  <ProfileRow
                    icon={<CreditCard className="w-4 h-4" />}
                    label="Primary Payment"
                    value={
                      wallet?.payment_methods?.[0]?.token_or_alias
                        ? wallet.payment_methods[0].token_or_alias
                        : 'krisha.agent@icici'
                    }
                  />
                  <ProfileRow
                    icon={<Lock className="w-4 h-4" />}
                    label="Account Security"
                    value="Policy Engine Protected"
                  />
                </div>
              </div>

              {/* Notification preferences */}
              <div className="bg-white border border-slate-200 rounded-xl p-6">
                <h3 className="text-sm font-semibold mb-4" style={{ color: '#0d1b3e' }}>
                  Preferences
                </h3>
                <div className="space-y-3">
                  {[
                    { label: 'Payment Notifications', value: 'Enabled' },
                    { label: 'Policy Alert Notifications', value: 'Enabled' },
                    { label: 'Audit Log Access', value: 'Full Access' },
                  ].map((pref) => (
                    <div key={pref.label} className="flex items-center justify-between py-2 border-b border-slate-50 last:border-0">
                      <div className="flex items-center gap-2.5">
                        <Bell className="w-3.5 h-3.5 text-slate-400" />
                        <span className="text-sm text-slate-700">{pref.label}</span>
                      </div>
                      <span className="text-xs font-medium text-emerald-600">{pref.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          )}

          {/* ════════════════════════════════════════════════════════════════
              SETTINGS
          ════════════════════════════════════════════════════════════════ */}
          {activeTab === 'settings' && (
            <div className="space-y-6 max-w-2xl">
              <PageHeader
                title="Settings"
                description="Payment rails, security, and autonomous agent configuration."
              />

              {/* Payment Adapters */}
              <SettingsSection
                icon={<Cpu className="w-4 h-4" />}
                title="Payment Rails"
                description="Active settlement integrations"
              >
                <div className="space-y-2">
                  <SettingsRow
                    label="Primary Rail"
                    value={health?.provider === 'RAZORPAY' ? 'Razorpay Test Mode' : 'Razorpay Test Mode'}
                    valueColor="text-emerald-600"
                  />
                  <SettingsRow
                    label="Fallback Rail"
                    value="Deterministic Mock Rail"
                    valueColor="text-[#305EFF]"
                  />
                </div>
              </SettingsSection>

              {/* Security */}
              <SettingsSection
                icon={<KeyRound className="w-4 h-4" />}
                title="Security"
                description="Zero-compromise safety invariants"
              >
                <div className="p-3 rounded-lg bg-slate-50 border border-slate-100">
                  <div className="text-sm font-medium text-slate-800">LLM Authorization Isolation</div>
                  <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                    The LLM may only request payments. The deterministic Policy Engine governs movement of funds.
                  </p>
                </div>
              </SettingsSection>

              {/* Autonomous Agent */}
              <SettingsSection
                icon={<Shield className="w-4 h-4" />}
                title="Autonomous Agent"
                description="Configured spending and category limits"
              >
                <div className="space-y-2">
                  <SettingsRow
                    label="Per-Transaction Limit"
                    value={`₹${(wallet?.per_transaction_limit ?? 8000).toLocaleString('en-IN')}`}
                  />
                  <SettingsRow
                    label="Daily Spending Limit"
                    value={`₹${(wallet?.daily_spending_limit ?? 15000).toLocaleString('en-IN')}`}
                  />
                  <SettingsRow label="Allowed Categories" value="Travel, Dining, Utilities" />
                </div>
              </SettingsSection>

              {/* Configured Payment Methods */}
              <SettingsSection
                icon={<QrCode className="w-4 h-4" />}
                title="Payment Methods"
                description="Registered payment instruments"
              >
                <div className="space-y-2">
                  {(wallet?.payment_methods?.length
                    ? wallet.payment_methods
                    : [
                        { id: '1', type: 'UPI_VPA', token_or_alias: 'krisha.agent@icici', is_primary: true, priority: 1 },
                        { id: '2', type: 'CARD_TOKEN', token_or_alias: 'Corporate Visa •••• 4082', is_primary: false, priority: 2 },
                      ]
                  ).map((pm, i) => (
                    <div key={pm.id || i} className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-100">
                      <div className="flex items-center gap-2.5">
                        {pm.type === 'UPI_VPA' ? (
                          <QrCode className="w-3.5 h-3.5 text-emerald-500" />
                        ) : (
                          <CreditCard className="w-3.5 h-3.5" style={{ color: '#305EFF' }} />
                        )}
                        <span className="text-sm text-slate-700 font-medium">{pm.token_or_alias}</span>
                      </div>
                      <span className={`text-xs font-medium ${pm.is_primary || pm.priority === 1 ? 'text-[#305EFF]' : 'text-slate-400'}`}>
                        {pm.is_primary || pm.priority === 1 ? 'Primary' : 'Fallback'}
                      </span>
                    </div>
                  ))}
                </div>
              </SettingsSection>
            </div>
          )}

        </div>
      </main>

      {/* Transaction Detail Modal */}
      {selectedTransaction && (
        <TransactionDetail
          transaction={selectedTransaction}
          onClose={() => setSelectedTransaction(null)}
        />
      )}

      {/* Footer */}
      <footer className="bg-white border-t border-slate-200 py-5">
        <div className="max-w-screen-xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-2">
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <div
              className="w-5 h-5 rounded flex items-center justify-center"
              style={{ backgroundColor: '#305EFF' }}
            >
              <Shield className="w-3 h-3 text-white" />
            </div>
            <span>AgentPay — Permissioned Autonomous Payment Infrastructure</span>
          </div>
          <div className="flex items-center gap-1.5 text-xs text-slate-400">
            <span
              className={`w-1.5 h-1.5 rounded-full ${health?.status === 'ok' ? 'bg-emerald-500' : 'bg-slate-300'}`}
            />
            <span>{health?.status === 'ok' ? 'System Online' : 'Connecting...'}</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

/* ══════════════════════════════════════════════════════════════════════════
   SMALL INLINE COMPONENTS (dashboard + settings helpers)
══════════════════════════════════════════════════════════════════════════ */

// Page header used across all non-dashboard tabs
function PageHeader({ title, description }: { title: string; description: string }) {
  return (
    <div className="pb-2">
      <h1 className="text-xl font-bold tracking-tight" style={{ color: '#0d1b3e' }}>
        {title}
      </h1>
      <p className="text-sm text-slate-500 mt-0.5">{description}</p>
    </div>
  )
}

// Compact recent-activity list for the dashboard (no search, max 5 rows)
function RecentActivity({
  transactions,
  loading,
  onSelect,
}: {
  transactions: Transaction[]
  loading: boolean
  onSelect: (tx: Transaction) => void
}) {
  const recent = transactions.slice(0, 5)

  const statusColor = (status: string) => {
    const s = status.toUpperCase()
    if (s === 'SUCCESS' || s === 'APPROVED') return 'text-emerald-600 bg-emerald-50'
    if (s === 'REJECTED' || s === 'FAILED') return 'text-rose-600 bg-rose-50'
    if (s === 'PENDING' || s === 'PAYMENT_PENDING') return 'text-amber-600 bg-amber-50'
    return 'text-slate-500 bg-slate-100'
  }

  const formatDate = (iso: string) => {
    try {
      return new Date(iso).toLocaleDateString('en-IN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        hour12: true,
      })
    } catch {
      return iso
    }
  }

  if (loading) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl divide-y divide-slate-100">
        {[1, 2, 3].map((i) => (
          <div key={i} className="px-5 py-4 flex items-center gap-4 animate-pulse">
            <div className="w-8 h-8 rounded-lg bg-slate-100 shrink-0" />
            <div className="flex-1 space-y-1.5">
              <div className="h-3 bg-slate-100 rounded w-1/3" />
              <div className="h-2.5 bg-slate-100 rounded w-1/4" />
            </div>
            <div className="h-3 bg-slate-100 rounded w-16" />
          </div>
        ))}
      </div>
    )
  }

  if (recent.length === 0) {
    return (
      <div className="bg-white border border-slate-200 rounded-xl px-5 py-10 text-center text-sm text-slate-400">
        No transactions yet. Run an agent task to create one.
      </div>
    )
  }

  return (
    <div className="bg-white border border-slate-200 rounded-xl divide-y divide-slate-100">
      {recent.map((tx) => (
        <button
          key={tx.id}
          type="button"
          onClick={() => onSelect(tx)}
          className="w-full px-5 py-4 flex items-center gap-4 hover:bg-slate-50 transition-colors cursor-pointer text-left"
        >
          <div className="w-8 h-8 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
            <CreditCard className="w-4 h-4 text-slate-400" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-slate-800 truncate">{tx.merchant_name}</div>
            <div className="text-xs text-slate-400 mt-0.5">{formatDate(tx.created_at)}</div>
          </div>
          <div className="text-right shrink-0">
            <div className="text-sm font-semibold" style={{ color: '#0d1b3e' }}>
              ₹{tx.amount.toLocaleString('en-IN')}
            </div>
            <span
              className={`inline-block text-xs font-medium px-1.5 py-0.5 rounded mt-0.5 ${statusColor(tx.status)}`}
            >
              {tx.status}
            </span>
          </div>
          <ChevronRight className="w-4 h-4 text-slate-300 shrink-0" />
        </button>
      ))}
    </div>
  )
}

// Profile row helper
function ProfileRow({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode
  label: string
  value: string
}) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-slate-50 last:border-0">
      <div className="flex items-center gap-2.5 text-slate-500">
        <span>{icon}</span>
        <span className="text-sm">{label}</span>
      </div>
      <span className="text-sm font-medium text-slate-800">{value}</span>
    </div>
  )
}

// Settings section card
function SettingsSection({
  icon,
  title,
  description,
  children,
}: {
  icon: React.ReactNode
  title: string
  description: string
  children: React.ReactNode
}) {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 space-y-4">
      <div className="flex items-center gap-2.5">
        <div
          className="w-8 h-8 rounded-lg flex items-center justify-center"
          style={{ backgroundColor: '#EFF4FF', color: '#305EFF' }}
        >
          {icon}
        </div>
        <div>
          <div className="text-sm font-semibold" style={{ color: '#0d1b3e' }}>
            {title}
          </div>
          <div className="text-xs text-slate-500">{description}</div>
        </div>
      </div>
      {children}
    </div>
  )
}

// Settings key-value row
function SettingsRow({
  label,
  value,
  valueColor = 'text-slate-700',
}: {
  label: string
  value: string
  valueColor?: string
}) {
  return (
    <div className="flex items-center justify-between p-3 rounded-lg bg-slate-50 border border-slate-100">
      <span className="text-sm text-slate-600 font-medium">{label}</span>
      <span className={`text-sm font-semibold ${valueColor}`}>{value}</span>
    </div>
  )
}

export default App
