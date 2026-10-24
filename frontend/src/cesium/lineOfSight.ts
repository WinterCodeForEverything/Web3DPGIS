// Line-of-sight queries against the 3D scene (model and globe).
import * as Cesium from 'cesium'

/** Raise a surface point by `metres` along the local vertical. */
export function raiseAboveSurface( p: Cesium.Cartesian3, metres: number ): Cesium.Cartesian3 {
	const up = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal( p )
	return Cesium.Cartesian3.add( p, Cesium.Cartesian3.multiplyByScalar( up, metres, new Cesium.Cartesian3() ), new Cesium.Cartesian3() )
}

/** First surface hit along origin→direction, or undefined when the ray hits nothing. */
export function firstHit( scene: Cesium.Scene, origin: Cesium.Cartesian3, direction: Cesium.Cartesian3, exclude: object[] = [] ): Cesium.Cartesian3 | undefined {
	const ray = new Cesium.Ray( origin, Cesium.Cartesian3.normalize( direction, new Cesium.Cartesian3() ) )
	const hit = ( scene as unknown as { pickFromRay( ray: Cesium.Ray, exclude?: object[] ): { position?: Cesium.Cartesian3 } | undefined } ).pickFromRay( ray, exclude )
	const position = hit?.position ?? scene.globe.pick( ray, scene )
	return position && Cesium.defined( position ) ? position : undefined
}

export interface SightResult {
	visible: boolean
	/** where the view is blocked, when it is */
	obstacle?: Cesium.Cartesian3
}

/** Can `from` see `to`? Blocked when something is hit more than `tolerance` metres before the target. */
export function lineOfSight( scene: Cesium.Scene, from: Cesium.Cartesian3, to: Cesium.Cartesian3, exclude: object[] = [], tolerance = 0.5 ): SightResult {
	const direction = Cesium.Cartesian3.subtract( to, from, new Cesium.Cartesian3() )
	const total = Cesium.Cartesian3.magnitude( direction )
	const hit = firstHit( scene, from, direction, exclude )
	if ( !hit ) return { visible: true }
	const atDistance = Cesium.Cartesian3.distance( from, hit )
	return atDistance < total - tolerance ? { visible: false, obstacle: hit } : { visible: true }
}
