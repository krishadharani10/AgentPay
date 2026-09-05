import React from 'react'
import {
  CheckCircle2,
  XCircle,
  AlertCircle,
  Clock,
  ShieldCheck,
  RotateCcw,
} from 'lucide-react'

interface StatusBadgeProps {
  status: string
  size?: 'sm' | 'md' | 'lg'
}

export const StatusBadge: React.FC<StatusBadgeProps> = ({ status, size = 'md' }) => {
  const normalized = (status || '').toUpperCase()

  const sizeClasses = {
    sm: 'text-[11px] px-2 py-0.5 gap-1 font-medium',
    md: 'text-xs px-2.5 py-1 gap-1.5 font-medium',
    lg: 'text-sm px-3 py-1.5 gap-2 font-medium',
  }[size]

  switch (normalized) {
    case 'SUCCESS':
    case 'APPROVED':
    case 'ALLOWED':
      return (
        <span
          className={`inline-flex items-center rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200/80 ${sizeClasses}`}
        >
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-600" />
          {normalized === 'ALLOWED' ? 'APPROVED' : normalized}
        </span>
      )

    case 'REJECTED':
    case 'DENIED':
      return (
        <span
          className={`inline-flex items-center rounded-md bg-rose-50 text-rose-700 border border-rose-200/80 ${sizeClasses}`}
        >
          <XCircle className="w-3.5 h-3.5 shrink-0 text-rose-600" />
          REJECTED
        </span>
      )

    case 'FAILED':
      return (
        <span
          className={`inline-flex items-center rounded-md bg-rose-50 text-rose-700 border border-rose-200/80 ${sizeClasses}`}
        >
          <AlertCircle className="w-3.5 h-3.5 shrink-0 text-rose-600" />
          FAILED
        </span>
      )

    case 'PAYMENT_PENDING':
    case 'PENDING':
    case 'PROCESSING':
      return (
        <span
          className={`inline-flex items-center rounded-md bg-amber-50 text-amber-700 border border-amber-200/80 ${sizeClasses}`}
        >
          <Clock className="w-3.5 h-3.5 shrink-0 animate-pulse text-amber-600" />
          PENDING
        </span>
      )

    case 'POLICY_CHECK':
      return (
        <span
          className={`inline-flex items-center rounded-md bg-blue-50 text-blue-700 border border-blue-200/80 ${sizeClasses}`}
        >
          <ShieldCheck className="w-3.5 h-3.5 shrink-0 text-[#305EFF]" />
          POLICY_CHECK
        </span>
      )

    case 'REQUESTED':
      return (
        <span
          className={`inline-flex items-center rounded-md bg-slate-50 text-slate-700 border border-slate-200 ${sizeClasses}`}
        >
          <Clock className="w-3.5 h-3.5 shrink-0 text-slate-500" />
          REQUESTED
        </span>
      )

    case 'FALLBACK':
    case 'FALLBACK_TRIGGERED':
      return (
        <span
          className={`inline-flex items-center rounded-md bg-blue-50 text-blue-700 border border-blue-200/80 ${sizeClasses}`}
        >
          <RotateCcw className="w-3.5 h-3.5 shrink-0 text-[#305EFF]" />
          FALLBACK
        </span>
      )

    default:
      return (
        <span
          className={`inline-flex items-center rounded-md bg-slate-50 text-slate-700 border border-slate-200 ${sizeClasses}`}
        >
          {normalized}
        </span>
      )
  }
}
