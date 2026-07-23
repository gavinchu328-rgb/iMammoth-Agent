/** 兼容非安全上下文（局域网 HTTP）；localhost / HTTPS 仍优先用 randomUUID。 */
export function newId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    try {
      return crypto.randomUUID()
    } catch {
      // http://192.168.x.x 等非安全上下文会抛错
    }
  }
  return `${Date.now()}-${Math.random().toString(36).slice(2, 11)}`
}
