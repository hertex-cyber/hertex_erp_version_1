import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, Compass, Sparkles } from 'lucide-react'

export default function NotFound() {
  const navigate = useNavigate()
  return (
    <div className="flex min-h-[70vh] items-center justify-center">
      <div className="card relative w-full max-w-xl overflow-hidden">
        <div className="forest-grid px-8 py-12 text-center">
          <span className="inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-gold text-forest">
            <Compass size={26} />
          </span>
          <p className="mt-5 text-[10px] font-bold uppercase tracking-[0.28em] text-gold">Off the map</p>
          <h1 className="display mt-2 text-5xl font-semibold text-white">404</h1>
          <p className="mx-auto mt-3 max-w-sm text-sm leading-relaxed text-white/55">
            This page is not part of the workspace. It may have moved, or the link is out of date.
          </p>
        </div>
        <div className="flex flex-col items-center gap-3 px-8 py-7 sm:flex-row sm:justify-center">
          <button type="button" className="btn-secondary w-full sm:w-auto" onClick={() => navigate(-1)}>
            <ArrowLeft size={15} /> Go back
          </button>
          <Link to="/" className="btn-primary w-full sm:w-auto">
            <Sparkles size={15} /> Command centre
          </Link>
        </div>
      </div>
    </div>
  )
}
