import { useEffect, useMemo, useState } from 'react'
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import {
  Bell,
  ChevronDown,
  Command,
  LogOut,
  Menu,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Sparkles,
  X,
} from 'lucide-react'
import { cn } from '../lib/format'
import { NAV_GROUPS } from '../lib/nav'
import { useAuth } from '../store/auth'
import { Avatar, Modal } from './ui'

function Brand({ compact = false }) {
  return (
    <Link to="/" className={cn('flex items-center gap-3', compact && 'justify-center')}>
      <span className="relative inline-flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl bg-gold text-[15px] font-extrabold text-forest shadow-[0_6px_18px_-8px_rgba(194,149,63,0.9)]">
        H
        <span className="absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/25" />
      </span>
      {!compact && (
        <span className="min-w-0">
          <span className="display block truncate text-lg font-semibold leading-none text-white">Hertex</span>
          <span className="mt-1 block text-[9px] font-bold uppercase tracking-[0.28em] text-white/40">Enterprise suite</span>
        </span>
      )}
    </Link>
  )
}

function SidebarContent({ collapsed, onNavigate, onCollapse }) {
  const can = useAuth((state) => state.can)
  const [query, setQuery] = useState('')
  const location = useLocation()

  const groups = useMemo(() => {
    const visible = NAV_GROUPS.map((group) => ({
      ...group,
      items: group.items.filter((item) => can(item.permission)),
    })).filter((group) => group.items.length)
    if (!query.trim()) return visible
    const needle = query.toLowerCase()
    return [
      {
        label: 'Matches',
        items: visible.flatMap((group) => group.items).filter((item) => item.label.toLowerCase().includes(needle)),
      },
    ].filter((group) => group.items.length)
  }, [can, query])

  return (
    <div className="flex h-full flex-col">
      <div className={cn('flex h-[74px] items-center border-b border-white/10 px-5', collapsed ? 'justify-center px-2' : 'justify-between')}>
        <Brand compact={collapsed} />
        {!collapsed && (
          <button
            type="button"
            onClick={onCollapse}
            className="hidden rounded-lg p-1.5 text-white/40 transition hover:bg-white/10 hover:text-white lg:inline-flex"
            aria-label="Collapse sidebar"
          >
            <PanelLeftClose size={16} />
          </button>
        )}
      </div>

      {!collapsed && (
        <div className="px-4 pt-4">
          <div className="relative">
            <Search size={14} className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-white/35" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Find a module…"
              className="w-full rounded-xl border border-white/10 bg-white/[0.06] py-2 pl-9 pr-3 text-xs text-white outline-none transition placeholder:text-white/30 focus:border-gold/40 focus:bg-white/[0.09]"
            />
          </div>
        </div>
      )}

      <nav className="flex-1 overflow-y-auto px-3 py-4 [scrollbar-width:thin]">
        {groups.map((group) => (
          <div key={group.label} className="mb-5">
            {!collapsed && <p className="mb-2 px-2.5 text-[9px] font-bold uppercase tracking-[0.22em] text-white/30">{group.label}</p>}
            <div className="space-y-0.5">
              {group.items.map((item) => {
                const Icon = item.icon
                return (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    title={collapsed ? item.label : undefined}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn(
                        'group relative flex items-center gap-3 rounded-xl px-2.5 py-2.5 text-[13px] font-medium transition',
                        collapsed && 'justify-center px-0',
                        isActive
                          ? 'bg-white/[0.11] text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]'
                          : 'text-white/55 hover:bg-white/[0.06] hover:text-white/90',
                      )
                    }
                  >
                    {({ isActive }) => (
                      <>
                        <Icon size={17} strokeWidth={isActive ? 2.2 : 1.8} className={cn('shrink-0', isActive ? 'text-gold' : 'text-white/45 group-hover:text-white/75')} />
                        {!collapsed && <span className="truncate">{item.label}</span>}
                        {!collapsed && isActive && <span className="ml-auto h-1.5 w-1.5 rounded-full bg-gold" />}
                      </>
                    )}
                  </NavLink>
                )
              })}
            </div>
          </div>
        ))}
        {!groups.length && (
          <p className="px-3 text-xs text-white/40">No modules match “{query}”.</p>
        )}
      </nav>

      <div className={cn('border-t border-white/10 p-3', collapsed && 'px-2')}>
        <MiniProfile collapsed={collapsed} />
      </div>
    </div>
  )
}

