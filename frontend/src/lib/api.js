import axios from 'axios'
import { clearTokens, getAccessToken, getCsrfToken, setAccessToken } from './tokens.js'

const runtimeEnv = import.meta.env ?? {}
const baseURL = runtimeEnv.VITE_API_URL || '/api/v1'
const VOLATILE_KEY_FIELDS = new Set(['idempotency_key', 'reversal_reference', 'csrf_token'])
const sessionSalt = globalThis.crypto?.randomUUID?.() ?? `session-${Date.now()}`
const idempotencyCache = new Map()

export function normalizeIdempotencyPayload(value) {
  if (value === null || value === undefined) return null
  if (typeof value === 'string') {
    try {
      return normalizeIdempotencyPayload(JSON.parse(value))
    } catch {
      return value
    }
  }
  if (Array.isArray(value)) return value.map(normalizeIdempotencyPayload)
  if (typeof value === 'object') {
    if (typeof value.get === 'function' && typeof value.entries === 'function') {
      return normalizeIdempotencyPayload(Object.fromEntries(value.entries()))
    }
    if (typeof FormData !== 'undefined' && value instanceof FormData) {
      return normalizeIdempotencyPayload(Object.fromEntries(value.entries()))
    }
    return Object.fromEntries(
      Object.keys(value)
        .filter((key) => !VOLATILE_KEY_FIELDS.has(key))
        .sort()
        .map((key) => [key, normalizeIdempotencyPayload(value[key])]),
    )
  }
  if (typeof value === 'number' && !Number.isFinite(value)) return null
  return value
}

function hashKey(value) {
  let hash = 0x811c9dc5
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193) >>> 0
  }
  return hash.toString(16).padStart(8, '0')
}

export function idempotencyKeyFor({ method = 'get', url = '', params, data }, salt = sessionSalt) {
  const normalized = {
    method: String(method).toUpperCase(),
    url: String(url).split('?')[0],
    params: normalizeIdempotencyPayload(params),
    data: normalizeIdempotencyPayload(data),
  }
  const fingerprint = JSON.stringify(normalized)
  const cacheKey = `${normalized.method}|${fingerprint}`
  if (!idempotencyCache.has(cacheKey)) {
    idempotencyCache.set(cacheKey, `pm-${hashKey(fingerprint)}-${hashKey(`${salt}:${cacheKey}`)}`)
  }
  return idempotencyCache.get(cacheKey)
}

function hasIdempotencyHeader(headers) {
  if (!headers) return false
  if (typeof headers.has === 'function' && headers.has('Idempotency-Key')) return true
  return Object.keys(headers).some((key) => key.toLowerCase() === 'idempotency-key')
}

function setIdempotencyHeader(headers, key) {
  if (typeof headers.set === 'function') {
    headers.set('Idempotency-Key', key)
    return
  }
  headers['Idempotency-Key'] = key
}

export const api = axios.create({ baseURL, timeout: 30000, withCredentials: true })

let refreshing = null

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  const method = String(config.method ?? 'get').toUpperCase()
  const isMutation = ['POST', 'PATCH', 'PUT', 'DELETE'].includes(method)
  const isAuthCall = String(config.url ?? '').includes('/auth/')
  if (isMutation && !isAuthCall) {
    config.headers = config.headers ?? {}
    if (!hasIdempotencyHeader(config.headers)) {
      setIdempotencyHeader(
        config.headers,
        idempotencyKeyFor({
          method,
          url: config.url,
          params: config.params,
          data: config.data,
        }),
      )
    }
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const status = error.response?.status
    const isAuthCall = original?.url?.includes('/auth/')

    if (status === 401 && original && !original._retried && !isAuthCall) {
      const csrf = getCsrfToken()
      if (!csrf) {
        clearTokens()
        window.dispatchEvent(new Event('hertex:logout'))
        return Promise.reject(error)
      }

      original._retried = true
      try {
        refreshing =
          refreshing ||
          api
            .post('/auth/refresh', {}, { headers: { 'X-CSRF-Token': csrf } })
            .then((response) => {
              setAccessToken(response.data.access_token)
              return response.data.access_token
            })
            .finally(() => {
              refreshing = null
            })

        const token = await refreshing
        original.headers.Authorization = `Bearer ${token}`
        return api(original)
      } catch (refreshError) {
        clearTokens()
        window.dispatchEvent(new Event('hertex:logout'))
        return Promise.reject(refreshError)
      }
    }
    return Promise.reject(error)
  },
)

export function apiErrorMessage(error, fallback = 'Something went wrong. Please try again.') {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        const field = Array.isArray(item.loc) ? item.loc.slice(1).join('.') : ''
        return field ? `${field}: ${item.msg}` : item.msg
      })
      .join(', ')
  }
  if (error?.code === 'ECONNABORTED') return 'The request timed out. Please try again.'
  if (!error?.response) return 'Cannot reach the API. Is the backend running?'
  return fallback
}
