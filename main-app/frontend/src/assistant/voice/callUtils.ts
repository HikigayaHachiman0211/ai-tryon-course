/* Call mode utility functions */

/** Format seconds to MM:SS display */
export function formatCallDuration(seconds: number): string {
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

/** Generate a unique call ID */
export function generateCallId(): string {
  return `call_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** Generate a unique turn ID */
export function generateTurnId(): string {
  return `turn_${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}
