// Thin fetch wrapper for the Django API: session cookies, CSRF header, JSON errors.
import type { CameraPose, FlightPath, GeoPoint, Job, Label, LabelIcon, Model3D, Page, User } from './types'

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

const query = ( params: Record<string, string | number | boolean | undefined> ) => {
	const entries = Object.entries( params ).filter( ( [ , v ] ) => v !== undefined && v !== '' )
	return entries.length ? '?' + new URLSearchParams( entries.map( ( [ k, v ] ) => [ k, String( v ) ] ) ) : ''
}

export const api = {
	me: () => request<User | null>( 'GET', '/auth/me/' ),
	login: ( login: string, password: string ) => request<User>( 'POST', '/auth/login/', { login, password } ),
	register: ( username: string, email: string, password: string ) => request<User>( 'POST', '/auth/register/', { username, email, password } ),
	logout: () => request<void>( 'POST', '/auth/logout/' ),

	models: ( params: { search?: string; mine?: boolean; near?: string; radius?: number; bbox?: string; page?: number } = {} ) =>
		request<Page<Model3D>>( 'GET', '/models/' + query( params ) ),
	model: ( id: number ) => request<Model3D>( 'GET', `/models/${id}/` ),
	updateModel: ( id: number, changes: Partial<Pick<Model3D, 'name' | 'is_public' | 'is_visible' | 'height_offset'>> ) =>
		request<Model3D>( 'PATCH', `/models/${id}/`, changes ),
	deleteModel: ( id: number ) => request<void>( 'DELETE', `/models/${id}/` ),
	reprocess: ( id: number ) => request<Job>( 'POST', `/models/${id}/reprocess/` ),
	uploadModel: ( form: FormData, onProgress: ( f: number ) => void ) => upload<Model3D>( '/models/', form, onProgress ),

	job: ( id: number ) => request<Job>( 'GET', `/jobs/${id}/` ),

	labelIcons: () => request<Page<LabelIcon>>( 'GET', '/label-icons/' ),
	uploadLabelIcon: ( form: FormData ) => request<LabelIcon>( 'POST', '/label-icons/', form ),
	labels: ( model: number ) => request<Page<Label>>( 'GET', '/labels/' + query( { model } ) ),
	createLabel: ( label: { model: number; name: string; icon: number | null; position: GeoPoint; properties?: Record<string, unknown> } ) =>
		request<Label>( 'POST', '/labels/', label ),
	updateLabel: ( id: number, changes: Partial<Pick<Label, 'name' | 'properties'>> ) => request<Label>( 'PATCH', `/labels/${id}/`, changes ),
	deleteLabel: ( id: number ) => request<void>( 'DELETE', `/labels/${id}/` ),

	flightPaths: ( model: number ) => request<Page<FlightPath>>( 'GET', '/flight-paths/' + query( { model } ) ),
	createFlightPath: ( model: number, name: string, points: CameraPose[] ) => request<FlightPath>( 'POST', '/flight-paths/', { model, name, points } ),
	deleteFlightPath: ( id: number ) => request<void>( 'DELETE', `/flight-paths/${id}/` ),
}
