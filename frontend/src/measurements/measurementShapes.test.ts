import { describe, expect, it } from 'vitest'
import { enuBasis, geodeticToEcef, type Vec3 } from '@/geo/geometry'
import { describeMeasurement, previewShapes } from './measurementShapes'

const base = geodeticToEcef( 113.26, 23.13, 10 )
function at( e: number, n: number, u = 0 ): Vec3 {
	const { east, north, up } = enuBasis( base )
	return [ 0, 1, 2 ].map( i => base[i] + e * east[i] + n * north[i] + u * up[i] ) as Vec3
}

describe( 'measurement shapes', () => {
	it( 'a path draws each segment with its length; only the panel text has the total', () => {
		const { text, shapes } = describeMeasurement( 'distance', [ at( 0, 0 ), at( 30, 0 ), at( 30, 40 ) ] )
		expect( text ).toBe( 'Distance: 70.00 m' )
		expect( shapes.filter( s => s.type === 'mark' ) ).toHaveLength( 3 )
		expect( shapes.filter( s => s.type === 'line' ) ).toHaveLength( 2 )
		const labels = shapes.flatMap( s => ( s.type === 'label' ? [ s ] : [] ) )
		expect( labels.map( l => l.text ) ).toEqual( [ '30.00 m', '40.00 m' ] )
	} )

	it( 'an area is filled and outlined, with surface and plan area for a slope', () => {
		const { text, shapes } = describeMeasurement( 'area', [ at( 0, 0 ), at( 100, 0 ), at( 100, 50, 50 ), at( 0, 50, 50 ) ] )
		expect( text ).toMatch( /^Area: 7071\.\d\d m² \(plan (4999|5000)\.\d\d m²\)$/ )
		expect( shapes.some( s => s.type === 'polygon' ) ).toBe( true )
		const outline = shapes.find( s => s.type === 'line' )
		expect( outline?.type === 'line' && outline.points ).toHaveLength( 5 )
	} )

	it( 'previews only the stretch from the last point of a path to the cursor', () => {
		const [ preview ] = previewShapes( 'distance', [ at( 0, 0 ), at( 10, 0 ) ], at( 20, 0 ) )
		expect( preview.type === 'line' && preview.points ).toEqual( [ at( 10, 0 ), at( 20, 0 ) ] )
		expect( previewShapes( 'area', [], at( 0, 0 ) ) ).toEqual( [] )
	} )
} )
