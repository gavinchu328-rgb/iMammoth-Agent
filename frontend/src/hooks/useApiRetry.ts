import { useEffect, useState } from 'react'

export type ApiLoadStatus = 'loading' | 'ready' | 'error'

/** 后端短暂不可用时自动重试；页面重新可见时也会刷新一次 */
export function useApiRetry(load: () => Promise<void>, retryMs = 3000): ApiLoadStatus {
  const [status, setStatus] = useState<ApiLoadStatus>('loading')

  useEffect(() => {
    let cancelled = false
    let timer: ReturnType<typeof setTimeout>

    const run = () => {
      load()
        .then(() => {
          if (!cancelled) setStatus('ready')
        })
        .catch((e) => {
          console.error(e)
          if (!cancelled) {
            setStatus('error')
            timer = setTimeout(run, retryMs)
          }
        })
    }

    setStatus('loading')
    run()

    const onVisible = () => {
      if (document.visibilityState === 'visible') {
        load()
          .then(() => {
            if (!cancelled) setStatus('ready')
          })
          .catch(() => {
            if (!cancelled) setStatus('error')
          })
      }
    }
    document.addEventListener('visibilitychange', onVisible)
    window.addEventListener('focus', onVisible)

    return () => {
      cancelled = true
      clearTimeout(timer)
      document.removeEventListener('visibilitychange', onVisible)
      window.removeEventListener('focus', onVisible)
    }
  }, [load, retryMs])

  return status
}
