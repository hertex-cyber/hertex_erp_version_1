import { create } from 'zustand'

let counter = 0

export const useToast = create((set) => ({
  toasts: [],
  push: (toast) => {
    const id = ++counter
    set((state) => ({ toasts: [...state.toasts, { id, tone: 'success', ...toast }] }))
    setTimeout(() => {
      set((state) => ({ toasts: state.toasts.filter((item) => item.id !== id) }))
    }, toast.duration ?? 4200)
  },
  dismiss: (id) => set((state) => ({ toasts: state.toasts.filter((item) => item.id !== id) })),
}))

export const toast = {
  success: (title, description) => useToast.getState().push({ title, description, tone: 'success' }),
  error: (title, description) => useToast.getState().push({ title, description, tone: 'error' }),
  info: (title, description) => useToast.getState().push({ title, description, tone: 'info' }),
}
