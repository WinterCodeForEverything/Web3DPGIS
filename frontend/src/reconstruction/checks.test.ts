import { describe, expect, it } from 'vitest'
import { choosePhotos, matchMasks, parseCameraParams } from './checks'
import type { Limits } from './reconstructionsApi'

const limits: Limits = {
	min_photos: 3, max_photos: 4, max_photo_size: 1000, photo_types: [ '.jpg', '.jpeg', '.png', '.tif', '.tiff' ], direct_upload: false,
	presets: { preview: { max_image_size: 1600, levels_of_detail: 3 }, standard: { max_image_size: 2400, levels_of_detail: 3 }, high: { max_image_size: 3200, levels_of_detail: 4 } },
	camera_models: { SIMPLE_RADIAL: 4, OPENCV: 8 },
}
const file = ( name: string, size = 10 ) => new File( [ new Uint8Array( size ) ], name )

describe( 'choosePhotos', () => {
	it( 'keeps photos and says why the rest were left out', () => {
		const { accepted, rejected } = choosePhotos( [ file( 'a.JPG' ), file( 'notes.txt' ), file( 'big.jpg', 2000 ), file( '.DS_Store' ), file( 'a.JPG' ) ], limits, [] )
		expect( accepted.map( f => f.name ) ).toEqual( [ 'a.JPG' ] )
		expect( rejected.map( r => [ r.name, r.reason ] ) ).toEqual( [
			[ 'notes.txt', 'not a photo (.jpg, .jpeg, .png, .tif, .tiff)' ],
			[ 'big.jpg', 'larger than 1 KB' ],
			[ 'a.JPG', 'another photo has the same name' ],
		] )
	} )

	it( 'counts photos already on the server against the limit', () => {
		const onServer = [ { name: 'x.jpg', size: 1, uploaded: true, mask: false }, { name: 'y.jpg', size: 1, uploaded: true, mask: false } ]
		const { accepted, rejected } = choosePhotos( [ file( 'x.jpg' ), file( 'a.jpg' ), file( 'b.jpg' ), file( 'c.jpg' ) ], limits, onServer )
		expect( accepted.map( f => f.name ) ).toEqual( [ 'x.jpg', 'a.jpg', 'b.jpg' ] )   // x.jpg replaces itself; c.jpg would be the fifth
		expect( rejected ).toEqual( [ { name: 'c.jpg', reason: 'at most 4 photos per reconstruction' } ] )
	} )
} )

describe( 'parseCameraParams', () => {
	it( 'reads numbers and checks the count for the model', () => {
		expect( parseCameraParams( '1000, 640 480,0.1', 'SIMPLE_RADIAL', limits ) ).toEqual( { params: [ 1000, 640, 480, 0.1 ] } )
		expect( parseCameraParams( '1000, 640', 'OPENCV', limits ).error ).toBe( 'OPENCV takes 8 parameters; 2 given.' )
		expect( parseCameraParams( '1000, x', 'OPENCV', limits ).error ).toContain( 'Numbers only' )
		expect( parseCameraParams( '  ', 'OPENCV', limits ) ).toEqual( { params: undefined } )
	} )
} )

describe( 'matchMasks', () => {
	it( 'matches <photo>.png and <stem>.png like the server', () => {
		expect( matchMasks( [ file( 'a.jpg.png' ), file( 'b.png' ), file( 'c.png' ), file( 'a.jpg' ) ], [ 'a.jpg', 'b.JPG' ] ) )
			.toEqual( { matched: [ 'a.jpg', 'b.JPG' ], unmatched: [ 'c.png', 'a.jpg' ] } )
	} )
} )
