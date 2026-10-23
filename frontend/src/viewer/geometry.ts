// Measurement maths on Earth-centred (ECEF) points, independent of Cesium so it can be unit-tested.

export type Vec3 = [ number, number, number ]

const A = 6378137.0
const E2 = 6.69437999014e-3

export const sub = ( a: Vec3, b: Vec3 ): Vec3 => [ a[0] - b[0], a[1] - b[1], a[2] - b[2] ]
export const dot = ( a: Vec3, b: Vec3 ) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2]
export const length = ( a: Vec3 ) => Math.sqrt( dot( a, a ) )
export const distance = ( a: Vec3, b: Vec3 ) => length( sub( a, b ) )

export function geodeticToEcef( lonDeg: number, latDeg: number, h = 0 ): Vec3 {
	const lon = lonDeg * Math.PI / 180, lat = latDeg * Math.PI / 180
	const n = A / Math.sqrt( 1 - E2 * Math.sin( lat ) ** 2 )
	return [ ( n + h ) * Math.cos( lat ) * Math.cos( lon ), ( n + h ) * Math.cos( lat ) * Math.sin( lon ), ( n * ( 1 - E2 ) + h ) * Math.sin( lat ) ]
}

/** Geodetic surface normal ("up") at an ECEF point. */
export function upAt( p: Vec3 ): Vec3 {
	// normal of the WGS84 ellipsoid: (x/a², y/a², z/b²), normalised
	const b2 = A * A * ( 1 - E2 )
	const n: Vec3 = [ p[0] / ( A * A ), p[1] / ( A * A ), p[2] / b2 ]
	const len = length( n )
	return [ n[0] / len, n[1] / len, n[2] / len ]
}

/** East, north, up unit vectors at an ECEF point. */
export function enuBasis( p: Vec3 ): { east: Vec3; north: Vec3; up: Vec3 } {
	const up = upAt( p )
	const eastRaw: Vec3 = [ -up[1], up[0], 0 ]
	const el = length( eastRaw ) || 1
	const east: Vec3 = [ eastRaw[0] / el, eastRaw[1] / el, 0 ]
	const north: Vec3 = [ up[1] * east[2] - up[2] * east[1], up[2] * east[0] - up[0] * east[2], up[0] * east[1] - up[1] * east[0] ]
	return { east, north, up }
}

/** Total length of a polyline in metres. */
export function polylineLength( points: Vec3[] ): number {
	let total = 0
	for ( let i = 1; i < points.length; i++ ) total += distance( points[i - 1], points[i] )
	return total
}

/** Area in m² of a polygon, measured flat in the local horizontal plane at its centroid. */
export function polygonArea( points: Vec3[] ): number {
	if ( points.length < 3 ) return 0
	const centroid = points.reduce<Vec3>( ( c, p ) => [ c[0] + p[0] / points.length, c[1] + p[1] / points.length, c[2] + p[2] / points.length ], [ 0, 0, 0 ] )
	const { east, north } = enuBasis( centroid )
	const local = points.map( p => { const d = sub( p, centroid ); return [ dot( d, east ), dot( d, north ) ] } )
	let twice = 0
	for ( let i = 0; i < local.length; i++ ) {
		const [ x1, y1 ] = local[i], [ x2, y2 ] = local[( i + 1 ) % local.length]
		twice += x1 * y2 - x2 * y1
	}
	return Math.abs( twice ) / 2
}

/** True area in m² of a (roughly planar) polygon in 3D, e.g. a wall or a sloping roof (Newell's method). */
export function surfaceArea( points: Vec3[] ): number {
	if ( points.length < 3 ) return 0
	const o = points[0]   // work relative to the first point to keep precision with ECEF magnitudes
	const n: Vec3 = [ 0, 0, 0 ]
	for ( let i = 0; i < points.length; i++ ) {
		const a = sub( points[i], o ), b = sub( points[( i + 1 ) % points.length], o )
		n[0] += ( a[1] - b[1] ) * ( a[2] + b[2] )
		n[1] += ( a[2] - b[2] ) * ( a[0] + b[0] )
		n[2] += ( a[0] - b[0] ) * ( a[1] + b[1] )
	}
	return length( n ) / 2
}

/** Horizontal, vertical and straight-line distance between two points (the "triangle" measurement). */
export function triangle( a: Vec3, b: Vec3 ): { horizontal: number; vertical: number; slant: number } {
	const up = upAt( a )
	const d = sub( b, a )
	const vertical = dot( d, up )
	const slant = length( d )
	return { horizontal: Math.sqrt( Math.max( slant * slant - vertical * vertical, 0 ) ), vertical, slant }
}

/** Area of a horizontal circle with the given centre and a point on its edge. */
export function circle( centre: Vec3, edge: Vec3 ): { radius: number; area: number } {
	const radius = triangle( centre, edge ).horizontal
	return { radius, area: Math.PI * radius * radius }
}

export function formatLength( m: number ): string {
	return Math.abs( m ) >= 1000 ? `${( m / 1000 ).toFixed( 3 )} km` : `${m.toFixed( 2 )} m`
}

export function formatArea( m2: number ): string {
	return m2 >= 1e6 ? `${( m2 / 1e6 ).toFixed( 4 )} km²` : `${m2.toFixed( 2 )} m²`
}
