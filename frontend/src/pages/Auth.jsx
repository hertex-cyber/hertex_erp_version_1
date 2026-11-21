import { useEffect, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { ArrowLeft, ArrowRight, CheckCircle2, Eye, EyeOff, KeyRound, Lock, Mail, Sparkles } from 'lucide-react'
import BrandLogo from '../components/BrandLogo'
import { api, apiErrorMessage } from '../lib/api'
import { useAuth } from '../store/auth'
import { toast } from '../store/toast'
import { Spinner } from '../components/ui'

const showDemoLogin = import.meta.env.DEV || import.meta.env.VITE_SHOW_DEMO_LOGIN === 'true'

function AuthArtwork() {
  return (
    <div className="forest-grid relative hidden min-h-screen flex-col justify-between overflow-hidden p-10 lg:flex xl:p-14">
      <div className="absolute -right-24 -top-24 h-80 w-80 rounded-full border border-white/10" />
      <div className="absolute -right-10 top-10 h-56 w-56 rounded-full border border-gold/20" />
      <div className="absolute bottom-[-160px] left-[-80px] h-[420px] w-[420px] rounded-full bg-gold/10 blur-3xl" />

      <Link to="/" className="relative flex items-center gap-3">
        <BrandLogo className="h-12 drop-shadow-[0_8px_24px_rgba(255,105,0,0.35)]" />
        <span>
          <span className="display block text-xl font-semibold leading-none text-white">Hertex</span>
          <span className="mt-1 block text-[9px] font-bold uppercase tracking-[0.3em] text-white/40">Enterprise suite</span>
        </span>
      </Link>

      <div className="relative max-w-lg">
        <p className="mb-5 inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/[0.06] px-3 py-1.5 text-[10px] font-bold uppercase tracking-[0.18em] text-gold">
          <Sparkles size={12} /> One calm operating system
        </p>
        <h1 className="display text-5xl font-medium leading-[1.05] text-white xl:text-6xl">
          Run the whole house
          <span className="block text-gold">from one quiet place.</span>
        </h1>
        <p className="mt-6 max-w-md text-sm leading-relaxed text-white/55">
          Sales, stock, money, people and relationships — woven into a single workspace that keeps the day legible.
        </p>

        <div className="mt-10 grid grid-cols-3 gap-3">
          {[
            ['12', 'Modules'],
            ['54', 'Data models'],
            ['236', 'API routes'],
          ].map(([value, label]) => (
            <div key={label} className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur">
              <p className="display text-2xl font-semibold text-white">{value}</p>
              <p className="mt-1 text-[10px] font-bold uppercase tracking-[0.16em] text-white/35">{label}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="relative flex items-center gap-3 text-[11px] text-white/40">
        <CheckCircle2 size={14} className="text-gold" />
        Role-based access, audit trails and tenant isolation built in.
      </div>
    </div>
  )
}

function AuthLayout({ children, footer }) {
  return (
    <div className="grid min-h-screen bg-canvas lg:grid-cols-[1.05fr_0.95fr]">
      <AuthArtwork />
      <div className="flex min-h-screen flex-col">
        <div className="flex items-center justify-between p-6 lg:justify-end">
          <Link to="/" className="flex items-center gap-2 lg:hidden">
            <BrandLogo compact className="h-9 w-9" />
            <span className="display text-lg font-semibold text-ink">Hertex</span>
          </Link>
          <p className="text-xs text-muted">{footer}</p>
        </div>
        <div className="flex flex-1 items-center justify-center px-6 pb-16 pt-4">
          <div className="w-full max-w-[420px] animate-in">{children}</div>
        </div>
      </div>
    </div>
  )
}

function TextField({ label, icon: Icon, type = 'text', reveal, ...props }) {
  const [visible, setVisible] = useState(false)
  const inputType = type === 'password' && visible ? 'text' : type
  return (
    <div>
      <label className="label">{label}</label>
      <div className="relative">
        {Icon && <Icon size={16} className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted" />}
        <input type={inputType} className={`input py-3 ${Icon ? 'pl-10' : ''} ${reveal ? 'pr-10' : ''}`} {...props} />
        {reveal && (
          <button
            type="button"
            onClick={() => setVisible((value) => !value)}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-muted hover:text-ink"
            aria-label={visible ? 'Hide password' : 'Show password'}
          >
            {visible ? <EyeOff size={16} /> : <Eye size={16} />}
          </button>
        )}
      </div>
    </div>
  )
}

function ErrorBox({ children }) {
  if (!children) return null
  return <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-xs font-semibold text-rose-700">{children}</div>
}

function PasswordHint() {
  return (
    <p className="text-[11px] leading-relaxed text-muted">
      Use 12+ characters with uppercase, lowercase, a number and a symbol. Avoid names and common sequences.
    </p>
  )
}

export function LoginPage() {
  const login = useAuth((state) => state.login)
  const verifyMfa = useAuth((state) => state.verifyMfa)
  const user = useAuth((state) => state.user)
  const navigate = useNavigate()
  const location = useLocation()
  const [stage, setStage] = useState('credentials')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [challengeToken, setChallengeToken] = useState('')
  const [code, setCode] = useState('')
  const [recoveryCode, setRecoveryCode] = useState('')
  const [useRecovery, setUseRecovery] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (user) navigate('/', { replace: true })
  }, [user, navigate])

  const finish = () => navigate(location.state?.from?.pathname ?? '/', { replace: true })

  const submit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      const result = await login(email, password)
      if (result.mfaRequired) {
        setChallengeToken(result.challengeToken)
        setStage('challenge')
        return
      }
      finish()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Sign-in failed. Check your credentials.'))
    } finally {
      setLoading(false)
    }
  }

  const verify = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await verifyMfa(challengeToken, code, useRecovery ? recoveryCode : '')
      finish()
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Verification failed. Try again.'))
    } finally {
      setLoading(false)
    }
  }

  const useDemo = () => {
    setEmail('admin@hertex.dev')
    setPassword('Admin@12345')
  }

  return (
    <AuthLayout footer={<span>New here? <Link className="font-semibold text-primary hover:underline" to="/register">Create a workspace</Link></span>}>
      {stage === 'credentials' ? (
        <>
          <p className="eyebrow mb-3">Welcome back</p>
          <h1 className="display text-4xl font-semibold text-ink">Sign in to Hertex</h1>
          <p className="mt-3 text-sm leading-relaxed text-muted">Use your workspace credentials to pick up where you left off.</p>

          <form onSubmit={submit} className="mt-8 space-y-4">
            <TextField label="Email" icon={Mail} type="email" autoComplete="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" />
            <TextField label="Password" icon={Lock} type="password" reveal autoComplete="current-password" required value={password} onChange={(event) => setPassword(event.target.value)} placeholder="••••••••" />

            <div className="flex justify-end">
              <Link className="text-xs font-semibold text-primary hover:underline" to="/forgot-password">Forgot password?</Link>
            </div>
            <ErrorBox>{error}</ErrorBox>

            <button type="submit" className="btn-primary w-full py-3" disabled={loading}>
              {loading ? <Spinner className="h-4 w-4" /> : null}
              Sign in
              {!loading && <ArrowRight size={16} />}
            </button>
          </form>

          {showDemoLogin && (
            <button type="button" onClick={useDemo} className="mt-4 w-full rounded-xl border border-dashed border-line bg-surface-2 px-4 py-3 text-left transition hover:border-primary/30">
              <span className="block text-[10px] font-bold uppercase tracking-[0.16em] text-muted">Demo workspace</span>
              <span className="mt-1 block text-xs font-semibold text-ink-soft">admin@hertex.dev · Admin@12345</span>
              <span className="mt-0.5 block text-[10px] text-muted">Click to fill the form automatically.</span>
            </button>
          )}
        </>
      ) : (
        <>
          <button type="button" onClick={() => { setStage('credentials'); setError('') }} className="mb-5 inline-flex items-center gap-2 text-xs font-semibold text-muted hover:text-ink">
            <ArrowLeft size={14} /> Back to sign in
          </button>
          <p className="eyebrow mb-3">Two-step verification</p>
          <h1 className="display text-4xl font-semibold text-ink">Confirm it’s you</h1>
          <p className="mt-3 text-sm leading-relaxed text-muted">Enter the 6-digit code from your authenticator app, or use a recovery code.</p>

          <form onSubmit={verify} className="mt-8 space-y-4">
            {useRecovery ? (
              <TextField label="Recovery code" icon={KeyRound} required value={recoveryCode} onChange={(event) => setRecoveryCode(event.target.value)} placeholder="ABC123-DEF456" />
            ) : (
              <TextField label="Verification code" icon={KeyRound} inputMode="numeric" pattern="[0-9]{6}" maxLength={6} required value={code} onChange={(event) => setCode(event.target.value.replace(/\D/g, ''))} placeholder="000000" />
            )}
            <button type="button" onClick={() => { setUseRecovery((value) => !value); setError('') }} className="text-xs font-semibold text-primary hover:underline">
              {useRecovery ? 'Use authenticator code' : 'Use a recovery code'}
            </button>
            <ErrorBox>{error}</ErrorBox>
            <button type="submit" className="btn-primary w-full py-3" disabled={loading}>
              {loading ? <Spinner className="h-4 w-4" /> : null}
              Verify and continue
              {!loading && <ArrowRight size={16} />}
            </button>
          </form>
        </>
      )}
    </AuthLayout>
  )
}

