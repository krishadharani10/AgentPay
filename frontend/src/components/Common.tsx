import React from 'react'
import { Loader2, AlertCircle, Inbox } from 'lucide-react'

interface MetricCardProps {
  label: string
  value: string
  subvalue?: string
  icon?: React.ReactNode
  badge?: React.ReactNode
}

export const MetricCard: React.FC<MetricCardProps> = ({
  label,
  value,
  subvalue,
  icon,
  badge,
}) => {
  return (
    <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-[0_1px_3px_rgba(15,23,42,0.04)] flex flex-col justify-between hover:border-slate-300 transition-colors">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-500 tracking-normal">
          {label}
        </span>
        {icon && (
          <div className="w-8 h-8 rounded-lg bg-blue-50/80 border border-blue-100 flex items-center justify-center text-[#305EFF]">
            {icon}
          </div>
        )}
      </div>
      <div className="mt-3">
        <div className="flex items-baseline justify-between gap-2">
          <span className="text-2xl font-semibold tracking-tight text-slate-900">
            {value}
          </span>
          {badge}
        </div>
        {subvalue && (
          <p className="text-xs text-slate-500 mt-1 font-normal">{subvalue}</p>
        )}
      </div>
    </div>
  )
}

export const LoadingSpinner: React.FC<{ message?: string }> = ({ message = 'Loading...' }) => {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
      <Loader2 className="w-6 h-6 text-[#305EFF] animate-spin mb-2.5" />
      <p className="text-xs font-medium text-slate-500">{message}</p>
    </div>
  )
}

export const EmptyState: React.FC<{
  title: string
  description?: string
  action?: React.ReactNode
}> = ({ title, description, action }) => {
  return (
    <div className="flex flex-col items-center justify-center py-12 px-6 text-center border border-dashed border-slate-200 rounded-xl bg-white">
      <div className="w-10 h-10 rounded-lg bg-slate-50 border border-slate-200 flex items-center justify-center text-slate-400 mb-3">
        <Inbox className="w-5 h-5" />
      </div>
      <h4 className="text-sm font-semibold text-slate-900">{title}</h4>
      {description && <p className="text-xs text-slate-500 mt-1 max-w-sm">{description}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}

export const ErrorAlert: React.FC<{
  title?: string
  message: string
  onRetry?: () => void
}> = ({ title = 'Error', message, onRetry }) => {
  return (
    <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 flex items-start gap-3">
      <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
      <div className="flex-1 text-xs">
        <span className="font-semibold block text-rose-900">{title}</span>
        <span className="mt-0.5 block text-rose-700 font-normal leading-relaxed">{message}</span>
      </div>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="text-xs font-medium px-2.5 py-1 bg-white hover:bg-rose-100 text-rose-700 border border-rose-300 rounded-lg transition-colors cursor-pointer"
        >
          Retry
        </button>
      )}
    </div>
  )
}
