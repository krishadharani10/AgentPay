import React, { useState } from 'react'
import { Shield, Menu, X } from 'lucide-react'

export type NavigationTab =
  | 'dashboard'
  | 'tasks'
  | 'payments'
  | 'wallet'
  | 'policies'
  | 'transactions'
  | 'audit'
  | 'profile'
  | 'settings'

export type NavTab = NavigationTab

interface NavbarProps {
  activeTab: NavTab
  onSelectTab: (tab: NavTab) => void
}

const NAV_ITEMS: { id: NavTab; label: string }[] = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'tasks', label: 'Autonomous Tasks' },
  { id: 'payments', label: 'Payments' },
  { id: 'wallet', label: 'Wallet' },
  { id: 'policies', label: 'Policies' },
  { id: 'transactions', label: 'Transactions' },
  { id: 'audit', label: 'Audit & Trust' },
]

export const Navbar: React.FC<NavbarProps> = ({ activeTab, onSelectTab }) => {
  const [mobileOpen, setMobileOpen] = useState(false)

  const handleNav = (tab: NavTab) => {
    onSelectTab(tab)
    setMobileOpen(false)
  }

  return (
    <>
      {/* ── Main Navbar ─────────────────────────────────────────────────────── */}
      <nav className="sticky top-0 z-50 bg-white border-b border-slate-200">
        <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center h-14 gap-8">

            {/* Brand */}
            <button
              type="button"
              onClick={() => handleNav('dashboard')}
              className="flex items-center gap-2.5 shrink-0 cursor-pointer group"
            >
              <div
                className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
                style={{ backgroundColor: '#305EFF' }}
              >
                <Shield className="w-4 h-4 text-white" />
              </div>
              <span
                className="font-extrabold text-sm tracking-tight"
                style={{ color: '#0d1b3e', letterSpacing: '-0.02em' }}
              >
                AgentPay
              </span>
            </button>

            {/* Desktop Nav Links */}
            <div className="hidden lg:flex items-center gap-0.5 flex-1">
              {NAV_ITEMS.map((item) => {
                const isActive = activeTab === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleNav(item.id)}
                    className={`relative px-3.5 py-1.5 text-sm font-medium rounded-md transition-colors cursor-pointer whitespace-nowrap ${
                      isActive
                        ? 'bg-[#EFF4FF]'
                        : 'text-slate-500 hover:text-slate-900 hover:bg-slate-50'
                    }`}
                    style={isActive ? { color: '#305EFF' } : {}}
                  >
                    {item.label}
                    {isActive && (
                      <span
                        className="absolute inset-x-0 bottom-0 h-0.5 rounded-t-full"
                        style={{ backgroundColor: '#305EFF' }}
                      />
                    )}
                  </button>
                )
              })}
            </div>

            {/* Spacer on mobile */}
            <div className="flex-1 lg:hidden" />

            {/* Right: User + Profile */}
            <div className="flex items-center gap-3">
              {/* Profile button — desktop */}
              <button
                type="button"
                onClick={() => handleNav('profile')}
                className={`hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg border transition-colors cursor-pointer ${
                  activeTab === 'profile'
                    ? 'border-[#305EFF] bg-[#EFF4FF]'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <div
                  className="w-6 h-6 rounded-full flex items-center justify-center text-white font-bold text-xs shrink-0"
                  style={{ backgroundColor: '#305EFF' }}
                >
                  K
                </div>
                <span className="text-sm font-semibold text-slate-700">Krisha</span>
                <span className="text-xs text-slate-400 hidden md:inline">· Profile</span>
              </button>

              {/* Mobile hamburger */}
              <button
                type="button"
                onClick={() => setMobileOpen(!mobileOpen)}
                className="lg:hidden p-2 rounded-lg text-slate-500 hover:text-slate-900 hover:bg-slate-100 transition-colors cursor-pointer"
                aria-label="Toggle navigation"
              >
                {mobileOpen ? <X className="w-5 h-5" /> : <Menu className="w-5 h-5" />}
              </button>
            </div>
          </div>
        </div>

        {/* ── Mobile Dropdown ─────────────────────────────────────────────── */}
        {mobileOpen && (
          <div className="lg:hidden border-t border-slate-200 bg-white">
            <div className="max-w-screen-2xl mx-auto px-4 py-3 space-y-0.5">
              {NAV_ITEMS.map((item) => {
                const isActive = activeTab === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleNav(item.id)}
                    className={`w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                      isActive
                        ? 'font-semibold bg-[#EFF4FF]'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                    }`}
                    style={isActive ? { color: '#305EFF' } : {}}
                  >
                    {item.label}
                  </button>
                )
              })}

              {/* Mobile profile link */}
              <div className="pt-2 border-t border-slate-100 mt-2">
                <button
                  type="button"
                  onClick={() => handleNav('profile')}
                  className={`w-full text-left px-3 py-2.5 rounded-lg text-sm font-medium transition-colors cursor-pointer flex items-center gap-2.5 ${
                    activeTab === 'profile'
                      ? 'font-semibold bg-[#EFF4FF]'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                  style={activeTab === 'profile' ? { color: '#305EFF' } : {}}
                >
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-white font-bold text-xs shrink-0"
                    style={{ backgroundColor: '#305EFF' }}
                  >
                    K
                  </div>
                  <span>Krisha — Profile</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </nav>
    </>
  )
}
