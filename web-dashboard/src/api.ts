import { z } from 'zod'

const utcDate = z.string().datetime({ offset: true })
const riskLevel = z.enum(['Normal', 'Advisory', 'Warning', 'Critical', 'Unknown'])
const sensorReading = z.object({
  reading_id: z.string(), sensor_id: z.string(), measurement_type: z.string(), unit_code: z.string(),
  value: z.number().nullable(), reading_status: z.enum(['valid', 'missing', 'stale', 'invalid']), observed_at: utcDate,
})
const health = z.object({
  schema_version: z.string(), device_id: z.string(), workplace_id: z.string(), observed_at: utcDate,
  battery_reading: sensorReading, connectivity_status: z.enum(['connected', 'disconnected', 'intermittent', 'unknown']),
  last_seen_at: utcDate.nullable(), last_seen_status: z.enum(['valid', 'stale', 'missing']),
})
const telemetry = z.object({
  schema_version: z.string(), event_id: z.string(), device_id: z.string(), workplace_id: z.string(),
  observed_at: utcDate, received_at: utcDate, readings: z.array(sensorReading), health,
})
export const helmetSummarySchema = z.object({
  helmet_id: z.string(), workplace_id: z.string(), last_telemetry_at: utcDate,
  connectivity_status: z.enum(['connected', 'disconnected', 'intermittent', 'unknown']), battery_reading: sensorReading,
  last_seen_at: utcDate.nullable(), last_seen_status: z.enum(['valid', 'stale', 'missing']),
})
export const helmetDetailSchema = helmetSummarySchema.extend({ latest_telemetry: telemetry })
export const incidentSchema = z.object({
  schema_version: z.string(), incident_id: z.string(), device_id: z.string(), workplace_id: z.string(),
  status: z.enum(['open', 'acknowledged', 'resolved', 'closed']), severity: riskLevel,
  risk_score: z.number(), opened_at: utcDate, updated_at: utcDate, reason: z.string(),
  source: z.object({ telemetry_event_id: z.string(), rule_ids: z.array(z.string()), reading_ids: z.array(z.string()) }),
  event_ids: z.array(z.string()), occurrence_count: z.number(),
  history: z.array(z.object({ entry_id: z.string(), action: z.string(), timestamp: utcDate,
    actor: z.string().nullable().optional(), target: z.string().nullable().optional(), note: z.string().nullable().optional() })),
  acknowledged_at: utcDate.nullable().optional(), acknowledged_by: z.string().nullable().optional(),
})
export const safetyEventSchema = z.object({
  schema_version: z.string(), event_id: z.string(), incident_id: z.string().nullable().optional(),
  device_id: z.string(), workplace_id: z.string(), event_type: z.string(), severity: riskLevel,
  occurred_at: utcDate, reported_at: utcDate, description: z.string(), related_reading_ids: z.array(z.string()),
})
export const riskSchema = z.object({
  device_id: z.string(), workplace_id: z.string(), telemetry_event_id: z.string(), evaluated_at: utcDate,
  risk_level: riskLevel, score: z.number(), reasons: z.array(z.string()), matched_rule_ids: z.array(z.string()),
  source_reading_ids: z.array(z.string()), quality_issue_codes: z.array(z.string()),
})
export const profileSchema = z.object({
  workplace_id: z.string(), profile_name: z.string(), max_telemetry_age_seconds: z.number(),
  max_reading_age_seconds: z.number(), required_measurements: z.array(z.string()),
  score_bands: z.object({ advisory: z.number(), warning: z.number(), critical: z.number() }),
  rules: z.array(z.object({ rule_id: z.string(), measurement_type: z.string(), unit_code: z.string(),
    operator: z.enum(['gt', 'gte', 'lt', 'lte']), threshold: z.number(), weight: z.number(),
    risk_level: z.enum(['Unknown', 'Advisory', 'Warning', 'Critical']), reason: z.string() })),
  escalation_steps: z.array(z.object({ minimum_risk_level: z.string(), after_seconds: z.number(), target: z.string(), repeat_every_seconds: z.number().nullable().optional() })),
})
const page = <T extends z.ZodTypeAny>(item: T) => z.object({ items: z.array(item), limit: z.number(), offset: z.number(), total: z.number() })

