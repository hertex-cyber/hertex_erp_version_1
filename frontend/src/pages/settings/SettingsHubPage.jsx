import { Link } from 'react-router-dom'
import { ArrowUpRight, BadgeIndianRupee, Building2, Clock3, Globe2, KeyRound, Layers3, ShieldCheck, SlidersHorizontal, Users } from 'lucide-react'
import { PageHeader } from '../../components/ui'
import SettingsSubnav from '../../components/settings/SettingsSubnav'
import { describePath } from '../../lib/nav'
import { useAuth } from '../../store/auth'

const CARDS = [
  { to: '/settings/organisation', icon: Building2, title: 'Organisation', description: 'Company profile, GSTIN and statutory particulars used on every invoice.' },
  { to: '/settings/localisation', icon: Globe2, title: 'Localisation', description: 'Currency, timezone, formats and financial-year start with a live sample.' },
  { to: '/settings/modules', icon: Layers3, title: 'Modules & features', description: 'Feature toggles and module preferences. APIs stay live when a module is disabled.' },
  { to: '/settings/values', icon: SlidersHorizontal, title: 'All settings', description: 'Every governed key with typed editors, provenance and change reasons.' },
  { to: '/settings/numbering', icon: BadgeIndianRupee, title: 'Numbering console', description: 'Series, live previews, locked states, gaps and offline device blocks.' },
  { to: '/settings/secrets', icon: KeyRound, title: 'Secrets vault', description: 'Masked credentials with write-only updates and timed rotation windows.' },
  { to: '/settings/history', icon: Clock3, title: 'Change history', description: 'Setting changes and secret-rotation audit events in one timeline.' },
  { to: '/settings/users', icon: Users, title: 'Team & access', description: 'Users, roles and the permissions that gate every settings surface.' },
  { to: '/settings/security', icon: ShieldCheck, title: 'Security', description: 'MFA and account security for administrators.' },
]

export default function SettingsHubPage() {
  const canView = useAuth().canView

  return (
    <div data-testid="settings-hub">
      <SettingsSubnav />
      <PageHeader eyebrow="Workspace" title="Settings hub" description="One governed place for organisation policy, feature flags, numbering and secrets." />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {CARDS.filter((card) => canView(describePath(card.to))).map(({ to, icon: Icon, title, description }) => (
          <Link key={to} to={to} className="card group flex flex-col gap-2 p-5 transition hover:border-primary/40 hover:shadow-[var(--shadow-float)]" data-testid={`hub-card-${title.toLowerCase().replace(/[^a-z]+/g, '-')}`}>
            <div className="flex items-start justify-between gap-2">
              <span className="inline-flex h-10 w-10 items-center justify-center rounded-xl bg-primary-soft text-primary"><Icon size={18} /></span>
              <ArrowUpRight size={16} className="text-muted transition group-hover:text-primary" />
            </div>
            <h2 className="text-sm font-bold text-ink">{title}</h2>
            <p className="text-xs leading-relaxed text-muted">{description}</p>
          </Link>
        ))}
      </div>
    </div>
  )
}
