import { afterEach, describe, expect, it, vi } from 'vitest'
import { postTryOnPayloadWithAck, serializeTryOnPayloadForUrl } from './tryonBridge'

afterEach(() => {
  vi.useRealTimers()
})

describe('try-on locale bridge', () => {
  it('includes locale in URL payload but never includes the user photo', () => {
    const serialized = serializeTryOnPayloadForUrl({
      source: 'down-jacket-recommendation',
      garmentImageUrl: 'https://cdn.example.test/garment.jpg',
      productId: 'p-1',
      productTitle: 'Example',
      locale: 'en',
      userImageDataUrl: 'data:image/jpeg;base64,private-photo',
    })
    const parsed = JSON.parse(serialized)
    expect(parsed.locale).toBe('en')
    expect(parsed.userImageDataUrl).toBeUndefined()
    expect(serialized).not.toContain('private-photo')
  })

  it('sends payload immediately upon DOWN_JACKET_TRYON_READY and stops on DOWN_JACKET_TRYON_ACK', () => {
    vi.useFakeTimers()
    const targetOrigin = 'https://workbench.example.test'
    const fakeWindow = {
      closed: false,
      postMessage: vi.fn(),
    } as unknown as Window

    postTryOnPayloadWithAck(fakeWindow, {
      source: 'down-jacket-recommendation',
      garmentImageUrl: 'https://cdn.example.test/garment.jpg',
      productId: 'p-1',
      productTitle: 'Example',
      locale: 'zh-CN',
      userImageDataUrl: 'data:image/jpeg;base64,photo-data',
    }, targetOrigin)

    expect(fakeWindow.postMessage).not.toHaveBeenCalled()

    window.dispatchEvent(new MessageEvent('message', {
      origin: targetOrigin,
      source: fakeWindow,
      data: { type: 'DOWN_JACKET_TRYON_READY' },
    }))

    expect(fakeWindow.postMessage).toHaveBeenCalledTimes(1)
    expect(fakeWindow.postMessage).toHaveBeenCalledWith(
      expect.objectContaining({
        type: 'DOWN_JACKET_TRYON_INIT',
        payload: expect.objectContaining({ userImageDataUrl: 'data:image/jpeg;base64,photo-data' }),
      }),
      targetOrigin,
    )

    window.dispatchEvent(new MessageEvent('message', {
      origin: targetOrigin,
      source: fakeWindow,
      data: { type: 'DOWN_JACKET_TRYON_ACK' },
    }))

    vi.advanceTimersByTime(60000)
    expect(fakeWindow.postMessage).toHaveBeenCalledTimes(1)
  })
})
