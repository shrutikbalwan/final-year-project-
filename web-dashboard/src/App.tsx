import { lazy, Suspense, useCallback, useEffect, useMemo, useState } from 'react'
import {
  Activity, AlertCircle, AlertTriangle, ArrowDownToLine, Bell, Check, ChevronDown,
  CircleHelp, Clock3, HardHat, LayoutDashboard, LogOut, MapPin, Menu, RefreshCw,
  ShieldCheck, SlidersHorizontal, Video, X,
} from 'lucide-react'
import {
  api, ApiError, type HelmetDetail, type HelmetSummary, type Incident,
  type RiskEvaluation, type SafetyEvent, type Telemetry, type WorkplaceProfile,
} from './api'
import { LoginScreen } from './components/LoginScreen'
import { RiskBadge, StatusBadge } from './components/Badges'

const HistoryChart = lazy(() => import('./components/HistoryChart').then(module => ({ default: module.HistoryChart })))

type Role = 'administrator' | 'supervisor' | 'viewer'
type User = { name: string; role: Role }
type Section = 'overview' | 'helmets' | 'incidents' | 'events' | 'history' | 'profiles' | 'reports'
type DashboardData = { helmets: HelmetSummary[]; incidents: Incident[]; events: SafetyEvent[]; profiles: WorkplaceProfile[]; risks: Record<string, RiskEvaluation> }

const initialData: DashboardData = { helmets: [], incidents: [], events: [], profiles: [], risks: {} }

function messageFor(error: unknown) {
  if (error instanceof ApiError) {
    if (error.kind === 'network') return 'Cannot reach the local API. Check that FastAPI is running and the API URL is correct.'
    if (error.kind === 'invalid_response') return 'The API returned data that does not match the dashboard contract.'
    return error.message
  }
  return 'Something went wrong while loading dashboard data.'
}

