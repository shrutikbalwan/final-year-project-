import { Check, CircleHelp, Wifi, WifiOff } from 'lucide-react'

export function RiskBadge({ level }: { level: string }) {
  const normalized = level.toLowerCase()
  const icon = normalized === 'critical' || normalized === 'warning' ? <span className="risk-dot" /> : normalized === 'normal' ? <Check size={12} /> : normalized === 'unknown' ? <CircleHelp size={12} /> : <span className="risk-dot" />
  return <span className={`risk-badge risk-${normalized}`}>{icon}{level}</span>
}

export function StatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase()
  return <span className={`connectivity-badge connectivity-${normalized}`}>{normalized === 'connected' ? <Wifi size={13} /> : <WifiOff size={13} />}{status}</span>
}
