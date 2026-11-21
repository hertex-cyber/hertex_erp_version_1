export const APP_LOGO = '/logo-transparent-bg.png'

export default function BrandLogo({ compact = false, className = '' }) {
  return (
    <img
      src={APP_LOGO}
      alt="Hertex ERP"
      className={compact ? `h-8 w-8 shrink-0 object-contain ${className}` : `h-10 w-auto max-w-[160px] shrink-0 object-contain ${className}`}
    />
  )
}
