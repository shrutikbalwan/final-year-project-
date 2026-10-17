import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import App from '../App'

const apiUrl = import.meta.env.VITE_LIVE_API_URL as string | undefined

describe.skipIf(!apiUrl)('live telemetry-to-dashboard workflow', () => {
  afterEach(() => {
    cleanup()
    vi.unstubAllEnvs()
  })

  it('posts synthetic telemetry to FastAPI and renders its risk and incident from live API reads', async () => {
    const deviceId = `synthetic-dashboard-${Date.now()}`
    const workplaceId = 'synthetic-dashboard-workplace'
    const eventId = `${deviceId}-telemetry`
    const now = new Date().toISOString()
    const payload = {
      schema_version: '1.0.0', event_id: eventId, device_id: deviceId, workplace_id: workplaceId,
      observed_at: now,
      readings: [{ reading_id: `${eventId}-temperature`, sensor_id: 'synthetic-temp-sensor',
        measurement_type: 'temperature', unit_code: 'Cel', value: 40, reading_status: 'valid', observed_at: now }],
      health: {
        schema_version: '1.0.0', device_id: deviceId, workplace_id: workplaceId, observed_at: now,
        battery_reading: { reading_id: `${eventId}-battery`, sensor_id: 'synthetic-battery-sensor',
          measurement_type: 'battery_charge', unit_code: '%', value: 86, reading_status: 'valid', observed_at: now },
        connectivity_status: 'connected', last_seen_at: now, last_seen_status: 'valid',
      },
    }

    const login = await fetch(`${apiUrl}/api/v1/auth/login`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'synthetic-supervisor', password: 'synthetic-e2e-password-2026' }) })
    const token = (await login.json()).access_token as string
    const sent = await fetch(`${apiUrl}/api/v1/telemetry`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(payload),
    })
    expect(sent.status, await sent.text()).toBe(201)

    render(<App />)
    fireEvent.change(screen.getByLabelText('Username'), { target: { value: 'synthetic-supervisor' } })
    fireEvent.change(screen.getByLabelText('Password'), { target: { value: 'synthetic-e2e-password-2026' } })
    await userEvent.click(screen.getByRole('button', { name: /sign in/i }))
    expect(await screen.findByText('API online')).toBeInTheDocument()
    expect((await screen.findAllByText(deviceId)).length).toBeGreaterThan(0)
    expect((await screen.findAllByText('Critical', { selector: '.risk-badge' })).length).toBeGreaterThan(0)
    expect((await screen.findAllByText(/Synthetic dashboard temperature rule matched/)).length).toBeGreaterThan(0)

    // Also open the incident list and verify the live incident row is present.
    await userEvent.click(screen.getByRole('button', { name: /Incidents/ }))
    expect((await screen.findAllByText(/Synthetic dashboard temperature rule matched/)).length).toBeGreaterThan(0)
  }, 20_000)
})
