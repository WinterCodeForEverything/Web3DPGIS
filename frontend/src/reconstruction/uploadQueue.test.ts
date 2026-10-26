import { describe, expect, it } from 'vitest'
import { ApiError } from '@/api/http'
import { type Send, UploadQueue } from './uploadQueue'

const photo = ( name: string, size = 100 ) => new File( [ new Uint8Array( size ) ], name, { type: 'image/jpeg' } )
const quick = { retryDelay: () => 0 }

describe( 'UploadQueue', () => {
	it( 'uploads at most `concurrency` photos at a time', async () => {
		let active = 0, peak = 0
		const send: Send = async () => {
			active++; peak = Math.max( peak, active )
			await new Promise( r => setTimeout( r, 5 ) )
			active--
		}
		const queue = new UploadQueue( send, { concurrency: 3, ...quick } )
		queue.add( Array.from( { length: 10 }, ( _, i ) => photo( `p${i}.jpg` ) ) )
		await queue.run()
		expect( peak ).toBe( 3 )
		expect( queue.counts ).toMatchObject( { done: 10, failed: 0, total: 10 } )
		expect( queue.progress ).toBe( 1 )
	} )

	it( 'retries network and server errors, but not refusals', async () => {
		const calls: Record<string, number> = {}
		const send: Send = async item => {
			calls[ item.name ] = ( calls[ item.name ] ?? 0 ) + 1
			if ( item.name === 'flaky.jpg' && calls[ item.name ] < 3 ) throw new ApiError( 0, 'Network error' )
			if ( item.name === 'down.jpg' ) throw new ApiError( 503, 'Service unavailable' )
			if ( item.name === 'bad.jpg' ) throw new ApiError( 400, [ 'bad.jpg: photos must be one of .jpg' ] )
		}
		const queue = new UploadQueue( send, { retries: 2, ...quick } )
		queue.add( [ photo( 'flaky.jpg' ), photo( 'down.jpg' ), photo( 'bad.jpg' ) ] )
		await queue.run()
		expect( calls ).toEqual( { 'flaky.jpg': 3, 'down.jpg': 3, 'bad.jpg': 1 } )
		expect( queue.items.map( i => [ i.name, i.state ] ) ).toEqual( [ [ 'flaky.jpg', 'done' ], [ 'down.jpg', 'failed' ], [ 'bad.jpg', 'failed' ] ] )
		expect( queue.items[2].error ).toContain( 'photos must be one of' )
	} )

	it( 'puts failed photos back on request', async () => {
		let fail = true
		const queue = new UploadQueue( async () => { if ( fail ) throw new ApiError( 400, 'no' ) }, quick )
		queue.add( [ photo( 'a.jpg' ) ] )
		await queue.run()
		expect( queue.counts.failed ).toBe( 1 )
		fail = false
		queue.retryFailed()
		await queue.run()
		expect( queue.counts ).toMatchObject( { done: 1, failed: 0 } )
	} )

	it( 'skips photos the server already has, so a reload resumes', async () => {
		const sent: string[] = []
		const queue = new UploadQueue( async item => { sent.push( item.name ) }, quick )
		queue.add( [ photo( 'a.jpg', 100 ), photo( 'b.jpg', 100 ), photo( 'c.jpg', 100 ) ], new Map( [ [ 'a.jpg', 100 ], [ 'b.jpg', 99 ] ] ) )
		await queue.run()
		expect( sent ).toEqual( [ 'b.jpg', 'c.jpg' ] )   // b.jpg changed size, so it goes again
		expect( queue.items.find( i => i.name === 'a.jpg' )?.state ).toBe( 'skipped' )
	} )

	it( 'replaces a photo added twice and removes on request', () => {
		const queue = new UploadQueue( async () => {}, quick )
		queue.add( [ photo( 'a.jpg', 1 ), photo( 'b.jpg' ) ] )
		queue.add( [ photo( 'a.jpg', 2 ) ] )
		queue.remove( 'b.jpg' )
		expect( queue.items.map( i => [ i.name, i.file.size ] ) ).toEqual( [ [ 'a.jpg', 2 ] ] )
	} )
} )
