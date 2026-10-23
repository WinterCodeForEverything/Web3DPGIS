import { describe, expect, it } from 'vitest'
import { circle, enuBasis, formatArea, formatLength, geodeticToEcef, polygonArea, polylineLength, surfaceArea, triangle, type Vec3 } from './geometry'

// Points offset from a base location by metres east / north / up, for exact expectations.
function offset( base: Vec3, e: number, n: number, u: number ): Vec3 {
	const { east, north, up } = enuBasis( base )
	return [ 0, 1, 2 ].map( i => base[i] + e * east[i] + n * north[i] + u * up[i] ) as Vec3
}

const gz = geodeticToEcef( 113.26, 23.13, 10 )

describe( 'geodeticToEcef', () => {
	it( 'matches the WGS84 equator radius', () => {
		expect( geodeticToEcef( 0, 0, 0 ) ).toEqual( [ 6378137, 0, 0 ] )
	} )
	it( 'matches the backend conversion for Guangzhou', () => {
		const [ x, y, z ] = geodeticToEcef( 113.26, 23.13, 20 )
		expect( x ).toBeCloseTo( -2317490.0936, 3 )
		expect( y ).toBeCloseTo( 5391509.5803, 3 )
		expect( z ).toBeCloseTo( 2489973.154, 3 )
	} )
} )

describe( 'measurements', () => {
	it( 'polyline length sums segments', () => {
		expect( polylineLength( [ gz, offset( gz, 30, 0, 0 ), offset( gz, 30, 40, 0 ) ] ) ).toBeCloseTo( 70, 6 )
	} )

	it( 'polygon area of a 100 m x 50 m rectangle', () => {
		const rect = [ gz, offset( gz, 100, 0, 0 ), offset( gz, 100, 50, 0 ), offset( gz, 0, 50, 0 ) ]
		expect( polygonArea( rect ) ).toBeCloseTo( 5000, 3 )
		expect( polygonArea( [ ...rect ].reverse() ) ).toBeCloseTo( 5000, 3 )
	} )

	it( 'polygon area ignores height differences between corners', () => {
		const tri = [ gz, offset( gz, 20, 0, 5 ), offset( gz, 0, 20, -3 ) ]
		expect( polygonArea( tri ) ).toBeCloseTo( 200, 1 )
	} )

	it( 'surface area of a vertical wall, where the horizontal area is zero', () => {
		const wall = [ gz, offset( gz, 20, 0, 0 ), offset( gz, 20, 0, 10 ), offset( gz, 0, 0, 10 ) ]
		expect( surfaceArea( wall ) ).toBeCloseTo( 200, 3 )
		expect( polygonArea( wall ) ).toBeCloseTo( 0, 3 )
	} )

	it( 'surface area of a sloping roof is larger than its footprint', () => {
		const roof = [ gz, offset( gz, 10, 0, 0 ), offset( gz, 10, 10, 10 ), offset( gz, 0, 10, 10 ) ]
		expect( surfaceArea( roof ) ).toBeCloseTo( 100 * Math.SQRT2, 3 )
		expect( polygonArea( roof ) ).toBeCloseTo( 100, 3 )
	} )

	it( 'triangle splits a 3-4-5 into horizontal and vertical', () => {
		const t = triangle( gz, offset( gz, 3, 0, 4 ) )
		expect( t.horizontal ).toBeCloseTo( 3, 6 )
		expect( t.vertical ).toBeCloseTo( 4, 6 )
		expect( t.slant ).toBeCloseTo( 5, 6 )
	} )

	it( 'circle uses horizontal radius', () => {
		const c = circle( gz, offset( gz, 0, 10, 7 ) )
		expect( c.radius ).toBeCloseTo( 10, 6 )
		expect( c.area ).toBeCloseTo( Math.PI * 100, 4 )
	} )

	it( 'degenerate inputs', () => {
		expect( polygonArea( [ gz, offset( gz, 1, 1, 0 ) ] ) ).toBe( 0 )
		expect( polylineLength( [ gz ] ) ).toBe( 0 )
	} )
} )

describe( 'formatting', () => {
	it( 'switches units', () => {
		expect( formatLength( 12.345 ) ).toBe( '12.35 m' )
		expect( formatLength( 1234.6 ) ).toBe( '1.235 km' )
		expect( formatArea( 5000 ) ).toBe( '5000.00 m²' )
		expect( formatArea( 2.5e6 ) ).toBe( '2.5000 km²' )
	} )
} )