function MiniProfile({ collapsed }) {
  const { user, roles, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)

  const signOut = async () => {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className={cn(
          'flex w-full items-center gap-2.5 rounded-xl p-1.5 text-left transition hover:bg-white/[0.07]',
          collapsed && 'justify-center',
        )}
      >
        <Avatar name={user?.full_name} size="sm" className="bg-gold/20 text-gold ring-gold/20" />
        {!collapsed && (
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-semibold text-white">{user?.full_name ?? 'Hertex user'}</span>
            <span className="block truncate text-[10px] capitalize text-white/40">{(roles[0] ?? 'member').replaceAll('_', ' ')}</span>
          </span>
        )}
        {!collapsed && <ChevronDown size={14} className="text-white/35" />}
      </button>
      {open && (
        <div className="absolute bottom-full left-0 z-40 mb-2 w-56 overflow-hidden rounded-xl border border-line bg-surface p-1.5 shadow-[var(--shadow-float)]">
          <div className="border-b border-line px-3 py-2">
            <p className="truncate text-xs font-bold text-ink">{user?.email}</p>
            <p className="mt-0.5 text-[10px] text-muted">Signed in to Hertex ERP</p>
          </div>
          <button type="button" className="mt-1 flex w-full items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold text-rose-600 transition hover:bg-rose-50" onClick={signOut}>
            <LogOut size={14} /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}

function CommandPalette({ open, onClose }) {
  const can = useAuth((state) => state.can)
  const navigate = useNavigate()
  const [query, setQuery] = useState('')

  const items = useMemo(() => {
    const all = NAV_GROUPS.flatMap((group) => group.items.filter((item) => can(item.permission)))
    if (!query.trim()) return all.slice(0, 9)
    const needle = query.toLowerCase()
    return all.filter((item) => item.label.toLowerCase().includes(needle)).slice(0, 10)
  }, [can, query])

  useEffect(() => {
    if (open) setQuery('')
  }, [open])

  return (
    <Modal open={open} onClose={onClose} title="Jump to…" description="Search modules and pages. Press Enter to open the first result." size="sm">
      <input
        autoFocus
        value={query}
        onChange={(event) => setQuery(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Enter' && items[0]) {
            navigate(items[0].to)
            onClose()
          }
        }}
        className="input"
        placeholder="Type a module name…"
      />
      <div className="mt-3 space-y-1">
        {items.map((item) => {
          const Icon = item.icon
          return (
            <button
              key={item.to}
              type="button"
              onClick={() => {
                navigate(item.to)
                onClose()
              }}
              className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left text-sm font-medium text-ink-soft transition hover:bg-surface-2 hover:text-ink"
            >
              <Icon size={16} className="text-muted" />
              {item.label}
            </button>
          )
        })}
        {!items.length && <p className="px-3 py-6 text-center text-xs text-muted">No modules found.</p>}
      </div>
    </Modal>
  )
}

export default function AppShell() {
  const [collapsed, setCollapsed] = useState(false)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [paletteOpen, setPaletteOpen] = useState(false)
  const location = useLocation()
  const { user, isSuperuser } = useAuth()

  useEffect(() => {
    setMobileOpen(false)
  }, [location.pathname])

  useEffect(() => {
    const onKey = (event) => {
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setPaletteOpen(true)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    const onLogout = () => window.location.assign('/login')
    window.addEventListener('hertex:logout', onLogout)
    return () => window.removeEventListener('hertex:logout', onLogout)
  }, [])

  return (
    <div className="flex min-h-screen bg-canvas">
      <aside
        className={cn(
          'forest-grid fixed inset-y-0 left-0 z-40 hidden shrink-0 border-r border-white/5 transition-[width] duration-300 lg:block',
          collapsed ? 'w-[76px]' : 'w-[268px]',
        )}
      >
        <SidebarContent collapsed={collapsed} onCollapse={() => setCollapsed(true)} />
        {collapsed && (
          <button
            type="button"
            onClick={() => setCollapsed(false)}
            className="absolute right-2 top-[82px] inline-flex h-7 w-7 items-center justify-center rounded-lg bg-white/10 text-white/60 hover:text-white"
            aria-label="Expand sidebar"
          >
            <PanelLeftOpen size={14} />
          </button>
        )}
      </aside>

      {mobileOpen && (
        <div className="fixed inset-0 z-50 lg:hidden">
          <button type="button" className="absolute inset-0 bg-forest/60 backdrop-blur-sm" onClick={() => setMobileOpen(false)} aria-label="Close menu" />
          <aside className="forest-grid absolute inset-y-0 left-0 w-[280px] border-r border-white/10 shadow-2xl">
            <button
              type="button"
              onClick={() => setMobileOpen(false)}
              className="absolute right-3 top-5 z-10 rounded-lg p-2 text-white/60 hover:bg-white/10 hover:text-white"
              aria-label="Close menu"
            >
              <X size={18} />
            </button>
            <SidebarContent onNavigate={() => setMobileOpen(false)} />
          </aside>
        </div>
      )}

      <div className={cn('flex min-w-0 flex-1 flex-col transition-[padding] duration-300', collapsed ? 'lg:pl-[76px]' : 'lg:pl-[268px]')}>
        <header className="glass sticky top-0 z-30 flex h-[74px] items-center gap-3 border-b border-line/80 px-4 sm:px-6 lg:px-8">
          <button
            type="button"
            className="inline-flex h-10 w-10 items-center justify-center rounded-xl border border-line bg-surface text-ink-soft lg:hidden"
            onClick={() => setMobileOpen(true)}
            aria-label="Open menu"
          >
            <Menu size={18} />
          </button>

          <div className="hidden min-w-0 items-center gap-2 text-xs text-muted sm:flex">
            <span className="font-semibold text-ink-soft">Workspace</span>
            <span className="text-line">/</span>
            <span className="truncate capitalize">{location.pathname.split('/').filter(Boolean).slice(0, 2).join(' / ') || 'Command centre'}</span>
          </div>

          <div className="ml-auto flex items-center gap-2">
            <button
              type="button"
              onClick={() => setPaletteOpen(true)}
              className="hidden w-64 items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2 text-left text-xs text-muted transition hover:border-primary/30 hover:text-ink-soft md:flex"
            >
              <Search size={14} />
              <span className="flex-1">Search modules…</span>
              <span className="inline-flex items-center gap-0.5 rounded border border-line bg-surface-2 px-1.5 py-0.5 text-[9px] font-bold text-muted">
                <Command size={9} /> K
              </span>
            </button>
            <Link to="/assistant" className="btn-secondary h-10 px-3" title="Ask the assistant">
              <Sparkles size={16} className="text-gold" />
              <span className="hidden text-xs sm:inline">Ask AI</span>
            </Link>
            <button type="button" className="relative inline-flex h-10 w-10 items-center justify-center rounded-xl border border-line bg-surface text-ink-soft transition hover:bg-surface-2" aria-label="Notifications">
              <Bell size={16} />
              <span className="absolute right-2.5 top-2.5 h-1.5 w-1.5 rounded-full bg-accent ring-2 ring-surface" />
            </button>
            <div className="hidden items-center gap-2 rounded-xl border border-line bg-surface py-1.5 pl-1.5 pr-3 sm:flex">
              <Avatar name={user?.full_name} size="sm" />
              <div className="leading-tight">
                <p className="max-w-[130px] truncate text-[11px] font-bold text-ink">{user?.full_name}</p>
                <p className="text-[9px] font-semibold uppercase tracking-wider text-muted">{isSuperuser ? 'Super admin' : 'Member'}</p>
              </div>
            </div>
          </div>
        </header>

        <main className="mx-auto w-full max-w-[1500px] flex-1 px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
          <Outlet />
        </main>

        <footer className="mx-auto w-full max-w-[1500px] px-4 pb-6 text-[10px] font-medium text-muted/70 sm:px-6 lg:px-8">
          Hertex ERP · calm operations for modern retail · {new Date().getFullYear()}
        </footer>
      </div>

      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  )
}
