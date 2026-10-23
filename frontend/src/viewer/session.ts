// A ToolSession owns everything one tool adds to the viewer, so switching tools always cleans up.
import * as Cesium from 'cesium'

export interface Destroyable {
	destroy(): void
	isDestroyed?(): boolean
}

export interface SessionHost {
	scene: { canvas: HTMLCanvasElement; primitives: { add<T>( p: T ): T; remove( p: unknown ): boolean }; requestRender(): void }
	dataSources: { add( ds: Cesium.DataSource ): Promise<Cesium.DataSource>; remove( ds: Cesium.DataSource, destroy?: boolean ): boolean }
}

export type HandlerFactory = ( canvas: HTMLCanvasElement ) => Cesium.ScreenSpaceEventHandler

const defaultHandlerFactory: HandlerFactory = canvas => new Cesium.ScreenSpaceEventHandler( canvas )

export class ToolSession {
	readonly entities: Cesium.EntityCollection
	private readonly dataSource: Cesium.CustomDataSource
	private readonly handlers: Cesium.ScreenSpaceEventHandler[] = []
	private readonly primitives: unknown[] = []
	private readonly cleanups: ( () => void )[] = []
	private destroyed = false

	constructor( private readonly host: SessionHost, name: string, private readonly createHandler: HandlerFactory = defaultHandlerFactory ) {
		this.dataSource = new Cesium.CustomDataSource( name )
		this.entities = this.dataSource.entities
		void host.dataSources.add( this.dataSource )
	}

	/** A canvas input handler that is destroyed with the session. */
	handler(): Cesium.ScreenSpaceEventHandler {
		this.assertAlive()
		const handler = this.createHandler( this.host.scene.canvas )
		this.handlers.push( handler )
		return handler
	}

	/** A primitive that is removed from the scene with the session. */
	addPrimitive<T>( primitive: T ): T {
		this.assertAlive()
		this.primitives.push( primitive )
		return this.host.scene.primitives.add( primitive )
	}

	/** Run fn when the session ends (restore camera settings, stop timers, …). */
	onDestroy( fn: () => void ) {
		this.cleanups.push( fn )
	}

	/** Remove drawings but keep the session (and its handlers) running. */
	clear() {
		this.entities.removeAll()
		for ( const p of this.primitives.splice( 0 ) ) this.host.scene.primitives.remove( p )
		this.host.scene.requestRender()
	}

	get isDestroyed() {
		return this.destroyed
	}

	destroy() {
		if ( this.destroyed ) return
		this.destroyed = true
		for ( const h of this.handlers.splice( 0 ) ) if ( !h.isDestroyed() ) h.destroy()
		for ( const fn of this.cleanups.splice( 0 ).reverse() ) fn()
		this.clear()
		this.host.dataSources.remove( this.dataSource, true )
		this.host.scene.requestRender()
	}

	private assertAlive() {
		if ( this.destroyed ) throw new Error( 'ToolSession already destroyed' )
	}
}

/** A session on a real viewer. */
export function createSession( viewer: Cesium.Viewer, name: string ): ToolSession {
	return new ToolSession( viewer as unknown as SessionHost, name )
}
