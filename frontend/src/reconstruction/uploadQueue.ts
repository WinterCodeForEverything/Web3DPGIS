// Uploads many photos a few at a time. Network and server errors are retried; a refusal (4xx) is not, its message is
// kept on the photo. Photos the server already has (same name and size) are skipped, so after a reload choosing the
// same folder again uploads only what is missing.
import { ApiError } from '@/api/http'

export type UploadState = 'waiting' | 'uploading' | 'done' | 'failed' | 'skipped'

export interface UploadItem {
	file: File
	name: string
	state: UploadState
	progress: number      // 0–1
	attempts: number
	error: string
}

export interface QueueOptions {
	concurrency?: number
	retries?: number                         // extra attempts after a network or server error
	retryDelay?: ( attempt: number ) => number
}

export type Send = ( item: UploadItem, onProgress: ( fraction: number ) => void ) => Promise<void>

const temporary = ( e: unknown ) => !( e instanceof ApiError ) || e.status === 0 || e.status >= 500

export class UploadQueue {
	items: UploadItem[] = []
	running = false
	private concurrency: number
	private retries: number
	private retryDelay: ( attempt: number ) => number

	constructor( private send: Send, options: QueueOptions = {} ) {
		this.concurrency = options.concurrency ?? 4
		this.retries = options.retries ?? 2
		this.retryDelay = options.retryDelay ?? ( attempt => 1000 * attempt )
	}

	/** Queue files; ones the server already has (by name and size) are marked skipped. Re-adding a name replaces it. */
	add( files: File[], onServer: Map<string, number> = new Map() ) {
		for ( const file of files ) {
			this.items = this.items.filter( i => i.name !== file.name )
			const skipped = onServer.get( file.name ) === file.size
			this.items.push( { file, name: file.name, state: skipped ? 'skipped' : 'waiting', progress: skipped ? 1 : 0, attempts: 0, error: '' } )
		}
	}

	remove( name: string ) {
		this.items = this.items.filter( i => i.name !== name || i.state === 'uploading' )
	}

	/** Put failed photos back in the queue; run() picks them up. */
	retryFailed() {
		for ( const item of this.items.filter( i => i.state === 'failed' ) ) Object.assign( item, { state: 'waiting', progress: 0, attempts: 0, error: '' } )
	}

	get counts() {
		const count = ( s: UploadState ) => this.items.filter( i => i.state === s ).length
		return { waiting: count( 'waiting' ), uploading: count( 'uploading' ), done: count( 'done' ) + count( 'skipped' ), failed: count( 'failed' ),
			total: this.items.length }
	}

	/** Fraction of bytes done over the whole queue. */
	get progress() {
		const total = this.items.reduce( ( s, i ) => s + i.file.size, 0 )
		return total ? this.items.reduce( ( s, i ) => s + i.file.size * i.progress, 0 ) / total : 0
	}

	/** Upload everything waiting, `concurrency` at a time; resolves when nothing is left to do. */
	async run() {
		if ( this.running ) return
		this.running = true
		try {
			const worker = async () => {
				for ( let item = this.next(); item; item = this.next() ) await this.upload( item )
			}
			await Promise.all( Array.from( { length: this.concurrency }, worker ) )
		} finally {
			this.running = false
		}
	}

	private next() {
		const item = this.items.find( i => i.state === 'waiting' )
		if ( item ) item.state = 'uploading'
		return item
	}

	private async upload( item: UploadItem ) {
		for ( ;; ) {
			item.attempts++
			try {
				await this.send( item, f => { item.progress = f } )
				Object.assign( item, { state: 'done', progress: 1, error: '' } )
				return
			} catch ( e ) {
				item.error = e instanceof Error ? e.message : String( e )
				if ( !temporary( e ) || item.attempts > this.retries ) {
					Object.assign( item, { state: 'failed', progress: 0 } )
					return
				}
				await new Promise( r => setTimeout( r, this.retryDelay( item.attempts ) ) )
			}
		}
	}
}