function timeAgo(value: string | null) {
  if (!value) return 'No confirmed contact'
  const seconds = Math.max(0, Math.floor((Date.now() - new Date(value).getTime()) / 1000))
  if (seconds < 60) return 'Just now'
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`
  return new Date(value).toLocaleString()
}

function App() {
  const [user, setUser] = useState<User | null>(null)
  const [authError, setAuthError] = useState<string | null>(null)
  const [authBusy, setAuthBusy] = useState(false)
  const [section, setSection] = useState<Section>('overview')
  const [data, setData] = useState<DashboardData>(initialData)
  const [loading, setLoading] = useState(false)
  const [apiOnline, setApiOnline] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedHelmet, setSelectedHelmet] = useState<string | null>(null)
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null)
  const [detail, setDetail] = useState<HelmetDetail | null>(null)
  const [history, setHistory] = useState<Telemetry[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)
  const [periodDays, setPeriodDays] = useState(7)
  const [measurement, setMeasurement] = useState('')
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [busyIncident, setBusyIncident] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)
  const [mobileNav, setMobileNav] = useState(false)

  const login = async (username: string, password: string) => {
    setAuthBusy(true); setAuthError(null)
    try {
      const result = await api.login(username, password)
      setUser({ name: result.user_id, role: result.role })
    } catch (caught) { setAuthError(messageFor(caught)) }
    finally { setAuthBusy(false) }
  }

  const signOut = useCallback(() => { api.logout(); setUser(null); setData(initialData) }, [])
  useEffect(() => { api.setUnauthorizedHandler(signOut); return () => api.setUnauthorizedHandler(undefined) }, [signOut])

  const loadDashboard = useCallback(async () => {
    setLoading(true); setError(null)
    try {
      await api.health()
      const [helmetPage, incidentPage, eventPage, profiles] = await Promise.all([
        api.helmets(), api.incidents(), api.events(), api.profiles(),
      ])
      const riskEntries = await Promise.all(helmetPage.items.map(async (helmet) => {
        try { return [helmet.helmet_id, await api.risk(helmet.helmet_id)] as const }
        catch (caught) {
          if (caught instanceof ApiError && ['expired', 'forbidden'].includes(caught.kind)) throw caught
          return null
        }
      }))
      const risks = Object.fromEntries(riskEntries.filter((entry): entry is NonNullable<typeof entry> => entry !== null))
      setData({ helmets: helmetPage.items, incidents: incidentPage.items, events: eventPage.items, profiles, risks })
      setApiOnline(true)
    } catch (caught) {
      setApiOnline(false)
      setError(messageFor(caught))
      if (caught instanceof ApiError && caught.kind === 'expired') signOut()
    } finally { setLoading(false) }
  }, [])

  useEffect(() => { if (user) void loadDashboard() }, [user, loadDashboard])

  const openHelmet = async (id: string) => {
    setSelectedHelmet(id); setDetail(null); setActionError(null)
    try { setDetail(await api.helmet(id)) }
    catch (caught) { setActionError(messageFor(caught)) }
  }

  const chooseIncident = async (incident: Incident) => {
    setSelectedIncident(incident); setActionError(null)
    try {
      const [fresh, entries] = await Promise.all([api.incident(incident.incident_id), api.incidentHistory(incident.incident_id)])
      setSelectedIncident({ ...fresh, history: entries })
    } catch (caught) { setActionError(messageFor(caught)) }
  }

  const acknowledge = async (incident: Incident) => {
    if (!user || !['supervisor', 'administrator'].includes(user.role)) return
    setBusyIncident(incident.incident_id); setActionError(null)
    try {
      await api.acknowledgeIncident(incident.incident_id, user.name)
      await loadDashboard()
      const updated = await api.incident(incident.incident_id)
      setSelectedIncident(updated)
    } catch (caught) { setActionError(messageFor(caught)) }
    finally { setBusyIncident(null) }
  }

  useEffect(() => {
    if (section !== 'history' || !selectedHelmet) return
    let cancelled = false
    const getHistory = async () => {
      setHistoryLoading(true); setHistoryError(null)
      const end = new Date()
      const start = new Date(end.getTime() - periodDays * 86400000)
      try {
        const page = await api.telemetry(`&device_id=${encodeURIComponent(selectedHelmet)}&start=${encodeURIComponent(start.toISOString())}&end=${encodeURIComponent(end.toISOString())}`)
        if (!cancelled) setHistory(page.items)
      } catch (caught) { if (!cancelled) setHistoryError(messageFor(caught)) }
      finally { if (!cancelled) setHistoryLoading(false) }
    }
    void getHistory()
    return () => { cancelled = true }
  }, [section, selectedHelmet, periodDays])

  const reportCsv = () => {
    const rows = [['helmet_id', 'workplace_id', 'connectivity', 'last_seen_at', 'battery_percent', 'risk_level']]
    for (const helmet of data.helmets) rows.push([
      helmet.helmet_id, helmet.workplace_id, helmet.connectivity_status, helmet.last_seen_at ?? '',
      helmet.battery_reading.value?.toString() ?? '', data.risks[helmet.helmet_id]?.risk_level ?? 'Unknown',
    ])
    const csv = rows.map(row => row.map(value => `"${value.replaceAll('"', '""')}"`).join(',')).join('\r\n')
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }))
    link.download = `helmet-status-${new Date().toISOString().slice(0, 10)}.csv`
    link.click(); URL.revokeObjectURL(link.href)
  }

  const activeIncidents = useMemo(() => data.incidents.filter(item => item.status === 'open' || item.status === 'acknowledged'), [data.incidents])
  const sectionTitle: Record<Section, string> = {
    overview: 'Operations overview', helmets: 'Helmet fleet', incidents: 'Incident management',
    events: 'Camera detections', history: 'Telemetry history', profiles: 'Workplace rules', reports: 'Reports',
  }

  if (!user) {
    return <LoginScreen onLogin={(username, password) => void login(username, password)} error={authError} busy={authBusy} />
  }

  const navItems: { id: Section; label: string; icon: typeof LayoutDashboard }[] = [
    { id: 'overview', label: 'Overview', icon: LayoutDashboard },
    { id: 'helmets', label: 'Helmet fleet', icon: HardHat },
    { id: 'incidents', label: 'Incidents', icon: AlertTriangle },
    { id: 'events', label: 'Camera detections', icon: Video },
    { id: 'history', label: 'Telemetry history', icon: Activity },
    { id: 'profiles', label: 'Workplace rules', icon: SlidersHorizontal },
    { id: 'reports', label: 'Reports', icon: ArrowDownToLine },
  ]

  return <div className="app-shell">
    <aside className={`sidebar ${mobileNav ? 'sidebar-open' : ''}`}>
      <div className="brand"><div className="brand-mark"><ShieldCheck size={21} /></div><div><strong>sentinel</strong><span>SAFETY OPERATIONS</span></div></div>
      <div className="site-picker"><div className="site-dot" /><div><small>ACTIVE WORKPLACE</small><strong>All workplaces</strong></div><ChevronDown size={15} /></div>
      <div className="nav-caption">WORKSPACE</div>
      <nav aria-label="Dashboard navigation">{navItems.map(item => {
        const Icon = item.icon
        return <button key={item.id} className={`nav-item ${section === item.id ? 'nav-active' : ''}`} onClick={() => { setSection(item.id); setMobileNav(false) }}>
          <Icon size={17} strokeWidth={1.8} /><span>{item.label}</span>
          {item.id === 'incidents' && activeIncidents.length > 0 && <em>{activeIncidents.length}</em>}
        </button>
      })}</nav>
      <div className="sidebar-foot"><div className="connection-indicator"><span className={apiOnline ? '' : 'offline-dot'} /> API connection <b>{apiOnline ? 'online' : 'offline'}</b></div><small>PHASE 1 · DEVELOPMENT</small></div>
    </aside>

    <main className="main-area">
      <header className="topbar">
        <button className="icon-button mobile-menu" aria-label="Open navigation" onClick={() => setMobileNav(!mobileNav)}><Menu size={19} /></button>
        <div className="breadcrumbs"><span>Safety operations</span><span className="crumb-slash">/</span><b>{sectionTitle[section]}</b></div>
        <div className={`top-actions ${apiOnline ? '' : 'api-offline'}`}><div className="api-pill"><span /> API {apiOnline ? 'online' : 'offline'}</div><button className="icon-button" aria-label="Refresh data" onClick={() => void loadDashboard()}><RefreshCw size={17} className={loading ? 'spin' : ''} /></button><button className="notification-button" aria-label="Active incidents" onClick={() => setSection('incidents')}><Bell size={17} />{activeIncidents.length > 0 && <i />}</button><div className="top-divider" /><div className="user-chip"><div className="avatar">{user.name.slice(0, 1).toUpperCase()}</div><span><b>{user.name}</b><small>{user.role}</small></span><button className="icon-button signout" aria-label="Sign out" onClick={signOut}><LogOut size={15} /></button></div></div>
      </header>

      <div className="dev-banner"><CircleHelp size={15} /><span><b>Authenticated local session.</b> The API verified this identity and enforces the assigned role.</span></div>

      <div className="content-area">
        <div className="page-heading"><div><div className="eyebrow">MONITORING CENTER <span>•</span> LIVE DATA</div><h1>{sectionTitle[section]}</h1><p>Helmet telemetry and safety events from the connected local API.</p></div><div className="heading-right"><span className="updated-label"><Clock3 size={14} /> Updated {new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span><button className="button secondary" onClick={() => void loadDashboard()}><RefreshCw size={15} /> Refresh</button></div></div>

        {error && <div className="error-banner" role="alert"><AlertCircle size={18} /><span>{error}</span><button onClick={() => void loadDashboard()}>Retry</button><button className="dismiss" aria-label="Dismiss error" onClick={() => setError(null)}><X size={16} /></button></div>}
        {actionError && <div className="error-banner compact" role="alert"><AlertCircle size={17} /><span>{actionError}</span><button className="dismiss" aria-label="Dismiss action error" onClick={() => setActionError(null)}><X size={16} /></button></div>}

        {section === 'overview' && <Overview data={data} loading={loading} incidents={activeIncidents} onHelmet={openHelmet} onIncident={chooseIncident} />}
        {section === 'helmets' && <HelmetFleet data={data} loading={loading} onHelmet={openHelmet} />}
        {section === 'incidents' && <IncidentList incidents={data.incidents} loading={loading} onIncident={chooseIncident} />}
        {section === 'events' && <EventList events={data.events} loading={loading} />}
        {section === 'history' && <section className="panel history-panel"><div className="panel-heading"><div><h2>Sensor trends</h2><p>Historical telemetry from persisted API records</p></div><div className="chart-filters"><select aria-label="Helmet filter" value={selectedHelmet ?? ''} onChange={e => setSelectedHelmet(e.target.value || null)}><option value="">Select helmet</option>{data.helmets.map(helmet => <option key={helmet.helmet_id} value={helmet.helmet_id}>{helmet.helmet_id}</option>)}</select><select aria-label="Time range" value={periodDays} onChange={e => setPeriodDays(Number(e.target.value))}><option value={1}>Last 24 hours</option><option value={7}>Last 7 days</option><option value={30}>Last 30 days</option></select></div></div>{!selectedHelmet ? <EmptyState icon={<Activity />} title="Choose a helmet" detail="Select a device to chart its recorded sensor values." /> : <HistoryView rows={history} loading={historyLoading} error={historyError} measurement={measurement} onMeasurement={setMeasurement} />}</section>}
        {section === 'profiles' && <ProfileList profiles={data.profiles} loading={loading} />}
        {section === 'reports' && <Reports data={data} loading={loading} onExport={reportCsv} />}

        <footer className="page-footer"><span><ShieldCheck size={14} /> Safety data should be reviewed by an authorized workplace supervisor.</span><span>SMART SAFETY HELMET · PHASE 1</span></footer>
      </div>
    </main>

    {selectedHelmet && <aside className="detail-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) { setSelectedHelmet(null); setDetail(null) } }}><div className="detail-drawer"><div className="drawer-head"><div><small>HELMET PROFILE</small><h2>{selectedHelmet}</h2></div><button aria-label="Close helmet detail" className="icon-button" onClick={() => { setSelectedHelmet(null); setDetail(null) }}><X size={18} /></button></div>{!detail ? <LoadingState label="Loading helmet details" /> : <HelmetDetailPanel detail={detail} risk={data.risks[selectedHelmet]} />}</div></aside>}
    {selectedIncident && <aside className="detail-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setSelectedIncident(null) }}><div className="detail-drawer"><div className="drawer-head"><div><small>INCIDENT DETAILS</small><h2>{selectedIncident.incident_id.slice(0, 18)}</h2></div><button aria-label="Close incident detail" className="icon-button" onClick={() => setSelectedIncident(null)}><X size={18} /></button></div><IncidentDetail incident={selectedIncident} user={user} busy={busyIncident === selectedIncident.incident_id} onAcknowledge={() => void acknowledge(selectedIncident)} /></div></aside>}
  </div>
}

function Overview({ data, loading, incidents, onHelmet, onIncident }: { data: DashboardData; loading: boolean; incidents: Incident[]; onHelmet: (id: string) => void; onIncident: (incident: Incident) => void }) {
  const connected = data.helmets.filter(item => item.connectivity_status === 'connected').length
  const unknown = data.helmets.filter(item => !data.risks[item.helmet_id] || data.risks[item.helmet_id].risk_level === 'Unknown').length
  const currentRiskCount = Object.values(data.risks).filter(item => ['Warning', 'Critical'].includes(item.risk_level)).length
  return <>
    <div className="stat-grid">
      <StatCard icon={<HardHat />} label="Registered helmets" value={loading ? '—' : String(data.helmets.length).padStart(2, '0')} foot="Devices with telemetry" tone="green" />
      <StatCard icon={<Activity />} label="Connected now" value={loading ? '—' : `${connected} / ${data.helmets.length}`} foot="Reported connectivity" tone="blue" />
      <StatCard icon={<Bell />} label="Active incidents" value={loading ? '—' : String(incidents.length).padStart(2, '0')} foot="Open or acknowledged" tone="orange" />
      <StatCard icon={<CircleHelp />} label="Unknown status" value={loading ? '—' : String(unknown).padStart(2, '0')} foot="Cannot establish current risk" tone="slate" />
    </div>
    <div className="overview-grid"><section className="panel fleet-panel"><div className="panel-heading"><div><h2>Helmet fleet</h2><p>Latest device heartbeat and risk assessment</p></div><span className="live-tag"><i /> LIVE</span></div>{loading && !data.helmets.length ? <LoadingState label="Loading fleet data" /> : data.helmets.length === 0 ? <EmptyState icon={<HardHat />} title="No helmets registered" detail="Helmets appear after the API receives valid telemetry." /> : <div className="fleet-list">{data.helmets.slice(0, 7).map(item => <button className="fleet-row" key={item.helmet_id} onClick={() => onHelmet(item.helmet_id)}><div className="helmet-avatar"><HardHat size={17} /></div><span className="fleet-name"><b>{item.helmet_id}</b><small><MapPin size={12} /> {item.workplace_id}</small></span><span className="fleet-battery"><span>BATTERY</span><b>{item.battery_reading.value === null ? '—' : `${item.battery_reading.value}%`}</b></span><StatusBadge status={item.connectivity_status} /><RiskBadge level={data.risks[item.helmet_id]?.risk_level ?? 'Unknown'} /></button>)}</div>}</section>
      <section className="panel incident-panel"><div className="panel-heading"><div><h2>Priority incidents</h2><p>Requires supervisor review</p></div><span className="count-pill">{incidents.length}</span></div>{loading && !incidents.length ? <LoadingState label="Loading incidents" /> : incidents.length === 0 ? <EmptyState icon={<ShieldCheck />} title="No active incidents" detail="New incidents will appear when rule evaluation raises a risk." /> : <div className="incident-preview-list">{incidents.slice(0, 5).map(incident => <button className="incident-preview" key={incident.incident_id} onClick={() => onIncident(incident)}><RiskBadge level={incident.severity} /><span><b>{incident.reason}</b><small>{incident.device_id} · {timeAgo(incident.updated_at)}</small></span><span className="preview-arrow">›</span></button>)}</div>}</section></div>
    <div className="bottom-grid"><section className="panel readings-panel"><div className="panel-heading"><div><h2>Current device status</h2><p>Last contact reported by each helmet</p></div><span className="subtle-label">{data.helmets.length} DEVICES</span></div>{data.helmets.length ? <div className="status-table"><div className="status-header"><span>DEVICE</span><span>LAST SEEN</span><span>BATTERY</span><span>RISK</span></div>{data.helmets.slice(0, 5).map(h => <div className="status-row" key={h.helmet_id}><b>{h.helmet_id}</b><span>{timeAgo(h.last_seen_at)}</span><span className={h.battery_reading.value !== null && h.battery_reading.value < 25 ? 'battery-low' : ''}>{h.battery_reading.value ?? '—'}{h.battery_reading.value === null ? '' : '%'}</span><RiskBadge level={data.risks[h.helmet_id]?.risk_level ?? 'Unknown'} /></div>)}</div> : <EmptyState icon={<Activity />} title="No current readings" detail="The API has not stored helmet telemetry yet." />}</section><section className="panel note-panel"><div className="note-icon"><AlertCircle size={17} /></div><div><b>Risk is rule based</b><p>Risk levels reflect the configured workplace profile and current data quality. Missing or stale readings remain Unknown; they are never treated as safe.</p></div><span className="note-count">{currentRiskCount} elevated</span></section></div>
  </>
}

function HelmetFleet({ data, loading, onHelmet }: { data: DashboardData; loading: boolean; onHelmet: (id: string) => void }) {
  return <section className="panel"><div className="panel-heading"><div><h2>All devices</h2><p>Current status retrieved from the backend</p></div><span className="count-pill">{data.helmets.length}</span></div>{loading ? <LoadingState label="Loading helmets" /> : data.helmets.length === 0 ? <EmptyState icon={<HardHat />} title="No helmets registered" detail="Ingest telemetry through POST /api/v1/telemetry to populate this view." /> : <div className="helmet-cards">{data.helmets.map(h => <button key={h.helmet_id} className="helmet-card" onClick={() => onHelmet(h.helmet_id)}><div className="card-top"><span className="helmet-avatar large"><HardHat size={19} /></span><RiskBadge level={data.risks[h.helmet_id]?.risk_level ?? 'Unknown'} /></div><h3>{h.helmet_id}</h3><p><MapPin size={13} />{h.workplace_id}</p><div className="helmet-card-foot"><span><small>BATTERY</small><b>{h.battery_reading.value ?? '—'}{h.battery_reading.value === null ? '' : '%'}</b></span><span><small>CONNECTIVITY</small><StatusBadge status={h.connectivity_status} /></span><span><small>LAST SEEN</small><b>{timeAgo(h.last_seen_at)}</b></span></div></button>)}</div>}</section>
}

function IncidentList({ incidents, loading, onIncident }: { incidents: Incident[]; loading: boolean; onIncident: (incident: Incident) => void }) {
  return <section className="panel"><div className="panel-heading"><div><h2>Incident queue</h2><p>Rule-engine incidents with reason and status</p></div><div className="table-filter"><SlidersHorizontal size={14} /> All severities</div></div>{loading ? <LoadingState label="Loading incident queue" /> : incidents.length === 0 ? <EmptyState icon={<ShieldCheck />} title="Incident queue is clear" detail="Incidents created by the safety engine will appear here." /> : <div className="incident-table-wrap"><table className="incident-table"><thead><tr><th>SEVERITY</th><th>DEVICE / WORKPLACE</th><th>REASON</th><th>STATUS</th><th>UPDATED</th></tr></thead><tbody>{incidents.map(incident => <tr key={incident.incident_id} onClick={() => onIncident(incident)} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter') onIncident(incident) }}><td><RiskBadge level={incident.severity} /></td><td><b>{incident.device_id}</b><small>{incident.workplace_id}</small></td><td className="reason-cell">{incident.reason}</td><td><span className={`incident-status status-${incident.status}`}>{incident.status}</span></td><td>{new Date(incident.updated_at).toLocaleString()}</td></tr>)}</tbody></table></div>}</section>
}

function EventList({ events, loading }: { events: SafetyEvent[]; loading: boolean }) {
  return <section className="panel"><div className="panel-heading"><div><h2>Detection event feed</h2><p>Camera safety events stored by the backend</p></div><span className="count-pill">{events.length}</span></div>{loading ? <LoadingState label="Loading detection events" /> : events.length === 0 ? <EmptyState icon={<Video />} title="No detection events" detail="This feed uses saved SafetyEvent records. The current API supports event ingestion and history, not live video." /> : <div className="event-feed">{events.map(event => <article key={event.event_id} className="event-row"><div className="event-icon"><Video size={16} /></div><div className="event-main"><div><b>{event.event_type.replaceAll('_', ' ')}</b><span>{event.device_id} · {event.workplace_id}</span></div><p>{event.description}</p><small>{new Date(event.occurred_at).toLocaleString()} · reported {new Date(event.reported_at).toLocaleTimeString()}</small></div><RiskBadge level={event.severity} /></article>)}</div>}</section>
}

function HistoryView({ rows, loading, error, measurement, onMeasurement }: { rows: Telemetry[]; loading: boolean; error: string | null; measurement: string; onMeasurement: (value: string) => void }) {
  const measurements = [...new Set(rows.flatMap(row => row.readings.map(reading => reading.measurement_type)))].sort()
  useEffect(() => { if (!measurement && measurements.length) onMeasurement(measurements[0]) }, [measurement, measurements.join('|'), onMeasurement])
  if (loading) return <LoadingState label="Loading telemetry history" />
  if (error) return <div role="alert" className="inline-error"><AlertCircle size={16} />{error}</div>
  if (!rows.length) return <EmptyState icon={<Activity />} title="No history in this range" detail="Historical charts use persisted telemetry. Try a wider date range or select another helmet." />
  const values = rows.flatMap(row => row.readings.filter(reading => reading.measurement_type === measurement && reading.reading_status === 'valid' && reading.value !== null).map(reading => ({ at: row.observed_at, value: reading.value as number, unit: reading.unit_code }))).reverse()
  return <><div className="chart-toolbar"><label>MEASUREMENT<select aria-label="Measurement" value={measurement} onChange={e => onMeasurement(e.target.value)}>{measurements.map(key => <option key={key}>{key}</option>)}</select></label><span>{rows.length} samples · latest first from API</span></div>{values.length ? <Suspense fallback={<LoadingState label="Loading chart" />}><HistoryChart values={values} /></Suspense> : <EmptyState icon={<Activity />} title="No valid values" detail="No valid values were returned for this measurement. Missing and invalid readings are not plotted." />}</>
}

function ProfileList({ profiles, loading }: { profiles: WorkplaceProfile[]; loading: boolean }) {
  return <><div className="readonly-callout"><SlidersHorizontal size={17} /><span><b>Read-only configuration</b> — the current backend exposes validated profiles for review but has no profile editing endpoint or authenticated access.</span></div>{loading ? <LoadingState label="Loading workplace profiles" /> : profiles.length === 0 ? <EmptyState icon={<MapPin />} title="No workplace profiles configured" detail="Configure SAFETY_PROFILES_PATH when starting the API. Without a matching profile, current risk is Unknown." /> : <div className="profile-grid">{profiles.map(profile => <section className="panel profile-card" key={profile.workplace_id}><div className="profile-title"><div className="profile-symbol"><MapPin size={17} /></div><span><h2>{profile.profile_name}</h2><small>{profile.workplace_id}</small></span><span className="readonly-tag">READ ONLY</span></div><div className="profile-bands"><span><small>ADVISORY</small><b>{profile.score_bands.advisory}</b></span><span><small>WARNING</small><b>{profile.score_bands.warning}</b></span><span><small>CRITICAL</small><b>{profile.score_bands.critical}</b></span></div><h3>Configured rules <em>{profile.rules.length}</em></h3><div className="rule-list">{profile.rules.map(rule => <div key={rule.rule_id} className="rule-row"><span><b>{rule.measurement_type}</b><small>{rule.rule_id} · {rule.reason}</small></span><span className="rule-value">{rule.operator} {rule.threshold} {rule.unit_code}</span><RiskBadge level={rule.risk_level} /></div>)}</div><p className="profile-footer">Data freshness limits: telemetry {profile.max_telemetry_age_seconds}s · readings {profile.max_reading_age_seconds}s</p><div className="profile-warning">Development profile values are not certified industrial safety limits.</div></section>)}</div>}</>
}

function Reports({ data, loading, onExport }: { data: DashboardData; loading: boolean; onExport: () => void }) {
  const connected = data.helmets.filter(item => item.connectivity_status === 'connected').length
  const critical = data.incidents.filter(item => item.severity === 'Critical').length
  return <div className="report-layout"><section className="panel report-summary"><div className="panel-heading"><div><h2>Fleet status report</h2><p>Snapshot generated from live backend records</p></div><span className="report-period">CURRENT SNAPSHOT</span></div>{loading ? <LoadingState label="Preparing report" /> : <><div className="report-kpis"><span><small>HELMETS</small><b>{data.helmets.length}</b></span><span><small>CONNECTED</small><b>{connected}</b></span><span><small>ACTIVE INCIDENTS</small><b>{data.incidents.filter(i => i.status === 'open' || i.status === 'acknowledged').length}</b></span><span><small>CRITICAL</small><b className="text-red">{critical}</b></span></div><button className="button primary" onClick={onExport}><ArrowDownToLine size={16} /> Export current fleet CSV</button></>}</section><section className="panel report-note"><div className="report-note-icon"><ShieldCheck /></div><h2>Report scope</h2><p>Exports include device identifiers, workplace, latest connectivity, last-seen time, battery, and current risk evaluation returned by the API. This is an operational snapshot, not a compliance certification.</p></section></div>
}

function HelmetDetailPanel({ detail, risk }: { detail: HelmetDetail; risk?: RiskEvaluation }) {
  const readings = detail.latest_telemetry.readings
  return <div className="drawer-content"><div className="drawer-status"><StatusBadge status={detail.connectivity_status} /><RiskBadge level={risk?.risk_level ?? 'Unknown'} /></div><div className="drawer-section"><div className="drawer-section-heading"><h3>Device health</h3><small>Latest telemetry {timeAgo(detail.last_telemetry_at)}</small></div><div className="health-grid"><span><small>BATTERY</small><b>{detail.battery_reading.value ?? '—'}{detail.battery_reading.value === null ? '' : '%'}</b></span><span><small>LAST SEEN</small><b>{timeAgo(detail.last_seen_at)}</b></span><span><small>CONNECTIVITY</small><b>{detail.connectivity_status}</b></span></div></div><div className="drawer-section"><div className="drawer-section-heading"><h3>Sensor readings</h3><small>{readings.length} configured values</small></div>{readings.map(reading => <div className="sensor-line" key={reading.reading_id}><span><b>{reading.measurement_type.replaceAll('_', ' ')}</b><small>{reading.sensor_id}</small></span><span className={`reading-value reading-${reading.reading_status}`}>{reading.value === null ? 'No reading' : `${reading.value} ${reading.unit_code}`}<small>{reading.reading_status}</small></span></div>)}</div><div className="drawer-section"><div className="drawer-section-heading"><h3>Rule evaluation</h3><small>{risk ? `Score ${risk.score}` : 'Unavailable'}</small></div>{risk ? <><div className="risk-reasons">{risk.reasons.map((reason, index) => <p key={`${index}-${reason}`}><span />{reason}</p>)}</div>{risk.quality_issue_codes.length > 0 && <div className="quality-codes">Data quality: {risk.quality_issue_codes.join(', ')}</div>}</> : <div className="muted-copy">Risk evaluation is unavailable. Unknown must not be interpreted as safe.</div>}</div><div className="drawer-section"><small className="mono-label">SOURCE TELEMETRY EVENT</small><code>{detail.latest_telemetry.event_id}</code></div></div>
}

function IncidentDetail({ incident, user, busy, onAcknowledge }: { incident: Incident; user: User; busy: boolean; onAcknowledge: () => void }) {
  const canAcknowledge = ['supervisor', 'administrator'].includes(user.role) && incident.status === 'open'
  return <div className="drawer-content"><div className="drawer-status"><RiskBadge level={incident.severity} /><span className={`incident-status status-${incident.status}`}>{incident.status}</span></div><div className="incident-summary"><b>{incident.reason}</b><p>{incident.device_id} · {incident.workplace_id}</p><small>Opened {new Date(incident.opened_at).toLocaleString()}</small></div>{canAcknowledge && <button className="button primary full-button" onClick={onAcknowledge} disabled={busy}><Check size={15} />{busy ? 'Acknowledging…' : 'Acknowledge incident'}</button>}{incident.status === 'acknowledged' && <div className="ack-confirm"><Check size={15} />Acknowledged by {incident.acknowledged_by ?? 'supervisor'} {incident.acknowledged_at ? `at ${new Date(incident.acknowledged_at).toLocaleString()}` : ''}</div>}{user.role === 'viewer' && incident.status === 'open' && <div className="readonly-callout small-callout">Viewer accounts are not permitted to acknowledge incidents.</div>}<div className="drawer-section"><div className="drawer-section-heading"><h3>Incident source</h3><small>{incident.occurrence_count} occurrence(s)</small></div><div className="source-reference"><small>TELEMETRY EVENT</small><code>{incident.source.telemetry_event_id}</code></div>{incident.source.rule_ids.map(id => <div className="source-reference" key={id}><small>MATCHED RULE</small><code>{id}</code></div>)}</div><div className="drawer-section"><div className="drawer-section-heading"><h3>History</h3><small>{incident.history.length} entries</small></div><div className="history-timeline">{incident.history.map(entry => <div className="history-entry" key={entry.entry_id}><span className="timeline-dot" /><div><b>{entry.action.replaceAll('_', ' ')}</b><small>{new Date(entry.timestamp).toLocaleString()}</small>{entry.note && <p>{entry.note}</p>}</div></div>)}</div></div><div className="auth-warning">The API verifies the bearer token and role for each acknowledgement request.</div></div>
}

function StatCard({ icon, label, value, foot, tone }: { icon: React.ReactNode; label: string; value: string; foot: string; tone: string }) {
  return <section className="stat-card"><div className={`stat-icon tone-${tone}`}>{icon}</div><span className="stat-label">{label}</span><b className="stat-value">{value}</b><small className="stat-foot">{foot}</small><div className={`stat-accent accent-${tone}`} /></section>
}
function LoadingState({ label }: { label: string }) { return <div className="loading-state" role="status"><span className="loader" />{label}</div> }
function EmptyState({ icon, title, detail }: { icon: React.ReactNode; title: string; detail: string }) { return <div className="empty-state"><div className="empty-icon">{icon}</div><b>{title}</b><p>{detail}</p></div> }
export default App
