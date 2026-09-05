import React, { useState } from 'react'
import { Shield, Menu, X } from 'lucide-react'

export type NavigationTab =
  | 'landing'
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
  { id: 'landing', label: 'Overview' },
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
      <nav className="sticky top-0 z-50 bg-white border-b border-slate-200/80">
        <div className="max-w-screen-2xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex items-center h-16 gap-6 sm:gap-8 justify-between">

            {/* Brand (Req 3: 22-24px, Inter SemiBold/Bold, dark text #0F172A) */}
            <button
              type="button"
              onClick={() => handleNav('dashboard')}
              className="flex items-center gap-3 shrink-0 cursor-pointer group text-left"
            >
              <div
                className="w-8 h-8 rounded-lg flex items-center justify-center shrink-0 shadow-2xs group-hover:opacity-95 transition-opacity"
                style={{ backgroundColor: '#305EFF' }}
              >
                <Shield className="w-4.5 h-4.5 text-white" />
              </div>
              <div className="flex flex-col">
                <span className="font-semibold text-xl sm:text-[22px] tracking-tight text-slate-900 leading-none">
                  AgentPay
                </span>
                <span className="text-[11px] font-normal text-slate-400 leading-tight mt-0.5">
                  AI Payment Infra
                </span>
              </div>
            </button>

            {/* Desktop Nav Links (Req 4: Inter Medium, 14-15px, subtle hover & active) */}
            <div className="hidden xl:flex items-center gap-1 flex-1 justify-center max-w-4xl">
              {NAV_ITEMS.map((item) => {
                const isActive = activeTab === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleNav(item.id)}
                    className={`px-3 py-1.5 text-sm font-medium rounded-md transition-colors cursor-pointer whitespace-nowrap ${
                      isActive
                        ? 'text-[#305EFF] bg-[#EFF4FF] font-semibold'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                    }`}
                  >
                    {item.label}
                  </button>
                )
              })}
            </div>

            {/* Large-Tablet Nav Links (compact list if xl is not met) */}
            <div className="hidden lg:flex xl:hidden items-center gap-1 flex-1 justify-center">
              {NAV_ITEMS.slice(0, 6).map((item) => {
                const isActive = activeTab === item.id
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleNav(item.id)}
                    className={`px-2.5 py-1.5 text-xs font-medium rounded-md transition-colors cursor-pointer whitespace-nowrap ${
                      isActive
                        ? 'text-[#305EFF] bg-[#EFF4FF] font-semibold'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                    }`}
                  >
                    {item.label}
                  </button>
                )
              })}
            </div>

            {/* Right: System Online + Profile */}
            <div className="flex items-center gap-3 shrink-0">
              {/* Subtle System Online pill */}
              <div className="hidden md:flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-emerald-50 border border-emerald-200/80 text-xs font-medium text-emerald-700">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                <span>System Online</span>
              </div>

              {/* Profile button — desktop */}
              <button
                type="button"
                onClick={() => handleNav('profile')}
                className={`hidden sm:flex items-center gap-2 px-2.5 py-1 rounded-lg border transition-colors cursor-pointer ${
                  activeTab === 'profile'
                    ? 'border-[#305EFF] bg-blue-50/60'
                    : 'border-slate-200 hover:border-slate-300 hover:bg-slate-50'
                }`}
              >
                <div
                  className="w-6 h-6 rounded-full flex items-center justify-center text-white font-medium text-xs shrink-0"
                  style={{ backgroundColor: '#305EFF' }}
                >
                  K
                </div>
                <span className="text-xs sm:text-sm font-medium text-slate-800">Krisha</span>
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
                    className={`w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer ${
                      isActive
                        ? 'font-semibold bg-[#EFF4FF] text-[#305EFF]'
                        : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                    }`}
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
                  className={`w-full text-left px-3 py-2 rounded-lg text-sm font-medium transition-colors cursor-pointer flex items-center gap-2.5 ${
                    activeTab === 'profile'
                      ? 'font-semibold bg-[#EFF4FF] text-[#305EFF]'
                      : 'text-slate-600 hover:text-slate-900 hover:bg-slate-50'
                  }`}
                >
                  <div
                    className="w-6 h-6 rounded-full flex items-center justify-center text-white font-medium text-xs shrink-0"
                    style={{ backgroundColor: '#305EFF' }}
                  >
                    K
                  </div>
                  <span>Krisha · Profile</span>
                </button>
              </div>
            </div>
          </div>
        )}
      </nav>
    </>
  )
}
