import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'
import { api, ApiError, type Incident } from '../api'

const now = new Date().toISOString()
const incident: Incident = {
  schema_version: '1.0.0', incident_id: 'incident-synthetic-01', device_id: 'helmet-synthetic-01',
  workplace_id: 'workplace-synthetic-01', status: 'open', severity: 'Warning', risk_score: 20,
  opened_at: now, updated_at: now, reason: 'Synthetic test rule was triggered.',
  source: { telemetry_event_id: 'telemetry-synthetic-01', rule_ids: ['rule-synthetic-01'], reading_ids: ['reading-synthetic-01'] },
  event_ids: [], occurrence_count: 1,
  history: [{ entry_id: 'history-synthetic-01', action: 'created', timestamp: now, note: 'Synthetic test incident.' }],
}

function setupMocks() {
  vi.spyOn(api, 'login').mockImplementation(async username => ({ access_token: 'synthetic-token', token_type: 'bearer',
    expires_at: new Date(Date.now() + 60000).toISOString(), user_id: username, role: username === 'viewer-test' ? 'viewer' : username === 'administrator-test' ? 'administrator' : 'supervisor' }))
  vi.spyOn(api, 'health').mockResolvedValue({ status: 'ok', storage: 'ready' })
  vi.spyOn(api, 'helmets').mockResolvedValue({ items: [], limit: 500, offset: 0, total: 0 })
  vi.spyOn(api, 'incidents').mockResolvedValue({ items: [incident], limit: 500, offset: 0, total: 1 })
  vi.spyOn(api, 'events').mockResolvedValue({ items: [], limit: 500, offset: 0, total: 0 })
  vi.spyOn(api, 'profiles').mockResolvedValue([])
  vi.spyOn(api, 'incident').mockResolvedValue(incident)
  vi.spyOn(api, 'incidentHistory').mockResolvedValue(incident.history)
  vi.spyOn(api, 'acknowledgeIncident').mockResolvedValue({ ...incident, status: 'acknowledged' })
}

async function signIn(role: 'supervisor' | 'viewer' = 'supervisor') {
  render(<App />)
  fireEvent.change(screen.getByLabelText('Username'), { target: { value: role === 'viewer' ? 'viewer-test' : 'supervisor-test' } })
  fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'synthetic-password' } })
  await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
}

describe('dashboard interactions', () => {
  beforeEach(() => {
    setupMocks()
  })
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllEnvs() })

  it('shows an explicitly development-only sign-in and then live empty states', async () => {
    await signIn()
    expect(await screen.findByText(/Authenticated local session/i)).toBeInTheDocument()
    expect(await screen.findByText('No helmets registered')).toBeInTheDocument()
    expect(screen.getByText('Unknown status')).toBeInTheDocument()
  })

  it('opens current sensor readings and the API rule explanation for a helmet', async () => {
    const reading = { reading_id: 'reading-synthetic-temp', sensor_id: 'sensor-synthetic-temp', measurement_type: 'temperature', unit_code: 'Cel', value: 28.5, reading_status: 'valid' as const, observed_at: now }
    const helmet = {
      helmet_id: 'helmet-synthetic-current', workplace_id: 'workplace-synthetic-current', last_telemetry_at: now,
      connectivity_status: 'connected' as const,
      battery_reading: { ...reading, reading_id: 'battery-synthetic', measurement_type: 'battery_charge', unit_code: '%', value: 86 },
      last_seen_at: now, last_seen_status: 'valid' as const,
    }
    vi.mocked(api.helmets).mockResolvedValue({ items: [helmet], limit: 500, offset: 0, total: 1 })
    vi.spyOn(api, 'risk').mockResolvedValue({
      device_id: helmet.helmet_id, workplace_id: helmet.workplace_id, telemetry_event_id: 'telemetry-synthetic', evaluated_at: now,
      risk_level: 'Warning', score: 10, reasons: ['Synthetic configured rule matched.'], matched_rule_ids: ['rule-synthetic'],
      source_reading_ids: [reading.reading_id], quality_issue_codes: [],
    })
    vi.spyOn(api, 'helmet').mockResolvedValue({ ...helmet, latest_telemetry: {
      schema_version: '1.0.0', event_id: 'telemetry-synthetic', device_id: helmet.helmet_id,
      workplace_id: helmet.workplace_id, observed_at: now, received_at: now, readings: [reading],
      health: { schema_version: '1.0.0', device_id: helmet.helmet_id, workplace_id: helmet.workplace_id,
        observed_at: now, battery_reading: helmet.battery_reading, connectivity_status: 'connected',
        last_seen_at: now, last_seen_status: 'valid' },
    } })
    await signIn()
    await userEvent.click(await screen.findByRole('button', { name: /helmet-synthetic-current/ }))
    expect(await screen.findByText('28.5 Cel')).toBeInTheDocument()
    expect(screen.getByText('Synthetic configured rule matched.')).toBeInTheDocument()
    expect(await screen.findAllByText('Warning')).not.toHaveLength(0)
  })

  it('shows a recoverable API network failure', async () => {
    vi.mocked(api.helmets).mockRejectedValueOnce(new ApiError('offline', 'network'))
    await signIn()
    expect(await screen.findByRole('alert')).toHaveTextContent(/Cannot reach the local API/)
    expect(screen.getByRole('button', { name: 'Retry' })).toBeInTheDocument()
  })

  it('opens incident history and lets an authenticated supervisor acknowledge', async () => {
    await signIn('supervisor')
    await userEvent.click(await screen.findByRole('button', { name: /Incidents/ }))
    await userEvent.click(await screen.findByText('Synthetic test rule was triggered.'))
    expect(await screen.findByText('Incident source')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Acknowledge incident' }))
    await waitFor(() => expect(api.acknowledgeIncident).toHaveBeenCalledWith(incident.incident_id, 'supervisor-test'))
  })

  it('hides acknowledgement from the viewer UI role', async () => {
    await signIn('viewer')
    await userEvent.click(await screen.findByRole('button', { name: /Incidents/ }))
    await userEvent.click(await screen.findByText('Synthetic test rule was triggered.'))
    expect(await screen.findByText(/Viewer accounts are not permitted to acknowledge/)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Acknowledge incident/i })).not.toBeInTheDocument()
    expect(api.acknowledgeIncident).not.toHaveBeenCalled()
  })
})
