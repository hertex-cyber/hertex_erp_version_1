import axios from 'axios'
import { getAccessToken, getRefreshToken, setTokens, clearTokens } from './tokens'

const baseURL = import.meta.env.VITE_API_URL || '/api/v1'

export const api = axios.create({ baseURL, timeout: 30000 })

let refreshing = null

api.interceptors.request.use((config) => {
  const token = getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config
    const status = error.response?.status
    const isAuthCall = original?.url?.includes('/auth/login') || original?.url?.includes('/auth/refresh')

    if (status === 401 && original && !original._retried && !isAuthCall) {
      const refresh = getRefreshToken()
      if (!refresh) {
        clearTokens()
        window.dispatchEvent(new Event('hertex:logout'))
        return Promise.reject(error)
      }
      original._retried = true
      try {
        refreshing =
          refreshing ||
          axios
            .post(`${baseURL}/auth/refresh`, { refresh_token: refresh })
            .then((res) => {
              setTokens(res.data)
              return res.data.access_token
            })
            .finally(() => {
              refreshing = null
            })
        const accessToken = await refreshing
        original.headers.Authorization = `Bearer ${accessToken}`
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
