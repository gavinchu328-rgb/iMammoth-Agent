import { useCallback, useEffect, useState } from 'react'

export type BackendHealth = 'checking' | 'up' | 'down'

/** 轮询 /api/health，用于顶部提示与避免「假空页面」 */
export function useBackendHealth(pollMs = 5000) {
  const [health, setHealth] = useState<BackendHealth>('checking')

  const check = useCallback(async () => {
    try {
      const res = await fetch('/api/health', { cache: 'no-store' })
      setHealth(res.ok ? 'up' : 'down')
    } catch {
      setHealth('down')
    }
  }, [])

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    const run = async () => {
      await check()
      if (!cancelled) timer = setTimeout(run, pollMs)
    }

    run()

    const onVisible = () => {
      if (document.visibilityState === 'visible') void check()
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)

    return () => {
      cancelled = true
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [check, pollMs])

  return { health, check }
}
