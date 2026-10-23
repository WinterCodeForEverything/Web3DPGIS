// Viewer setup and helpers shared by all tools.
import * as Cesium from 'cesium'
import type { InjectionKey, ShallowRef } from 'vue'
import type { CameraPose, GeoPoint, Model3D } from '@/api/types'
import type { Vec3 } from './geometry'

export interface ViewerContext {
	viewer: Cesium.Viewer
	tileset: ShallowRef<Cesium.Cesium3DTileset | null>
	model: ShallowRef<Model3D>
	notify: ( message: string, kind?: 'info' | 'error' ) => void
}

export const viewerKey: InjectionKey<ViewerContext> = Symbol( 'viewer' )

export function createViewer( container: HTMLElement, ionToken?: string ): Cesium.Viewer {
	const token = ionToken ?? import.meta.env.VITE_CESIUM_ION_TOKEN
	if ( token ) Cesium.Ion.defaultAccessToken = token
	const viewer = new Cesium.Viewer( container, {
		animation: false,
		timeline: false,
		baseLayerPicker: false,
		geocoder: false,
		homeButton: false,
		sceneModePicker: false,
		infoBox: false,
		selectionIndicator: false,
		navigationHelpButton: true,
		fullscreenButton: true,
		requestRenderMode: true,
		maximumRenderTimeChange: Infinity,
		// offline base map shipped with Cesium, so no ion token is needed
		baseLayer: Cesium.ImageryLayer.fromProviderAsync( Cesium.TileMapServiceImageryProvider.fromUrl( Cesium.buildModuleUrl( 'Assets/Textures/NaturalEarthII' ) ) ),
	} )
	viewer.scene.globe.depthTestAgainstTerrain = true
	viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction( Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK )
	return viewer
}

/** Load a tileset and lift it by heightOffset metres along the local vertical. */
export async function loadTileset( viewer: Cesium.Viewer, url: string, heightOffset: number ): Promise<Cesium.Cesium3DTileset> {
	const tileset = await Cesium.Cesium3DTileset.fromUrl( url )
	viewer.scene.primitives.add( tileset )
	setHeightOffset( tileset, heightOffset )
	await viewer.zoomTo( tileset, new Cesium.HeadingPitchRange( 0, -0.5, tileset.boundingSphere.radius * 2.5 ) )
	return tileset
}

export function setHeightOffset( tileset: Cesium.Cesium3DTileset, offset: number ) {
	const centre = Cesium.Cartographic.fromCartesian( tileset.boundingSphere.center )
	const surface = Cesium.Cartesian3.fromRadians( centre.longitude, centre.latitude, 0 )
	const lifted = Cesium.Cartesian3.fromRadians( centre.longitude, centre.latitude, offset )
	tileset.modelMatrix = Cesium.Matrix4.fromTranslation( Cesium.Cartesian3.subtract( lifted, surface, new Cesium.Cartesian3() ) )
}

/** The 3D point under the cursor: on the model if it was hit, otherwise on the globe. */
export function pickPoint( viewer: Cesium.Viewer, position: Cesium.Cartesian2 ): Cesium.Cartesian3 | undefined {
	const scene = viewer.scene
	if ( scene.pickPositionSupported && Cesium.defined( scene.pick( position ) ) ) {
		const p = scene.pickPosition( position )
		if ( Cesium.defined( p ) ) return p
	}
	const ray = viewer.camera.getPickRay( position )
	return ray ? scene.globe.pick( ray, scene ) : undefined
}

export const toVec3 = ( c: Cesium.Cartesian3 ): Vec3 => [ c.x, c.y, c.z ]

export function toGeoPoint( c: Cesium.Cartesian3 ): GeoPoint {
	const carto = Cesium.Cartographic.fromCartesian( c )
	return { longitude: Cesium.Math.toDegrees( carto.longitude ), latitude: Cesium.Math.toDegrees( carto.latitude ), height: carto.height }
}

export const fromGeoPoint = ( p: GeoPoint ) => Cesium.Cartesian3.fromDegrees( p.longitude, p.latitude, p.height ?? 0 )

export function currentPose( camera: Cesium.Camera ): CameraPose {
	const d = camera.directionWC, u = camera.upWC
	return { position: toGeoPoint( camera.positionWC ), direction: [ d.x, d.y, d.z ], up: [ u.x, u.y, u.z ] }
}

export function poseOrientation( pose: CameraPose ) {
	return { direction: new Cesium.Cartesian3( ...pose.direction ), up: new Cesium.Cartesian3( ...pose.up ) }
}

// Shared drawing helpers so every tool looks the same
export const style = {
	point: { pixelSize: 9, color: Cesium.Color.YELLOW, outlineColor: Cesium.Color.BLACK, outlineWidth: 1, disableDepthTestDistance: Number.POSITIVE_INFINITY },
	line: Cesium.Color.YELLOW,
	fill: Cesium.Color.YELLOW.withAlpha( 0.3 ),
	label: {
		font: '14px sans-serif', fillColor: Cesium.Color.WHITE, outlineColor: Cesium.Color.BLACK, outlineWidth: 3,
		style: Cesium.LabelStyle.FILL_AND_OUTLINE, verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
		pixelOffset: new Cesium.Cartesian2( 0, -12 ), disableDepthTestDistance: Number.POSITIVE_INFINITY,
		showBackground: true, backgroundColor: Cesium.Color.BLACK.withAlpha( 0.6 ),
	},
}
