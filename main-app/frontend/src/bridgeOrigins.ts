export function isExactBridgeOriginAllowed(configuredOrigin: string, candidateOrigin: string): boolean {
  const configured = configuredOrigin.trim()
  const candidate = candidateOrigin.trim()
  if (!configured || configured === '*' || !candidate || candidate === '*') return false
  try {
    return new URL(configured).origin === new URL(candidate).origin
  } catch {
    return false
  }
}