export function RegisterPage() {
  const register = useAuth((state) => state.register)
  const navigate = useNavigate()
  const [form, setForm] = useState({ tenant_name: '', full_name: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const update = (key) => (event) => setForm((current) => ({ ...current, [key]: event.target.value }))

  const submit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    try {
      await register(form)
      navigate('/', { replace: true })
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not create the workspace.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout footer={<span>Already have an account? <Link className="font-semibold text-primary hover:underline" to="/login">Sign in</Link></span>}>
      <p className="eyebrow mb-3">Start fresh</p>
      <h1 className="display text-4xl font-semibold text-ink">Create your workspace</h1>
      <p className="mt-3 text-sm leading-relaxed text-muted">You’ll become the tenant administrator with full access to every module.</p>

      <form onSubmit={submit} className="mt-8 space-y-4">
        <TextField label="Workspace name" required value={form.tenant_name} onChange={update('tenant_name')} placeholder="Hertex Retail" />
        <TextField label="Your name" required value={form.full_name} onChange={update('full_name')} placeholder="Meera Rao" />
        <TextField label="Email" icon={Mail} type="email" required value={form.email} onChange={update('email')} placeholder="you@company.com" />
        <TextField label="Password" icon={Lock} type="password" reveal required minLength={12} value={form.password} onChange={update('password')} placeholder="At least 12 characters" />
        <PasswordHint />
        <ErrorBox>{error}</ErrorBox>

        <button type="submit" className="btn-primary w-full py-3" disabled={loading}>
          {loading ? <Spinner className="h-4 w-4" /> : null}
          Create workspace
          {!loading && <ArrowRight size={16} />}
        </button>
      </form>
    </AuthLayout>
  )
}

export function ForgotPasswordPage() {
  const [email, setEmail] = useState('')
  const [message, setMessage] = useState('')
  const [devToken, setDevToken] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    setLoading(true)
    setError('')
    setMessage('')
    try {
      const { data } = await api.post('/auth/forgot-password', { email })
      setMessage(data.message)
      setDevToken(data.dev_token ?? '')
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not request a reset link.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout footer={<span>Remembered it? <Link className="font-semibold text-primary hover:underline" to="/login">Sign in</Link></span>}>
      <p className="eyebrow mb-3">Account recovery</p>
      <h1 className="display text-4xl font-semibold text-ink">Reset your password</h1>
      <p className="mt-3 text-sm leading-relaxed text-muted">We’ll issue a single-use reset link if an active account matches this email.</p>

      <form onSubmit={submit} className="mt-8 space-y-4">
        <TextField label="Email" icon={Mail} type="email" required value={email} onChange={(event) => setEmail(event.target.value)} placeholder="you@company.com" />
        <ErrorBox>{error}</ErrorBox>
        {message && (
          <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-xs font-semibold text-emerald-700">
            {message}
            {devToken && (
              <Link className="mt-2 block font-bold underline" to={`/reset-password?token=${encodeURIComponent(devToken)}`}>
                Open development reset link
              </Link>
            )}
          </div>
        )}
        <button type="submit" className="btn-primary w-full py-3" disabled={loading}>
          {loading ? <Spinner className="h-4 w-4" /> : null}
          Send reset link
          {!loading && <ArrowRight size={16} />}
        </button>
      </form>
    </AuthLayout>
  )
}

export function ResetPasswordPage() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  const submit = async (event) => {
    event.preventDefault()
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setLoading(true)
    setError('')
    try {
      await api.post('/auth/reset-password', { token: params.get('token'), new_password: password })
      toast.success('Password reset', 'Sign in with your new password.')
      navigate('/login', { replace: true })
    } catch (requestError) {
      setError(apiErrorMessage(requestError, 'Could not reset the password.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <AuthLayout footer={<span>Back to <Link className="font-semibold text-primary hover:underline" to="/login">sign in</Link></span>}>
      <p className="eyebrow mb-3">Choose a new password</p>
      <h1 className="display text-4xl font-semibold text-ink">Secure your account</h1>
      <p className="mt-3 text-sm leading-relaxed text-muted">Reset links are single-use and expire after 30 minutes.</p>

      <form onSubmit={submit} className="mt-8 space-y-4">
        <TextField label="New password" icon={Lock} type="password" reveal required minLength={12} value={password} onChange={(event) => setPassword(event.target.value)} placeholder="At least 12 characters" />
        <TextField label="Confirm password" icon={Lock} type="password" reveal required minLength={12} value={confirm} onChange={(event) => setConfirm(event.target.value)} placeholder="Repeat new password" />
        <PasswordHint />
        <ErrorBox>{error}</ErrorBox>
        <button type="submit" className="btn-primary w-full py-3" disabled={loading}>
          {loading ? <Spinner className="h-4 w-4" /> : null}
          Reset password
          {!loading && <ArrowRight size={16} />}
        </button>
      </form>
    </AuthLayout>
  )
}
