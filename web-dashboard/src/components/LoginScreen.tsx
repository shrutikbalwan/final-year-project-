import { useState, type FormEvent } from 'react'
import { ArrowRight, HardHat, ShieldCheck } from 'lucide-react'

export function LoginScreen({ onLogin, error, busy }: {
  onLogin: (username: string, password: string) => void
  error?: string | null
  busy?: boolean
}) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const submit = (event: FormEvent) => {
    event.preventDefault()
    onLogin(username.trim(), password)
  }
  return <main className="login-screen"><div className="login-aside"><div className="login-brand"><div className="brand-mark"><ShieldCheck size={21} /></div><strong>sentinel</strong><span>SAFETY OPERATIONS</span></div><div className="login-art"><div className="orbit orbit-one" /><div className="orbit orbit-two" /><div className="login-helmet"><HardHat size={80} strokeWidth={1.1} /></div><span className="floating-chip chip-one"><i /> Device online</span><span className="floating-chip chip-two"><ShieldCheck size={14} /> Risk monitoring</span></div><div className="login-side-copy"><small>CONNECTED WORKPLACE INTELLIGENCE</small><h2>See risk sooner.<br />Keep teams moving.</h2><p>One clear view across connected helmet telemetry and safety events.</p></div><span className="login-copyright">SMART SAFETY HELMET · PHASE 1</span></div><div className="login-main"><div className="login-form-wrap"><div className="login-symbol"><ShieldCheck size={23} /></div><div className="eyebrow">SECURE LOCAL SIGN-IN</div><h1>Welcome back</h1><p className="login-subtitle">Sign in with an account configured by the API administrator.</p>{error && <div className="demo-warning" role="alert">{error}</div>}<form onSubmit={submit}><label htmlFor="username">Username</label><input id="username" autoComplete="username" value={username} onChange={e => setUsername(e.target.value)} required /><label htmlFor="password">Password</label><input id="password" type="password" autoComplete="current-password" value={password} onChange={e => setPassword(e.target.value)} required /><button className="button primary login-button" type="submit" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'} <ArrowRight size={16} /></button></form><div className="login-security"><ShieldCheck size={15} /><span>Credentials are sent to the API. Tokens remain in memory and expire automatically; use HTTPS outside local development.</span></div></div></div></main>
}
