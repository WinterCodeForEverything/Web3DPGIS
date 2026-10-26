// 3D reconstruction from photos: /api/v1/reconstructions/ (see reconstruction/api.py for the rules behind each call)
import { ApiError, query, request, upload } from '@/api/http'
import type { GeoPoint, Job, Page } from '@/api/types'

export type Preset = 'preview' | 'standard' | 'high'

/** What is known about the cameras; every field is optional on the server, which fills in defaults. */
export interface CameraOptions {
	camera_model: string
	camera_params?: number[]
	fix_intrinsics: boolean
	prior_std: number
	gps_std: [ number, number ]
	ignore_gps: boolean
	altitude_reference: 'sea-level' | 'ellipsoid'
	full_resolution: boolean
	sift_threshold?: number | null
	min_track: number
	units_to_metres: number
	up_axis: string
	up_method: 'IMAGE-ORIENTATION' | 'MANHATTAN-WORLD'
}

export interface ReconstructionStats {
	photos?: number
	photos_with_gps?: number
	masks?: number
	registered_photos?: number
	reprojection_error_px?: number
	position_residual_median?: number
	position_outliers?: Record<string, number>
	points?: number
	scale?: string
	georeferenced?: boolean
	geoid_corrected?: boolean
	total_seconds?: number
	result_mb?: number
	stages?: Record<string, number>
}

export interface Reconstruction {
	id: number
	model: number
	name: string
	is_public: boolean
	preset: Preset
	options: CameraOptions
	placement: GeoPoint | null
	status: 'pending' | 'processing' | 'ready' | 'failed'
	photos: { uploaded: number; pending: number; masks: number }
	has_poses: boolean
	mode: string
	stats: ReconstructionStats
	resolution_shift: number
	cancel_requested: boolean
	latest_job: ( Job & { kind: string } ) | null
	created_at: string
	started_at: string | null
}

export interface PhotoInfo {
	name: string
	size: number
	uploaded: boolean
	mask: boolean
}

export interface Limits {
	min_photos: number
	max_photos: number
	max_photo_size: number
	photo_types: string[]
	direct_upload: boolean
	presets: Record<Preset, { max_image_size: number; levels_of_detail: number }>
	camera_models: Record<string, number>
}

export interface NewReconstruction {
	name: string
	is_public: boolean
	preset: Preset
	placement?: GeoPoint | null
}

const base = '/reconstructions/'

export const reconstructionsApi = {
	limits: () => request<Limits>( 'GET', `${base}limits/` ),
	create: ( data: NewReconstruction ) => request<Reconstruction>( 'POST', base, data ),
	get: ( id: number ) => request<Reconstruction>( 'GET', `${base}${id}/` ),
	byModel: async ( modelId: number ) => ( await request<Page<Reconstruction>>( 'GET', base + query( { model: modelId } ) ) ).results[0] ?? null,
	update: ( id: number, changes: Partial<Pick<Reconstruction, 'name' | 'is_public' | 'preset' | 'placement'>> & { options?: Partial<CameraOptions> } ) =>
		request<Reconstruction>( 'PATCH', `${base}${id}/`, changes ),
	remove: ( id: number ) => request<void>( 'DELETE', `${base}${id}/` ),

	photos: ( id: number ) => request<PhotoInfo[]>( 'GET', `${base}${id}/photos/` ),
	removePhotos: ( id: number, names: string[] ) => request<{ removed: number }>( 'DELETE', `${base}${id}/photos/`, { names } ),
	/** One photo through the server (local storage). */
	uploadPhoto: ( id: number, file: File, onProgress: ( f: number ) => void ) => {
		const form = new FormData()
		form.append( 'photos', file )
		return upload<{ uploaded: string[] }>( `${base}${id}/photos/`, form, onProgress )
	},
	/** Presigned PUT URLs for photos that go straight into the bucket (S3 storage), then confirmPhotos. */
	presignPhotos: ( id: number, files: File[] ) =>
		request<{ uploads: { name: string; url: string; content_type: string }[] }>( 'POST', `${base}${id}/photos/`,
			{ photos: files.map( f => ( { name: f.name, size: f.size } ) ) } ),
	confirmPhotos: ( id: number, names: string[] ) =>
		request<{ confirmed: string[]; missing: string[]; too_large: string[] }>( 'POST', `${base}${id}/photos/confirm/`, { names } ),
	uploadMasks: ( id: number, files: File[], onProgress: ( f: number ) => void ) => {
		const form = new FormData()
		for ( const f of files ) form.append( 'masks', f )
		return upload<{ matched: string[]; unmatched: string[] }>( `${base}${id}/masks/`, form, onProgress )
	},
	uploadPoses: ( id: number, file: File ) => {
		const form = new FormData()
		form.append( 'file', file )
		return request<{ poses: number; kind: string }>( 'POST', `${base}${id}/poses/`, form )
	},
	removePoses: ( id: number ) => request<void>( 'DELETE', `${base}${id}/poses/` ),

	start: ( id: number ) => request<Job>( 'POST', `${base}${id}/start/` ),
	cancel: ( id: number ) => request<Job>( 'POST', `${base}${id}/cancel/` ),
}

/** PUT a file to a presigned bucket URL with progress (no cookies or CSRF: the URL carries its own signature). */
export function putToBucket( url: string, file: File, contentType: string, onProgress: ( f: number ) => void ): Promise<void> {
	return new Promise( ( resolve, reject ) => {
		const xhr = new XMLHttpRequest()
		xhr.open( 'PUT', url )
		xhr.setRequestHeader( 'Content-Type', contentType )
		xhr.upload.onprogress = e => e.lengthComputable && onProgress( e.loaded / e.total )
		xhr.onload = () => xhr.status >= 200 && xhr.status < 300 ? resolve() : reject( new ApiError( xhr.status, `Storage refused the upload (${xhr.status})` ) )
		xhr.onerror = () => reject( new ApiError( 0, 'Network error, please check your connection.' ) )
		xhr.send( file )
	} )
}
