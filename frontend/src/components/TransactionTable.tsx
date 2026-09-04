import React, { useState } from 'react'
import {
  Search,
  ArrowRight,
  CreditCard,
  QrCode,
  Zap,
  ShoppingBag,
  Tv,
  Music,
  Plane,
} from 'lucide-react'
import { StatusBadge } from './StatusBadge'
import type { Transaction } from '../types'

interface TransactionTableProps {
  transactions: Transaction[]
  loading?: boolean
  onSelectTransaction: (tx: Transaction) => void
}

export const TransactionTable: React.FC<TransactionTableProps> = ({
  transactions,
  loading,
  onSelectTransaction,
}) => {
  const [searchTerm, setSearchTerm] = useState('')
  const [statusFilter, setStatusFilter] = useState('ALL')

  const getMerchantIcon = (name: string, category: string) => {
    const n = name.toLowerCase()
    const c = category.toLowerCase()
    if (n.includes('torrent') || c.includes('util')) {
      return (
        <div className="w-8 h-8 rounded-lg bg-amber-50 text-amber-600 border border-amber-200 flex items-center justify-center shrink-0">
          <Zap className="w-4 h-4" />
        </div>
      )
    }
    if (n.includes('netflix') || c.includes('sub')) {
      return (
        <div className="w-8 h-8 rounded-lg bg-rose-50 text-rose-600 border border-rose-200 flex items-center justify-center shrink-0">
          <Tv className="w-4 h-4" />
        </div>
      )
    }
    if (n.includes('spotify') || c.includes('music')) {
      return (
        <div className="w-8 h-8 rounded-lg bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center justify-center shrink-0">
          <Music className="w-4 h-4" />
        </div>
      )
    }
    if (n.includes('makemytrip') || c.includes('travel') || n.includes('airdemo')) {
      return (
        <div className="w-8 h-8 rounded-lg bg-blue-50 text-blue-600 border border-blue-200 flex items-center justify-center shrink-0">
          <Plane className="w-4 h-4" />
        </div>
      )
    }
    if (n.includes('amazon') || c.includes('shop')) {
      return (
        <div className="w-8 h-8 rounded-lg bg-orange-50 text-orange-600 border border-orange-200 flex items-center justify-center shrink-0">
          <ShoppingBag className="w-4 h-4" />
        </div>
      )
    }
    return (
      <div className="w-8 h-8 rounded-lg bg-slate-50 text-slate-600 border border-slate-200 flex items-center justify-center shrink-0">
        <CreditCard className="w-4 h-4" />
      </div>
    )
  }

  const getMethodBadge = (tx: Transaction) => {
    if (tx.payment_method_type === 'CARD_TOKEN' || tx.payment_method_alias?.includes('corp')) {
      return (
        <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700">
          <CreditCard className="w-3.5 h-3.5 text-blue-600" />
          <span>Corporate Card</span>
        </span>
      )
    }
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-700">
        <QrCode className="w-3.5 h-3.5 text-emerald-600" />
        <span>UPI Rail</span>
      </span>
    )
  }

  const filtered = transactions.filter((tx) => {
    const matchesSearch =
      tx.merchant_name.toLowerCase().includes(searchTerm.toLowerCase()) ||
      tx.category.toLowerCase().includes(searchTerm.toLowerCase()) ||
      tx.id.toLowerCase().includes(searchTerm.toLowerCase())

    const matchesStatus =
      statusFilter === 'ALL' || tx.status.toUpperCase() === statusFilter.toUpperCase()

    return matchesSearch && matchesStatus
  })

  return (
    <div className="bg-white border border-slate-200/90 rounded-2xl shadow-xs overflow-hidden">
      {/* Table Header & Controls */}
      <div className="p-5 border-b border-slate-100 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h3 className="text-base font-bold text-[#0d1b3e] tracking-tight">Recent Activity & Transactions</h3>
          <p className="text-xs text-slate-500 font-medium mt-0.5">
            Immutable database records evaluated against deterministic financial policies
          </p>
        </div>

        {/* Filter controls */}
        <div className="flex items-center gap-2.5">
          {/* Search */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search merchant or category..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="pl-8 pr-3 py-1.5 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-900 placeholder-slate-400 focus:outline-hidden focus:bg-white focus:border-[#305EFF] transition-all w-48 sm:w-56"
            />
          </div>

          {/* Status Dropdown */}
          <div className="relative">
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-slate-50 border border-slate-200 rounded-xl px-3 py-1.5 text-xs text-slate-700 focus:outline-hidden focus:bg-white focus:border-[#305EFF] transition-all cursor-pointer font-medium"
            >
              <option value="ALL">All Statuses</option>
              <option value="SUCCESS">Success</option>
              <option value="REJECTED">Rejected</option>
              <option value="FAILED">Failed</option>
              <option value="PAYMENT_PENDING">Pending</option>
            </select>
          </div>
        </div>
      </div>

      {/* Table Element */}
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-slate-100 bg-slate-50/60 text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
              <th className="py-3 px-5">Merchant / Category</th>
              <th className="py-3 px-5">Amount (INR)</th>
              <th className="py-3 px-5">Payment Method</th>
              <th className="py-3 px-5">Status</th>
              <th className="py-3 px-5">Timestamp</th>
              <th className="py-3 px-5 text-right">Explainability</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 text-xs">
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="py-12 text-center text-slate-400 font-medium">
                  {loading ? 'Fetching transactions from backend...' : 'No transactions matching your criteria.'}
                </td>
              </tr>
            ) : (
              filtered.map((tx) => (
                <tr
                  key={tx.id}
                  onClick={() => onSelectTransaction(tx)}
                  className="hover:bg-slate-50/80 transition-colors cursor-pointer group"
                >
                  {/* Merchant / Category */}
                  <td className="py-3.5 px-5">
                    <div className="flex items-center gap-3">
                      {getMerchantIcon(tx.merchant_name, tx.category)}
                      <div>
                        <span className="font-semibold text-[#0d1b3e] block group-hover:text-[#305EFF] transition-colors">
                          {tx.merchant_name}
                        </span>
                        <span className="text-[11px] text-slate-500 capitalize font-medium">
                          {tx.category}
                        </span>
                      </div>
                    </div>
                  </td>

                  {/* Amount */}
                  <td className="py-3.5 px-5">
                    <span className="font-bold font-mono text-sm text-[#0d1b3e]">
                      ₹{tx.amount.toLocaleString('en-IN', { minimumFractionDigits: 2 })}
                    </span>
                  </td>

                  {/* Method */}
                  <td className="py-3.5 px-5">
                    {getMethodBadge(tx)}
                  </td>

                  {/* Status */}
                  <td className="py-3.5 px-5">
                    <StatusBadge status={tx.status} />
                  </td>

                  {/* Timestamp */}
                  <td className="py-3.5 px-5 text-slate-500 font-mono text-[11px]">
                    {new Date(tx.created_at).toLocaleTimeString([], {
                      hour: '2-digit',
                      minute: '2-digit',
                      second: '2-digit',
                    })}
                  </td>

                  {/* Explainability Action */}
                  <td className="py-3.5 px-5 text-right">
                    <span className="inline-flex items-center gap-1 text-[11px] font-semibold text-[#305EFF] group-hover:text-blue-700">
                      <span>Inspect Audit</span>
                      <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-0.5 transition-transform" />
                    </span>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}
