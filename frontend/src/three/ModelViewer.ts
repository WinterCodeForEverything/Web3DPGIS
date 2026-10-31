// A plain three.js viewer for a model's 3D Tiles: orbit around the model, no globe or GIS tools.
// It can still convert between scene points and longitude/latitude/height, so shared features such as labels work here.
import { TilesRenderer } from '3d-tiles-renderer'
import { GLTFExtensionsPlugin, ImplicitTilingPlugin, ReorientationPlugin } from '3d-tiles-renderer/plugins'
import {
	Box3, Color, DirectionalLight, GridHelper, Group, HemisphereLight, Material, Matrix4, Mesh, NeutralToneMapping, PerspectiveCamera,
	PMREMGenerator, Raycaster, Scene, Sphere, Vector2, Vector3, WebGLRenderer, type Object3D,
} from 'three'
import type { GeoPoint } from '@/api/types'
import type { Vec3 } from '@/geo/geometry'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { RoomEnvironment } from 'three/examples/jsm/environments/RoomEnvironment.js'
import { CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { DRACOLoader } from 'three/examples/jsm/loaders/DRACOLoader.js'
import { MeshoptDecoder } from 'three/examples/jsm/libs/meshopt_decoder.module.js'

export interface ModelViewerOptions {
	/** Lift the model by this many metres, as the map viewer does with the model's height offset. */
	heightOffset?: number
	onProgress?: ( fraction: number ) => void
	onReady?: () => void
	onError?: ( message: string ) => void
}

// viewing direction for the initial and reset views: from the south-east, looking slightly down
const VIEW_DIRECTION = new Vector3( 1, 0.7, 1 ).normalize()
// a pointer that moves further than this between press and release was dragging the camera, not clicking
const CLICK_TOLERANCE_PX = 4
const DEG = 180 / Math.PI
const FLIGHT_MS = 600

export class ModelViewer {
	readonly renderer: WebGLRenderer
	readonly scene = new Scene()
	readonly camera = new PerspectiveCamera( 45, 1, 0.1, 1000 )
	readonly controls: OrbitControls
	readonly tiles: TilesRenderer
	/** HTML overlay: CSS2DObjects added to the scene are drawn here, on top of the model. */
	readonly overlay = new CSS2DRenderer()
	/** Resolves once the tileset has been moved into the scene, i.e. when geoToLocal() and localToGeo() work. */
	readonly placed: Promise<void>
	private markPlaced!: () => void
	private readonly anchor = new Group()
	private readonly grid: GridHelper
	private readonly bounds = new Sphere()
	private readonly resizeObserver: ResizeObserver
	private readonly environment: ReturnType<PMREMGenerator['fromScene']>
	private frame = 0
	private dirty = true
	private fitted = false
	private watchdog = 0
	private wireframe = false
	/** A camera move in progress (see focusOn), eased over FLIGHT_MS. */
	private flight: { from: Vector3; to: Vector3; fromTarget: Vector3; toTarget: Vector3; start: number } | null = null

	constructor( private readonly container: HTMLElement, url: string, private readonly events: ModelViewerOptions = {} ) {
		this.placed = new Promise( resolve => { this.markPlaced = resolve } )
		this.renderer = new WebGLRenderer( { antialias: true, logarithmicDepthBuffer: true } )
		this.renderer.setPixelRatio( window.devicePixelRatio )
		this.renderer.toneMapping = NeutralToneMapping
		container.appendChild( this.renderer.domElement )
		Object.assign( this.overlay.domElement.style, { position: 'absolute', inset: '0', pointerEvents: 'none' } )
		container.appendChild( this.overlay.domElement )

		this.scene.background = new Color( 0x2a2f38 )
		const pmrem = new PMREMGenerator( this.renderer )
		this.environment = pmrem.fromScene( new RoomEnvironment(), 0.04 )
		pmrem.dispose()
		this.scene.environment = this.environment.texture
		this.scene.add( new HemisphereLight( 0xffffff, 0x444444, 0.6 ) )
		const sun = new DirectionalLight( 0xffffff, 1.2 )
		sun.position.set( 1, 2, 1.5 )
		this.scene.add( sun )

		this.grid = new GridHelper( 1, 20, 0x8892a6, 0x4a5262 )
		this.grid.visible = false
		this.scene.add( this.grid )

		this.controls = new OrbitControls( this.camera, this.renderer.domElement )
		this.controls.enableDamping = true
		this.controls.addEventListener( 'change', this.invalidate )

		this.tiles = new TilesRenderer( url )
		// georeferenced tilesets sit thousands of km from the origin: move the model to it, with up as +Y
		this.tiles.registerPlugin( new ReorientationPlugin( { recenter: true } ) )
		const dracoLoader = new DRACOLoader().setDecoderPath( `${import.meta.env.BASE_URL}draco/` )
		this.tiles.registerPlugin( new ImplicitTilingPlugin() )
		this.tiles.registerPlugin( new GLTFExtensionsPlugin( { dracoLoader, meshoptDecoder: MeshoptDecoder } ) )
		this.tiles.setCamera( this.camera )
		this.tiles.addEventListener( 'load-root-tileset', this.onRootLoaded )
		this.tiles.addEventListener( 'load-model', this.onModelLoaded )
		this.tiles.addEventListener( 'tiles-load-end', this.onTilesLoaded )
		this.tiles.addEventListener( 'needs-update', this.invalidate )
		this.tiles.addEventListener( 'load-error', this.onLoadError )
		// the tileset sits in an anchor that carries the model's height offset, so the plugin can still move the tileset itself
		this.anchor.position.y = events.heightOffset ?? 0
		this.anchor.add( this.tiles.group )
		this.scene.add( this.anchor )

		this.resizeObserver = new ResizeObserver( this.resize )
		this.resizeObserver.observe( container )
		this.resize()
		this.frame = requestAnimationFrame( this.render )
	}

	/** Frame the whole model again. */
	resetView() {
		const { center, radius } = this.bounds
		if ( radius <= 0 ) return
		const distance = radius / Math.sin( ( this.camera.fov * Math.PI ) / 360 ) * 1.1
		this.camera.near = radius / 1e4
		this.camera.far = radius * 1e3
		this.camera.updateProjectionMatrix()
		this.camera.position.copy( center ).addScaledVector( VIEW_DIRECTION, distance )
		this.controls.target.copy( center )
		this.controls.maxDistance = distance * 20
		this.controls.update()
		this.invalidate()
	}

	/** Move the camera so a sphere around centre fills the middle of the view, looking from the same direction as now. */
	focusOn( centre: Vector3, radius: number ) {
		// a single point has no size: frame a small part of the model around it instead
		const size = Math.max( radius, this.bounds.radius * 0.08, 0.5 )
		const distance = size / Math.sin( ( this.camera.fov * Math.PI ) / 360 ) * 1.5
		const direction = this.camera.position.clone().sub( this.controls.target ).normalize()
		this.flight = {
			from: this.camera.position.clone(), to: centre.clone().addScaledVector( direction, distance ),
			fromTarget: this.controls.target.clone(), toTarget: centre.clone(), start: performance.now(),
		}
		this.invalidate()
	}

	setAutoRotate( on: boolean ) {
		this.controls.autoRotate = on
		this.invalidate()
	}

	setGrid( on: boolean ) {
		this.grid.visible = on
		this.invalidate()
	}

	setWireframe( on: boolean ) {
		this.wireframe = on
		this.tiles.group.traverse( object => this.applyWireframe( object ) )
		this.invalidate()
	}

	requestRender() {
		this.dirty = true
	}

	// Scene points and Earth-centred (ECEF) points convert through the tileset's own placement, without the anchor:
	// the map viewer stores points on the model as raised by its height offset, and the anchor raises the model by the same amount.

	/** The scene point of an Earth-centred (ECEF) point. */
	ecefToLocal( v: Vec3 ): Vector3 {
		this.tiles.group.updateMatrix()
		return new Vector3( ...v ).applyMatrix4( this.tiles.group.matrix )
	}

	/** The Earth-centred (ECEF) point of a scene point. */
	localToEcef( v: Vector3 ): Vec3 {
		this.tiles.group.updateMatrix()
		return v.clone().applyMatrix4( new Matrix4().copy( this.tiles.group.matrix ).invert() ).toArray() as Vec3
	}

	/** The scene point at a longitude/latitude/height. */
	geoToLocal( p: GeoPoint ): Vector3 {
		const ecef = this.tiles.ellipsoid.getCartographicToPosition( p.latitude / DEG, p.longitude / DEG, p.height ?? 0, new Vector3() )
		return this.ecefToLocal( ecef.toArray() as Vec3 )
	}

	/** The longitude/latitude/height of a scene point. */
	localToGeo( v: Vector3 ): GeoPoint {
		const { lat, lon, height } = this.tiles.ellipsoid.getPositionToCartographic( new Vector3( ...this.localToEcef( v ) ), {} )
		return { longitude: lon * DEG, latitude: lat * DEG, height }
	}

	/** The point on the model under a pointer event, if the model is there. */
	pick( event: { clientX: number; clientY: number } ): Vector3 | null {
		const rect = this.renderer.domElement.getBoundingClientRect()
		const ndc = new Vector2( ( event.clientX - rect.left ) / rect.width * 2 - 1, -( ( event.clientY - rect.top ) / rect.height ) * 2 + 1 )
		const raycaster = new Raycaster()
		raycaster.setFromCamera( ndc, this.camera )
		return raycaster.intersectObject( this.tiles.group, true )[0]?.point ?? null
	}

	/**
	 * Call fn for clicks on the canvas with a mouse button (0 left, 2 right), ignoring drags that move the camera.
	 * Returns a function that stops listening.
	 */
	onClick( fn: ( event: PointerEvent ) => void, button = 0 ): () => void {
		const canvas = this.renderer.domElement
		let down: { x: number; y: number } | null = null
		const press = ( e: PointerEvent ) => { down = e.button === button ? { x: e.clientX, y: e.clientY } : null }
		const release = ( e: PointerEvent ) => {
			if ( down && e.button === button && Math.hypot( e.clientX - down.x, e.clientY - down.y ) <= CLICK_TOLERANCE_PX ) fn( e )
			down = null
		}
		canvas.addEventListener( 'pointerdown', press )
		canvas.addEventListener( 'pointerup', release )
		return () => {
			canvas.removeEventListener( 'pointerdown', press )
			canvas.removeEventListener( 'pointerup', release )
		}
	}

	/** Call fn as the pointer moves over the canvas, at most once a frame. Returns a function that stops listening. */
	onPointerMove( fn: ( event: PointerEvent ) => void ): () => void {
		const canvas = this.renderer.domElement
		let latest: PointerEvent | null = null, frame = 0
		const move = ( e: PointerEvent ) => {
			latest = e
			frame ||= requestAnimationFrame( () => { frame = 0; if ( latest ) fn( latest ) } )
		}
		canvas.addEventListener( 'pointermove', move )
		return () => {
			canvas.removeEventListener( 'pointermove', move )
			cancelAnimationFrame( frame )
		}
	}

	dispose() {
		cancelAnimationFrame( this.frame )
		window.clearInterval( this.watchdog )
		this.resizeObserver.disconnect()
		this.controls.dispose()
		this.tiles.dispose()
		this.environment.dispose()
		this.renderer.dispose()
		this.renderer.domElement.remove()
		this.overlay.domElement.remove()
	}

	private invalidate = () => { this.dirty = true }

	private resize = () => {
		const { clientWidth: width, clientHeight: height } = this.container
		if ( !width || !height ) return
		this.renderer.setSize( width, height )
		this.overlay.setSize( width, height )
		this.camera.aspect = width / height
		this.camera.updateProjectionMatrix()
		this.tiles.setResolutionFromRenderer( this.camera, this.renderer )
		this.invalidate()
	}

	private render = () => {
		this.frame = requestAnimationFrame( this.render )
		// damping and auto-rotation keep moving the camera after the pointer stops
		if ( this.flight ) this.fly()
		const moved = this.controls.update()
		if ( !moved && !this.dirty ) return
		this.dirty = false
		this.camera.updateMatrixWorld()
		this.tiles.update()
		this.renderer.render( this.scene, this.camera )
		this.overlay.render( this.scene, this.camera )
		this.events.onProgress?.( this.tiles.loadProgress )
	}

	private fly() {
		const f = this.flight!
		const t = Math.min( ( performance.now() - f.start ) / FLIGHT_MS, 1 )
		const eased = t * t * ( 3 - 2 * t )
		this.camera.position.lerpVectors( f.from, f.to, eased )
		this.controls.target.lerpVectors( f.fromTarget, f.toTarget, eased )
		if ( t === 1 ) this.flight = null
		this.dirty = true
	}

	private onRootLoaded = () => {
		// the reorientation plugin has moved the group by now; its bounding sphere gives a first view
		this.anchor.updateMatrixWorld( true )
		this.markPlaced()
		if ( this.tiles.getBoundingSphere( this.bounds ) ) {
			this.bounds.applyMatrix4( this.tiles.group.matrixWorld )
			this.resetView()
		}
		// some tilesets (e.g. 3D Tiles 1.1 multiple contents) load nothing here and never report tiles-load-end
		let idleChecks = 0
		this.watchdog = window.setInterval( () => {
			if ( this.fitted ) return window.clearInterval( this.watchdog )
			idleChecks = this.tiles.loadProgress === 1 && this.tiles.group.children.length === 0 ? idleChecks + 1 : 0
			if ( idleChecks < 3 ) return
			window.clearInterval( this.watchdog )
			this.events.onError?.( 'this tileset has no content the 3D model viewer can show. Try the Map (GIS) viewer.' )
		}, 2000 )
	}

	private onModelLoaded = ( { scene }: { scene: Object3D } ) => {
		if ( this.wireframe ) scene.traverse( object => this.applyWireframe( object ) )
	}

	private onTilesLoaded = () => {
		this.events.onProgress?.( 1 )
		if ( this.fitted ) return
		// the loaded geometry is tighter than the tileset's bounding volume: frame it and put the grid under it
		const box = new Box3().setFromObject( this.tiles.group )
		if ( box.isEmpty() ) return
		this.fitted = true
		box.getBoundingSphere( this.bounds )
		const size = box.getSize( new Vector3() )
		const span = Math.max( size.x, size.z ) * 2
		this.grid.scale.setScalar( span )
		this.grid.position.set( this.bounds.center.x, box.min.y, this.bounds.center.z )
		this.resetView()
		this.events.onReady?.()
	}

	private onLoadError = ( { tile, error }: { tile: unknown; error: Error } ) => {
		// a missing child tile only leaves a gap; without the root tileset there is nothing to show
		if ( tile === null ) this.events.onError?.( error.message )
	}

	private applyWireframe( object: Object3D ) {
		if ( !( object instanceof Mesh ) ) return
		const materials: Material[] = Array.isArray( object.material ) ? object.material : [ object.material ]
		for ( const material of materials ) if ( 'wireframe' in material ) ( material as Material & { wireframe: boolean } ).wireframe = this.wireframe
	}
}
