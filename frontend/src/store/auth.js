import { create } from 'zustand'
import { api } from '../lib/api'
import { clearTokens, getAccessToken, getCsrfToken, hasSessionCookie, setAccessToken } from '../lib/tokens'

const emptySession = {
  user: null,
  permissions: [],
  roles: [],
  isSuperuser: false,
}

let bootstrapPromise = null

function applyTokens(data) {
  setAccessToken(data.access_token)
}

export const useAuth = create((set, get) => ({
  ...emptySession,
  loading: true,

  login: async (email, password) => {
    const { data } = await api.post('/auth/login', { email, password })
    if (data.mfa_required) {
      return {
        mfaRequired: true,
        challengeToken: data.challenge_token,
        expiresIn: data.expires_in,
      }
    }
    applyTokens(data)
    set({ user: data.user, loading: false })
    await get().loadPermissions()
    return { mfaRequired: false, user: data.user }
  },

  verifyMfa: async (challengeToken, code, recoveryCode) => {
    const payload = { challenge_token: challengeToken }
    if (recoveryCode) payload.recovery_code = recoveryCode
    else payload.code = code
    const { data } = await api.post('/auth/mfa/verify', payload)
    applyTokens(data)
    set({ user: data.user, loading: false })
    await get().loadPermissions()
    return data.user
  },

  register: async (payload) => {
    const { data } = await api.post('/auth/register', payload)
    applyTokens(data)
    set({ user: data.user, loading: false })
    await get().loadPermissions()
    return data.user
  },

  loadPermissions: async () => {
    const { data } = await api.get('/auth/permissions')
    set({
      permissions: data.permissions ?? [],
      roles: data.roles ?? [],
      isSuperuser: Boolean(data.is_superuser),
    })
  },

  bootstrap: () => {
    if (bootstrapPromise) return bootstrapPromise
    bootstrapPromise = (async () => {
      try {
        if (!hasSessionCookie() && !getAccessToken()) {
          set({ ...emptySession, loading: false })
          return
        }
        if (!getAccessToken()) {
          const csrf = getCsrfToken()
          const { data } = await api.post(
            '/auth/refresh',
            {},
            { headers: csrf ? { 'X-CSRF-Token': csrf } : {} },
          )
          applyTokens(data)
        }
        const { data } = await api.get('/auth/me')
        set({ user: data, loading: false })
        await get().loadPermissions()
      } catch {
        clearTokens()
        set({ ...emptySession, loading: false })
      }
    })().finally(() => {
      bootstrapPromise = null
    })
    return bootstrapPromise
  },

  changePassword: async (currentPassword, newPassword) => {
    const { data } = await api.post('/auth/change-password', {
      current_password: currentPassword,
      new_password: newPassword,
    })
    applyTokens(data)
    set({ user: data.user })
    await get().loadPermissions()
    return data
  },

  logout: async () => {
    try {
      await api.post('/auth/logout')
    } catch {
      clearTokens()
    }
    clearTokens()
    set({ ...emptySession, loading: false })
  },

  can: (code) => {
    if (!code) return true
    const { isSuperuser, permissions, user } = get()
    if (isSuperuser || user?.is_superuser) return true
    return permissions.includes(code)
  },
}))
