// Checks made in the browser before anything is uploaded, with the server's own limits (GET /reconstructions/limits/).
// The server checks again; these only save a wasted upload and say what is wrong next to the right field.
import type { Limits, PhotoInfo } from './reconstructionsApi'

export interface Rejected {
	name: string
	reason: string
}

export const formatBytes = ( bytes: number ) =>
	bytes >= 2 ** 30 ? `${( bytes / 2 ** 30 ).toFixed( 1 )} GB` : bytes >= 2 ** 20 ? `${( bytes / 2 ** 20 ).toFixed( 1 )} MB` : `${Math.ceil( bytes / 1024 )} KB`

/** Split a selection (a dropped folder may hold anything) into photos to upload and files left out, with why. */
export function choosePhotos( files: File[], limits: Limits, onServer: PhotoInfo[] ): { accepted: File[]; rejected: Rejected[] } {
	const accepted: File[] = [], rejected: Rejected[] = []
	const names = new Set( onServer.map( p => p.name ) )
	const seen = new Set<string>()
	for ( const file of files ) {
		const lower = file.name.toLowerCase()
		if ( file.name.startsWith( '.' ) ) continue   // .DS_Store and other hidden files in a dropped folder
		if ( !limits.photo_types.some( ext => lower.endsWith( ext ) ) ) {
			rejected.push( { name: file.name, reason: `not a photo (${limits.photo_types.join( ', ' )})` } )
		} else if ( file.size > limits.max_photo_size ) {
			rejected.push( { name: file.name, reason: `larger than ${formatBytes( limits.max_photo_size )}` } )
		} else if ( seen.has( file.name ) ) {
			rejected.push( { name: file.name, reason: 'another photo has the same name' } )
		} else {
			seen.add( file.name )
			accepted.push( file )
		}
	}
	const total = new Set( [ ...names, ...seen ] ).size
	if ( total > limits.max_photos ) {
		const keep = Math.max( 0, accepted.length - ( total - limits.max_photos ) )
		for ( const file of accepted.splice( keep ) ) rejected.push( { name: file.name, reason: `at most ${limits.max_photos} photos per reconstruction` } )
	}
	return { accepted, rejected }
}

/** Parse "f, cx, cy, k" into numbers and check the count for the camera model; returns the numbers or an error. */
export function parseCameraParams( text: string, model: string, limits: Limits ): { params?: number[]; error?: string } {
	if ( !text.trim() ) return { params: undefined }
	const parts = text.split( /[\s,]+/ ).filter( Boolean )
	const params = parts.map( Number )
	if ( params.some( v => !Number.isFinite( v ) ) ) return { error: 'Numbers only, separated by commas or spaces.' }
	const expected = limits.camera_models[ model ]
	if ( expected !== undefined && params.length !== expected ) return { error: `${model} takes ${expected} parameters; ${params.length} given.` }
	return { params }
}

/** What each camera model's parameters are, in COLMAP's order (pixels; distortion has no unit). */
export const CAMERA_PARAM_NAMES: Record<string, string> = {
	SIMPLE_PINHOLE: 'f, cx, cy',
	PINHOLE: 'fx, fy, cx, cy',
	SIMPLE_RADIAL: 'f, cx, cy, k',
	RADIAL: 'f, cx, cy, k1, k2',
	OPENCV: 'fx, fy, cx, cy, k1, k2, p1, p2',
}

/** Match mask files to photos the way the server does: <photo name>.png or <photo stem>.png. */
export function matchMasks( files: File[], photos: string[] ): { matched: string[]; unmatched: string[] } {
	const byName = new Set( photos ), byStem = new Map( photos.map( p => [ p.replace( /\.[^.]+$/, '' ), p ] ) )
	const matched: string[] = [], unmatched: string[] = []
	for ( const f of files ) {
		const base = f.name.toLowerCase().endsWith( '.png' ) ? f.name.slice( 0, -4 ) : null
		const photo = base === null ? undefined : byName.has( base ) ? base : byStem.get( base )
		if ( photo ) matched.push( photo )
		else unmatched.push( f.name )
	}
	return { matched, unmatched }
}
