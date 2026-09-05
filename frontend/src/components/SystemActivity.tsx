import React from 'react'
import { Activity, ShieldCheck, CreditCard, Bot, RotateCcw, Clock } from 'lucide-react'
import type { AuditLog } from '../types'

interface SystemActivityProps {
  logs: AuditLog[]
  loading?: boolean
}

export const SystemActivity: React.FC<SystemActivityProps> = ({ logs, loading }) => {
  const getIcon = (eventType: string) => {
    const e = eventType.toUpperCase()
    if (e.includes('AGENT')) {
      return (
        <div className="w-6 h-6 rounded-md bg-blue-50 text-[#305EFF] border border-blue-100 flex items-center justify-center shrink-0">
          <Bot className="w-3.5 h-3.5" />
        </div>
      )
    }
    if (e.includes('POLICY')) {
      return (
        <div className="w-6 h-6 rounded-md bg-emerald-50 text-emerald-600 border border-emerald-100 flex items-center justify-center shrink-0">
          <ShieldCheck className="w-3.5 h-3.5" />
        </div>
      )
    }
    if (e.includes('FALLBACK') || e.includes('RESET')) {
      return (
        <div className="w-6 h-6 rounded-md bg-blue-50 text-[#305EFF] border border-blue-100 flex items-center justify-center shrink-0">
          <RotateCcw className="w-3.5 h-3.5" />
        </div>
      )
    }
    return (
      <div className="w-6 h-6 rounded-md bg-slate-50 text-slate-600 border border-slate-200 flex items-center justify-center shrink-0">
        <CreditCard className="w-3.5 h-3.5" />
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

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-[0_1px_3px_rgba(15,23,42,0.04)]">
      <div className="flex items-center justify-between mb-4 pb-3 border-b border-slate-100">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-blue-50 border border-blue-100 rounded-lg text-[#305EFF] flex items-center justify-center">
            <Activity className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-900 tracking-tight">Audit & Trust Activity Stream</h3>
            <p className="text-xs text-slate-500 font-normal">
              Immutable Policy & Transaction Audit Trail
            </p>
          </div>
        </div>

        <div className="flex items-center gap-1.5 text-xs text-slate-500 font-medium">
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
          <span>Live Stream</span>
        </div>
      </div>

      <div className="space-y-2.5 max-h-[380px] overflow-y-auto pr-1">
        {logs.length === 0 ? (
          <div className="text-center py-8 text-xs text-slate-400 font-normal">
            {loading ? 'Streaming audit logs...' : 'No recent system activity.'}
          </div>
        ) : (
          logs.slice(0, 10).map((log) => (
            <div
              key={log.id}
              className="p-3 rounded-lg bg-slate-50 border border-slate-200 flex items-start gap-3 hover:bg-slate-100/60 transition-colors text-xs"
            >
              <div className="mt-0.5 shrink-0">{getIcon(log.event_type)}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-900 truncate text-[11px]">
                    {log.event_type.replace(/_/g, ' ')}
                  </span>
                  <span className="text-[11px] text-slate-400 shrink-0 flex items-center gap-1">
                    <Clock className="w-3 h-3" />
                    {formatTime(log.created_at)}
                  </span>
                </div>
                <p className="text-slate-600 text-xs mt-0.5 line-clamp-2 leading-relaxed font-normal">
                  {log.reason}
                </p>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  )
}
