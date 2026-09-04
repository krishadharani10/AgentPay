import React from 'react'
import {
  CheckCircle2,
  XCircle,
  AlertTriangle,
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
    sm: 'text-[10px] px-2 py-0.5 gap-1 font-bold',
    md: 'text-xs px-2.5 py-1 gap-1.5 font-bold',
    lg: 'text-sm px-3 py-1.5 gap-2 font-bold',
  }[size]

  switch (normalized) {
    case 'SUCCESS':
    case 'APPROVED':
    case 'ALLOWED':
      return (
        <span
          className={`inline-flex items-center rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200 shadow-2xs ${sizeClasses}`}
        >
          <CheckCircle2 className="w-3.5 h-3.5 shrink-0 text-emerald-600" />
          {normalized === 'ALLOWED' ? 'APPROVED' : normalized}
        </span>
      )

    case 'REJECTED':
    case 'DENIED':
      return (
        <span
          className={`inline-flex items-center rounded-full bg-rose-50 text-rose-700 border border-rose-200 shadow-2xs ${sizeClasses}`}
        >
          <XCircle className="w-3.5 h-3.5 shrink-0 text-rose-600" />
          REJECTED
        </span>
      )

    case 'FAILED':
      return (
        <span
          className={`inline-flex items-center rounded-full bg-red-50 text-red-700 border border-red-200 shadow-2xs ${sizeClasses}`}
        >
          <AlertTriangle className="w-3.5 h-3.5 shrink-0 text-red-600" />
          FAILED
        </span>
      )

    case 'PAYMENT_PENDING':
    case 'PENDING':
    case 'PROCESSING':
      return (
        <span
          className={`inline-flex items-center rounded-full bg-amber-50 text-amber-700 border border-amber-200 shadow-2xs ${sizeClasses}`}
        >
          <Clock className="w-3.5 h-3.5 shrink-0 animate-pulse text-amber-600" />
          PENDING
        </span>
      )

    case 'POLICY_CHECK':
      return (
        <span
          className={`inline-flex items-center rounded-full bg-blue-50 text-blue-700 border border-blue-200 shadow-2xs ${sizeClasses}`}
        >
          <ShieldCheck className="w-3.5 h-3.5 shrink-0 text-blue-600" />
          POLICY_CHECK
        </span>
      )

    case 'REQUESTED':
      return (
        <span
          className={`inline-flex items-center rounded-full bg-slate-100 text-slate-700 border border-slate-200 shadow-2xs ${sizeClasses}`}
        >
          <Clock className="w-3.5 h-3.5 shrink-0 text-slate-500" />
          REQUESTED
        </span>
      )

    case 'FALLBACK':
    case 'FALLBACK_TRIGGERED':
      return (
        <span
          className={`inline-flex items-center rounded-full bg-blue-50 text-blue-800 border border-blue-200 shadow-2xs ${sizeClasses}`}
        >
          <RotateCcw className="w-3.5 h-3.5 shrink-0 text-blue-600" />
          FALLBACK
        </span>
      )

    default:
      return (
        <span
          className={`inline-flex items-center rounded-full bg-slate-100 text-slate-700 border border-slate-200 shadow-2xs ${sizeClasses}`}
        >
          {normalized}
        </span>
      )
  }
}
