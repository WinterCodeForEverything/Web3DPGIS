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

/** Longitude, latitude (degrees) and ellipsoidal height (metres) of an ECEF point. */
export function ecefToGeodetic( [ x, y, z ]: Vec3 ): { longitude: number; latitude: number; height: number } {
	const b = A * Math.sqrt( 1 - E2 ), ep2 = ( A * A - b * b ) / ( b * b )
	const lon = Math.atan2( y, x ), p = Math.hypot( x, y )
	if ( p < 1e-9 ) return { longitude: lon * 180 / Math.PI, latitude: Math.sign( z ) * 90, height: Math.abs( z ) - b }
	// Bowring's initial guess, then a few fixed-point iterations (converges to < 1 mm)
	const theta = Math.atan2( z * A, p * b )
	let lat = Math.atan2( z + ep2 * b * Math.sin( theta ) ** 3, p - E2 * A * Math.cos( theta ) ** 3 )
	let n = 0, h = 0
	for ( let i = 0; i < 5; i++ ) {
		n = A / Math.sqrt( 1 - E2 * Math.sin( lat ) ** 2 )
		h = p / Math.cos( lat ) - n
		lat = Math.atan2( z, p * ( 1 - E2 * n / ( n + h ) ) )
	}
	n = A / Math.sqrt( 1 - E2 * Math.sin( lat ) ** 2 )
	return { longitude: lon * 180 / Math.PI, latitude: lat * 180 / Math.PI, height: p / Math.cos( lat ) - n }
}

export const midpoint = ( a: Vec3, b: Vec3 ): Vec3 => [ ( a[0] + b[0] ) / 2, ( a[1] + b[1] ) / 2, ( a[2] + b[2] ) / 2 ]

/** Centre of the box around some points. */
export function boundsCentre( points: Vec3[] ): Vec3 {
	return [ 0, 1, 2 ].map( i => {
		const values = points.map( p => p[i] )
		return ( Math.min( ...values ) + Math.max( ...values ) ) / 2
	} ) as Vec3
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

/** Length in metres of each segment of a polyline, in order. */
export function segmentLengths( points: Vec3[] ): number[] {
	return points.slice( 1 ).map( ( p, i ) => distance( points[i], p ) )
}

/** Total length of a polyline in metres. */
export function polylineLength( points: Vec3[] ): number {
	return segmentLengths( points ).reduce( ( total, l ) => total + l, 0 )
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

/** Points around a horizontal circle, e.g. to draw it as a polygon. */
export function circleRing( centre: Vec3, radius: number, segments = 64 ): Vec3[] {
	const { east, north } = enuBasis( centre )
	return Array.from( { length: segments }, ( _, i ) => {
		const t = 2 * Math.PI * i / segments, e = Math.cos( t ) * radius, n = Math.sin( t ) * radius
		return [ 0, 1, 2 ].map( k => centre[k] + e * east[k] + n * north[k] ) as Vec3
	} )
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
