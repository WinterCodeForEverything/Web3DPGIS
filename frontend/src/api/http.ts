// Thin fetch wrapper for the Django API: session cookies, CSRF header, JSON errors.

export class ApiError extends Error {
	constructor( public status: number, public data: unknown ) {
		super( ApiError.describe( data ) || `Request failed (${status})` )
	}

	/** Flatten DRF error bodies ({"detail": …} or {"field": ["msg"]}) into one readable line. */
	static describe( data: unknown ): string {
		if ( !data || typeof data !== 'object' ) return typeof data === 'string' ? data : ''
		return Object.entries( data as Record<string, unknown> )
			.map( ( [ key, value ] ) => {
				const text = Array.isArray( value ) ? value.join( ' ' ) : typeof value === 'object' ? ApiError.describe( value ) : String( value )
				return key === 'detail' || key === 'non_field_errors' ? text : `${key}: ${text}`
			} )
			.join( '; ' )
	}

	/** Errors for one form field, if the API returned any. */
	field( name: string ): string {
		const value = ( this.data as Record<string, unknown> | null )?.[name]
		return Array.isArray( value ) ? value.join( ' ' ) : ''
	}
}

function csrfToken(): string {
	return document.cookie.split( '; ' ).find( c => c.startsWith( 'csrftoken=' ) )?.split( '=' )[1] ?? ''
}

export async function request<T>( method: string, path: string, body?: unknown ): Promise<T> {
	const headers: Record<string, string> = { Accept: 'application/json' }
	let payload: BodyInit | undefined
	if ( body instanceof FormData ) {
		payload = body
	} else if ( body !== undefined ) {
		headers['Content-Type'] = 'application/json'
		payload = JSON.stringify( body )
	}
	if ( method !== 'GET' ) headers['X-CSRFToken'] = csrfToken()
	const response = await fetch( `/api/v1${path}`, { method, headers, body: payload, credentials: 'same-origin' } )
	if ( response.status === 204 ) return undefined as T
	const data = response.headers.get( 'content-type' )?.includes( 'json' ) ? await response.json() : await response.text()
	if ( !response.ok ) throw new ApiError( response.status, data )
	return data as T
}

/** Upload with progress events (fetch cannot report upload progress). */
export function upload<T>( path: string, form: FormData, onProgress: ( fraction: number ) => void ): Promise<T> {
	return new Promise( ( resolve, reject ) => {
		const xhr = new XMLHttpRequest()
		xhr.open( 'POST', `/api/v1${path}` )
		xhr.setRequestHeader( 'X-CSRFToken', csrfToken() )
		xhr.setRequestHeader( 'Accept', 'application/json' )
		xhr.upload.onprogress = e => e.lengthComputable && onProgress( e.loaded / e.total )
		xhr.onload = () => {
			let data: unknown = xhr.responseText
			try { data = JSON.parse( xhr.responseText ) } catch { /* not JSON */ }
			if ( xhr.status >= 200 && xhr.status < 300 ) resolve( data as T )
			else reject( new ApiError( xhr.status, data ) )
		}
		xhr.onerror = () => reject( new ApiError( 0, 'Network error, please check your connection.' ) )
		xhr.send( form )
	} )
}

export const query = ( params: Record<string, string | number | boolean | undefined> ) => {
	const entries = Object.entries( params ).filter( ( [ , v ] ) => v !== undefined && v !== '' )
	return entries.length ? '?' + new URLSearchParams( entries.map( ( [ k, v ] ) => [ k, String( v ) ] ) ) : ''
}
