const CSRF_KEY = 'hertex_csrf'

let accessToken = null

export const getAccessToken = () => accessToken

export function setAccessToken(token) {
  accessToken = token || null
  return accessToken
}

export function getCsrfToken() {
  if (typeof document === 'undefined') return null
  const prefix = `${CSRF_KEY}=`
  const cookie = document.cookie.split('; ').find((item) => item.startsWith(prefix))
  return cookie ? decodeURIComponent(cookie.slice(prefix.length)) : null
}

export function hasSessionCookie() {
  return Boolean(getCsrfToken())
}

export function clearTokens() {
  accessToken = null
  localStorage.removeItem('hertex.auth')
  localStorage.removeItem('hertex.access')
  localStorage.removeItem('hertex.refresh')
}