export type HelmetSummary = z.infer<typeof helmetSummarySchema>
export type HelmetDetail = z.infer<typeof helmetDetailSchema>
export type Incident = z.infer<typeof incidentSchema>
export type SafetyEvent = z.infer<typeof safetyEventSchema>
export type RiskEvaluation = z.infer<typeof riskSchema>
export type WorkplaceProfile = z.infer<typeof profileSchema>
export type Telemetry = z.infer<typeof telemetry>

export class ApiError extends Error {
  constructor(message: string, readonly kind: 'network' | 'expired' | 'forbidden' | 'http' | 'invalid_response', readonly status?: number) {
    super(message)
    this.name = 'ApiError'
  }
}

export class ApiClient {
  private readonly baseUrl: string
  private accessToken: string | null = null
  private unauthorizedHandler?: () => void

  constructor(baseUrl = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000', private readonly fetcher: typeof fetch = globalThis.fetch.bind(globalThis)) {
    this.baseUrl = baseUrl.replace(/\/$/, '')
  }

  private async request<T>(path: string, schema: z.ZodType<T>, init?: RequestInit): Promise<T> {
    let response: Response
    try {
      response = await this.fetcher(`${this.baseUrl}${path}`, {
        ...init,
        headers: { Accept: 'application/json', ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
          ...(this.accessToken ? { Authorization: `Bearer ${this.accessToken}` } : {}), ...init?.headers },
      })
    } catch (error) {
      throw new ApiError(error instanceof Error ? error.message : 'Network request failed', 'network')
    }
    if (response.status === 401) { this.accessToken = null; this.unauthorizedHandler?.(); throw new ApiError('Your sign-in session has expired. Sign in again.', 'expired', 401) }
    if (response.status === 403) throw new ApiError('You are not authorized to perform this action.', 'forbidden', 403)
    if (!response.ok) throw new ApiError(`API request failed (${response.status})`, 'http', response.status)
    let payload: unknown
    try { payload = await response.json() } catch { throw new ApiError('The API returned invalid JSON.', 'invalid_response', response.status) }
    const parsed = schema.safeParse(payload)
    if (!parsed.success) throw new ApiError('The API response did not match the expected contract.', 'invalid_response', response.status)
    return parsed.data
  }

  health() { return this.request('/health', z.object({ status: z.string(), storage: z.string() })) }
  async login(username: string, password: string) {
    const schema = z.object({ access_token: z.string(), token_type: z.literal('bearer'), expires_at: utcDate,
      user_id: z.string(), role: z.enum(['administrator', 'supervisor', 'viewer']) })
    const result = await this.request('/api/v1/auth/login', schema, { method: 'POST', body: JSON.stringify({ username, password }) })
    this.accessToken = result.access_token
    return result
  }
  logout() { this.accessToken = null }
  setUnauthorizedHandler(handler?: () => void) { this.unauthorizedHandler = handler }
  helmets(limit = 500) { return this.request('/api/v1/helmets?limit=' + limit, page(helmetSummarySchema)) }
  helmet(id: string) { return this.request(`/api/v1/helmets/${encodeURIComponent(id)}`, helmetDetailSchema) }
  risk(id: string) { return this.request(`/api/v1/helmets/${encodeURIComponent(id)}/risk`, riskSchema) }
  incidents(limit = 500) { return this.request('/api/v1/incidents?limit=' + limit, page(incidentSchema)) }
  incident(id: string) { return this.request(`/api/v1/incidents/${encodeURIComponent(id)}`, incidentSchema) }
  incidentHistory(id: string) {
    return this.request(`/api/v1/incidents/${encodeURIComponent(id)}/history`, z.array(incidentSchema.shape.history.element))
  }
  acknowledgeIncident(id: string, acknowledgedBy: string) {
    return this.request(`/api/v1/incidents/${encodeURIComponent(id)}/acknowledge`, incidentSchema,
      { method: 'POST', body: JSON.stringify({ acknowledged_by: acknowledgedBy }) })
  }
  events(params = '') { return this.request(`/api/v1/events?limit=500${params}`, page(safetyEventSchema)) }
  telemetry(params = '') { return this.request(`/api/v1/telemetry?limit=500${params}`, page(telemetry)) }
  profiles() { return this.request('/api/v1/workplaces/profiles', z.array(profileSchema)) }
}

export const api = new ApiClient()
