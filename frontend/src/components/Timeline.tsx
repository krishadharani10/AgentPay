import React from 'react'
import {
  Clock,
  ShieldCheck,
  CreditCard,
  RotateCcw,
  CheckCircle2,
  XCircle,
  Bot,
  Layers,
} from 'lucide-react'
import type { AuditLog, PaymentAttempt } from '../types'

interface TimelineItem {
  timestamp: string
  title: string
  subtitle?: string
  status?: string
  icon: React.ReactNode
  color: 'emerald' | 'rose' | 'amber' | 'blue' | 'purple' | 'slate'
  metadata?: Record<string, unknown> | null
}

interface TimelineProps {
  auditLogs?: AuditLog[]
  paymentAttempts?: PaymentAttempt[]
}

export const Timeline: React.FC<TimelineProps> = ({
  auditLogs = [],
  paymentAttempts = [],
}) => {
  const items: TimelineItem[] = []

  // Add audit logs
  auditLogs.forEach((log) => {
    let color: TimelineItem['color'] = 'blue'
    let icon = <Layers className="w-3.5 h-3.5" />

    const eventType = (log.event_type || '').toUpperCase()
    const decision = (log.decision || '').toUpperCase()

    if (eventType.includes('AGENT') || eventType.includes('INTENT')) {
      icon = <Bot className="w-3.5 h-3.5" />
      color = 'purple'
    } else if (eventType.includes('POLICY')) {
      icon = <ShieldCheck className="w-3.5 h-3.5" />
      color = decision === 'APPROVED' ? 'emerald' : 'rose'
    } else if (eventType.includes('FALLBACK') || eventType.includes('RESET')) {
      icon = <RotateCcw className="w-3.5 h-3.5" />
      color = 'amber'
    } else if (eventType.includes('PAYMENT_RESULT') || eventType.includes('PAYMENT')) {
      icon = <CreditCard className="w-3.5 h-3.5" />
      color = decision === 'SUCCESS' ? 'emerald' : decision === 'FAILED' ? 'rose' : 'blue'
    }

    items.push({
      timestamp: log.created_at,
      title: log.event_type.replace(/_/g, ' '),
      subtitle: log.reason,
      status: log.decision,
      icon,
      color,
      metadata: log.metadata_payload,
    })
  })

  // Add payment attempts
  paymentAttempts.forEach((att) => {
    const isSuccess = att.status === 'SUCCESS'
    items.push({
      timestamp: att.created_at,
      title: `PAYMENT ATTEMPT #${att.attempt_number} (${att.payment_method_type || 'UPI'})`,
      subtitle: isSuccess
        ? `Provider Payment ID: ${att.provider_payment_id || 'Settled'}`
        : `Provider Error: ${att.error_code || 'DECLINED'} — ${att.error_message || 'Declined by network'}`,
      status: att.status,
      icon: isSuccess ? <CheckCircle2 className="w-3.5 h-3.5" /> : <XCircle className="w-3.5 h-3.5" />,
      color: isSuccess ? 'emerald' : 'rose',
      metadata: att.response_payload,
    })
  })

  // Sort chronologically ascending
  items.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime())

  if (items.length === 0) {
    return (
      <div className="py-6 text-center text-xs text-slate-400">
        No audit events recorded for this transaction.
      </div>
    )
  }

  const formatTime = (isoString: string) => {
    try {
      const d = new Date(isoString)
      return d.toLocaleTimeString('en-IN', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
      })
    } catch {
      return isoString
    }
  }

  const getColorClasses = (color: TimelineItem['color']) => {
    switch (color) {
      case 'emerald':
        return {
          bg: 'bg-emerald-50',
          border: 'border-emerald-300',
          text: 'text-emerald-700',
        }
      case 'rose':
        return {
          bg: 'bg-rose-50',
          border: 'border-rose-300',
          text: 'text-rose-700',
        }
      case 'amber':
        return {
          bg: 'bg-amber-50',
          border: 'border-amber-300',
          text: 'text-amber-700',
        }
      case 'purple':
        return {
          bg: 'bg-purple-50',
          border: 'border-purple-300',
          text: 'text-purple-700',
        }
      case 'blue':
      default:
        return {
          bg: 'bg-blue-50',
          border: 'border-blue-300',
          text: 'text-blue-700',
        }
    }
  }

  return (
    <div className="relative pl-6 space-y-4 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200">
      {items.map((item, index) => {
        const theme = getColorClasses(item.color)
        return (
          <div key={index} className="relative group">
            {/* Timeline node bead */}
            <div
              className={`absolute -left-6 top-0.5 w-5 h-5 rounded-full border ${theme.border} ${theme.bg} ${theme.text} flex items-center justify-center shadow-2xs`}
            >
              {item.icon}
            </div>

            {/* Event content */}
            <div className="bg-white border border-slate-200/90 rounded-xl p-3.5 hover:border-slate-300 transition-all shadow-2xs">
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="text-xs font-bold text-slate-900 uppercase tracking-wider">
                  {item.title}
                </span>
                <div className="flex items-center gap-1.5 text-[10px] text-slate-400 font-mono">
                  <Clock className="w-3 h-3" />
                  {formatTime(item.timestamp)}
                </div>
              </div>

              {item.subtitle && (
                <p className="text-xs text-slate-600 mt-1 leading-relaxed font-medium">
                  {item.subtitle}
                </p>
              )}

              {item.status && (
                <div className="mt-2 flex items-center gap-2">
                  <span
                    className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded ${
                      item.status === 'SUCCESS' || item.status === 'APPROVED' || item.status === 'SELECTED'
                        ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        : item.status === 'FAILED' || item.status === 'REJECTED'
                        ? 'bg-rose-50 text-rose-700 border border-rose-200'
                        : 'bg-blue-50 text-blue-700 border border-blue-200'
                    }`}
                  >
                    {item.status}
                  </span>
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
