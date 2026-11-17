import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { api } from '../lib/api'
import { clearTokens, getAccessToken, setTokens } from '../lib/tokens'

export const useAuth = create(
  persist(
    (set, get) => ({
      user: null,
      permissions: [],
      roles: [],
      isSuperuser: false,
      loading: true,

      login: async (email, password) => {
        const { data } = await api.post('/auth/login', { email, password })
        setTokens(data)
        set({ user: data.user, loading: false })
        await get().loadPermissions()
        return data.user
      },

      register: async (payload) => {
        const { data } = await api.post('/auth/register', payload)
        setTokens(data)
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

      bootstrap: async () => {
        if (!getAccessToken()) {
          set({ loading: false, user: null })
          return
        }
        try {
          const { data } = await api.get('/auth/me')
          set({ user: data })
          await get().loadPermissions()
        } catch {
          clearTokens()
          set({ user: null, permissions: [], roles: [], isSuperuser: false })
        } finally {
          set({ loading: false })
        }
      },

      logout: async () => {
        try {
          await api.post('/auth/logout')
        } catch {
          // Session may already be gone; clear locally regardless.
        }
        clearTokens()
        set({ user: null, permissions: [], roles: [], isSuperuser: false, loading: false })
      },

      can: (code) => {
        if (!code) return true
        const { isSuperuser, permissions, user } = get()
        if (isSuperuser || user?.is_superuser) return true
        return permissions.includes(code)
      },
    }),
    {
      name: 'hertex.auth',
      partialize: (state) => ({ user: state.user }),
    },
  ),
)
