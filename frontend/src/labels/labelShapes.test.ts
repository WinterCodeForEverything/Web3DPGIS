import { describe, expect, it } from 'vitest'
import { distance, ecefToGeodetic, enuBasis, geodeticToEcef, type Vec3 } from '@/geo/geometry'
import { defaultName, describeLabel, draftShapes, geometryFromClicks, labelGeometry, labelInput, iconAnchor, shapesOf } from './labelShapes'

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

	it( 'an unnamed shape is named after its kind, and keeps its icon', () => {
		const g = geometryFromClicks( 'polygon', [ at( 0, 0 ), at( 10, 0 ), at( 10, 10 ) ], 10, '#00ff00' )!
		expect( labelInput( 7, '', 3, g ) ).toMatchObject( { name: 'Polygon', icon: 3, color: '#00ff00' } )
	} )

	it( 'a 2D shape has its icon centred on its middle; a 3D shape has it standing on its top centre', () => {
		const line = geometryFromClicks( 'polyline', [ at( 0, 0 ), at( 10, 0 ), at( 10, 30 ) ], 10, '#000000' )!
		expect( iconAnchor( line ).standing ).toBe( false )
		expect( distance( iconAnchor( line ).at, at( 10, 10 ) ) ).toBeLessThan( 1e-6 )   // 20 m along a 40 m path
		const square = geometryFromClicks( 'polygon', [ at( 0, 0 ), at( 10, 0 ), at( 10, 10 ), at( 0, 10 ) ], 10, '#000000' )!
		expect( distance( iconAnchor( square ).at, at( 5, 5 ) ) ).toBeLessThan( 0.01 )
		const wall = geometryFromClicks( 'wall', [ at( 0, 0 ), at( 20, 0 ), at( 20, 20 ) ], 6, '#000000' )!
		expect( iconAnchor( wall ) ).toMatchObject( { standing: true } )
		expect( distance( iconAnchor( wall ).at, at( 20, 0, 6 ) ) ).toBeLessThan( 0.01 )   // top of the wall, halfway along it
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

	it( 'a cone is a cylinder with no top, and icons stand on the tops of 3D shapes', () => {
		const cone = geometryFromClicks( 'cone', [ base, at( 2, 0 ) ], 8, '#123456' )!
		expect( shapesOf( cone ) ).toEqual( [ { type: 'cylinder', base, radius: cone.radius, topRadius: 0, height: 8, color: '#123456' } ] )
		expect( heightOf( iconAnchor( cone ).at ) ).toBeCloseTo( 18, 3 )
		const sphere = geometryFromClicks( 'sphere', [ base, at( 0, 0, 4 ) ], 8, '#123456' )!
		expect( heightOf( iconAnchor( sphere ).at ) ).toBeCloseTo( 14, 3 )
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

	it( 'a new label is named after its kind with the next number, skipping names already taken', () => {
		expect( defaultName( 'circle', [] ) ).toBe( 'Circle 1' )
		const labels = [ { kind: 'circle' as const, name: 'Circle 1' }, { kind: 'circle' as const, name: 'Pond' }, { kind: 'point' as const, name: 'Gate' } ]
		expect( defaultName( 'circle', labels ) ).toBe( 'Circle 3' )
		expect( defaultName( 'point', labels ) ).toBe( 'Point 2' )
		// Circle 1 was deleted after Circle 2 was added: two circles remain, and Circle 3 is taken
		expect( defaultName( 'circle', [ { kind: 'circle', name: 'Circle 2' }, { kind: 'circle', name: 'Circle 3' } ] ) ).toBe( 'Circle 4' )
	} )
} )
