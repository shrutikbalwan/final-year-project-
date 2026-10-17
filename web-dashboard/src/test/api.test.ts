import { describe, expect, it, vi } from 'vitest'
import { ApiClient, ApiError } from '../api'

describe('ApiClient', () => {
  it('identifies expired authentication sessions', async () => {
    const client = new ApiClient('http://api.test', vi.fn().mockResolvedValue(new Response('', { status: 401 })))
    await expect(client.health()).rejects.toMatchObject({ kind: 'expired', status: 401 })
  })

  it('rejects invalid JSON and contract shapes', async () => {
    const malformedJson = new ApiClient('http://api.test', vi.fn().mockResolvedValue(new Response('not json', { status: 200 })))
    await expect(malformedJson.health()).rejects.toMatchObject({ kind: 'invalid_response' })
    const invalidShape = new ApiClient('http://api.test', vi.fn().mockResolvedValue(Response.json({ status: 'ok' })))
    await expect(invalidShape.health()).rejects.toBeInstanceOf(ApiError)
  })

  it('maps a failed fetch to a network error', async () => {
    const client = new ApiClient('http://api.test', vi.fn().mockRejectedValue(new TypeError('offline')))
    await expect(client.health()).rejects.toMatchObject({ kind: 'network' })
  })

  it('calls the browser fetch function with its required global context', async () => {
    const fetchMock = vi.fn(function (this: typeof globalThis) {
      expect(this).toBe(globalThis)
      return Promise.resolve(Response.json({ status: 'ok', storage: 'ready' }))
    })
    vi.stubGlobal('fetch', fetchMock)
    try {
      await new ApiClient('http://api.test').health()
      expect(fetchMock).toHaveBeenCalledOnce()
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it('sends the signed bearer token only after a successful login', async () => {
    const fetcher = vi.fn()
      .mockResolvedValueOnce(Response.json({ access_token: 'signed-test-token', token_type: 'bearer',
        expires_at: new Date(Date.now() + 60000).toISOString(), user_id: 'viewer-test', role: 'viewer' }))
      .mockResolvedValueOnce(Response.json({ status: 'ok', storage: 'ready' }))
    const client = new ApiClient('http://api.test', fetcher)
    await client.login('viewer-test', 'synthetic-password')
    await client.health()
    expect(fetcher.mock.calls[0][1]?.headers).not.toHaveProperty('Authorization')
    expect(fetcher.mock.calls[1][1]?.headers).toMatchObject({ Authorization: 'Bearer signed-test-token' })
    client.logout()
  })
})
