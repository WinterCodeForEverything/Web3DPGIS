import { describe, expect, it } from 'vitest'
import { distance, ecefToGeodetic, enuBasis, geodeticToEcef, type Vec3 } from '@/geo/geometry'
import { describeLabel, draftShapes, geometryFromClicks, labelGeometry, labelInput, nameAnchor, shapesOf } from './labelShapes'

const base = geodeticToEcef( 113.26, 23.13, 10 )
function at( e: number, n: number, u = 0 ): Vec3 {
	const { east, north, up } = enuBasis( base )
	return [ 0, 1, 2 ].map( i => base[i] + e * east[i] + n * north[i] + u * up[i] ) as Vec3
}
const heightOf = ( p: Vec3 ) => ecefToGeodetic( p ).height

describe( 'label shapes', () => {
	it( 'a point label is saved at its click, with its icon and no colour or size', () => {
		const g = geometryFromClicks( 'point', [ base ], 10, '#ff0000' )!
		const input = labelInput( 7, ' Gate ', 3, g )
		expect( input ).toMatchObject( { model: 7, kind: 'point', name: 'Gate', icon: 3 } )
		expect( input.position!.height ).toBeCloseTo( 10, 6 )
		expect( input ).not.toHaveProperty( 'color' )
		expect( input ).not.toHaveProperty( 'radius' )
		expect( shapesOf( g ) ).toEqual( [] )
	} )

	it( 'an unnamed shape is named after its kind, and a shape has no icon', () => {
		const g = geometryFromClicks( 'polygon', [ at( 0, 0 ), at( 10, 0 ), at( 10, 10 ) ], 10, '#00ff00' )!
		expect( labelInput( 7, '', 3, g ) ).toMatchObject( { name: 'Polygon', icon: null, color: '#00ff00' } )
	} )

	it( 'vertex shapes send their points and leave the name position to the server', () => {
		const g = geometryFromClicks( 'wall', [ at( 0, 0 ), at( 20, 0 ) ], 6, '#1e90ff' )!
		const input = labelInput( 1, 'Fence', null, g )
		expect( input.points ).toHaveLength( 2 )
		expect( input.position ).toBeUndefined()
		expect( input.height ).toBe( 6 )
		expect( describeLabel( g ) ).toBe( 'Wall · 20.00 m long · height 6.00 m' )
	} )

	it( 'round shapes take their radius from the second click: horizontal for circles and cylinders, straight for spheres', () => {
		const clicks = [ base, at( 3, 4, 12 ) ]
		expect( geometryFromClicks( 'circle', clicks, 10, '#000000' )!.radius ).toBeCloseTo( 5, 6 )
		expect( geometryFromClicks( 'cylinder', clicks, 10, '#000000' )!.radius ).toBeCloseTo( 5, 6 )
		expect( geometryFromClicks( 'sphere', clicks, 10, '#000000' )!.radius ).toBeCloseTo( 13, 6 )
		// only walls, cylinders and cones have a height
		expect( labelInput( 1, '', null, geometryFromClicks( 'sphere', clicks, 10, '#000000' )! ) ).not.toHaveProperty( 'height' )
	} )

	it( 'a cone is a cylinder with no top, and names sit above the tops of 3D shapes', () => {
		const cone = geometryFromClicks( 'cone', [ base, at( 2, 0 ) ], 8, '#123456' )!
		expect( shapesOf( cone ) ).toEqual( [ { type: 'cylinder', base, radius: cone.radius, topRadius: 0, height: 8, color: '#123456' } ] )
		expect( heightOf( nameAnchor( cone ) ) ).toBeCloseTo( 18, 3 )
		const sphere = geometryFromClicks( 'sphere', [ base, at( 0, 0, 4 ) ], 8, '#123456' )!
		expect( heightOf( nameAnchor( sphere ) ) ).toBeCloseTo( 14, 3 )
	} )

	it( 'a saved label reads back from longitude/latitude into the same geometry', () => {
		const saved = { kind: 'cylinder' as const, position: { longitude: 113.26, latitude: 23.13, height: 10 }, points: [], radius: 3, height: 8, color: '#ff8800' }
		const g = labelGeometry( saved )
		expect( distance( g.position, base ) ).toBeLessThan( 1e-6 )
		expect( describeLabel( g ) ).toBe( 'Cylinder · radius 3.00 m · height 8.00 m' )
	} )

	it( 'while drawing, the shape follows the cursor; a polygon with two corners is drawn as a line', () => {
		expect( draftShapes( 'circle', [ base ], null, 10, '#ff0000' ) ).toEqual( [ { type: 'mark', at: base } ] )
		expect( draftShapes( 'circle', [ base ], at( 5, 0 ), 10, '#ff0000' ).map( s => s.type ) ).toEqual( [ 'mark', 'circle' ] )
		expect( draftShapes( 'polygon', [ base ], at( 5, 0 ), 10, '#ff0000' ).map( s => s.type ) ).toEqual( [ 'mark', 'line' ] )
		expect( draftShapes( 'polygon', [ base, at( 5, 0 ) ], at( 5, 5 ), 10, '#ff0000' ).map( s => s.type ) ).toEqual( [ 'mark', 'mark', 'polygon', 'line' ] )
	} )
} )
