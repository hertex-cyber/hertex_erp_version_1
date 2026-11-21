import { useCallback, useEffect, useState } from 'react'
import { api, apiErrorMessage } from '../../lib/api'

export default function useSettingValues(params = {}) {
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const signature = JSON.stringify(params)

  const load = useCallback(async () => {
    setError('')
    try {
      const response = await api.get('/settings/values', { params: { size: 500, ...params } })
      setRows(Array.isArray(response.data?.items) ? response.data.items : [])
    } catch (err) {
      setError(apiErrorMessage(err, 'Settings could not be loaded.'))
    } finally {
      setLoading(false)
    }
  }, [signature])

  useEffect(() => {
    load()
  }, [load])

  return { rows, loading, error, reload: load }
}
