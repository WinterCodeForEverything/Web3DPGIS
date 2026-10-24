import { describe, expect, it } from 'vitest'
import { viewerFromQuery } from './viewers'

describe( 'viewerFromQuery', () => {
	it( 'defaults to the three.js model viewer', () => {
		expect( viewerFromQuery( undefined ) ).toBe( 'model' )
		expect( viewerFromQuery( '' ) ).toBe( 'model' )
		expect( viewerFromQuery( 'something-else' ) ).toBe( 'model' )
		expect( viewerFromQuery( [ 'map' ] ) ).toBe( 'model' )
	} )

	it( 'picks the GIS viewer when asked', () => {
		expect( viewerFromQuery( 'map' ) ).toBe( 'map' )
		expect( viewerFromQuery( 'model' ) ).toBe( 'model' )
	} )
} )
