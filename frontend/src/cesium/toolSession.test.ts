import { describe, expect, it, vi } from 'vitest'
import type * as Cesium from 'cesium'
import { ToolSession, type SessionHost } from './toolSession'

function fakeHost() {
	const primitives = new Set<unknown>()
	const dataSources = new Set<unknown>()
	const host: SessionHost = {
		scene: {
			canvas: document.createElement( 'canvas' ),
			primitives: { add: p => ( primitives.add( p ), p ), remove: p => primitives.delete( p ) },
			requestRender: vi.fn(),
		},
		dataSources: { add: async ds => ( dataSources.add( ds ), ds ), remove: ds => dataSources.delete( ds ) },
	}
	return { host, primitives, dataSources }
}

function fakeHandler() {
	let destroyed = false
	return { destroy: vi.fn( () => { destroyed = true } ), isDestroyed: () => destroyed } as unknown as Cesium.ScreenSpaceEventHandler
}

describe( 'ToolSession', () => {
	it( 'destroys handlers, primitives, entities and its data source', () => {
		const { host, primitives, dataSources } = fakeHost()
		const handlers: Cesium.ScreenSpaceEventHandler[] = []
		const session = new ToolSession( host, 'measure', () => { const h = fakeHandler(); handlers.push( h ); return h } )
		session.handler()
		session.handler()
		session.addPrimitive( { kind: 'frustum' } )
		session.entities.add( { name: 'point' } )
		const cleanup = vi.fn()
		session.onDestroy( cleanup )
		expect( dataSources.size ).toBe( 1 )

		session.destroy()

		expect( handlers.every( h => h.isDestroyed() ) ).toBe( true )
		expect( primitives.size ).toBe( 0 )
		expect( session.entities.values.length ).toBe( 0 )
		expect( dataSources.size ).toBe( 0 )
		expect( cleanup ).toHaveBeenCalledOnce()
		expect( session.isDestroyed ).toBe( true )
	} )

	it( 'is safe to destroy twice and refuses new handlers afterwards', () => {
		const { host } = fakeHost()
		const session = new ToolSession( host, 'x', fakeHandler )
		session.destroy()
		session.destroy()
		expect( () => session.handler() ).toThrow( /destroyed/ )
	} )

	it( 'clear() removes drawings but keeps handlers alive', () => {
		const { host, primitives } = fakeHost()
		const session = new ToolSession( host, 'x', fakeHandler )
		const handler = session.handler()
		session.addPrimitive( {} )
		session.entities.add( {} )
		session.clear()
		expect( primitives.size ).toBe( 0 )
		expect( session.entities.values.length ).toBe( 0 )
		expect( handler.isDestroyed() ).toBe( false )
	} )
} )
