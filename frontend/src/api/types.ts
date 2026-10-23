// Shapes returned by the Django REST API (/api/v1/). See /api/docs/ for the full schema.

export interface GeoPoint {
	longitude: number
	latitude: number
	height: number
}

export interface User {
	id: number
	username: string
	email: string
	is_staff: boolean
}

export type JobStatus = 'queued' | 'running' | 'succeeded' | 'failed'

export interface Job {
	id: number
	model: number
	status: JobStatus
	progress: number
	attempts: number
	stage: string
	message: string
	created_at: string
	started_at: string | null
	finished_at: string | null
	log?: string
}

export type ModelStatus = 'pending' | 'processing' | 'ready' | 'failed'

export interface Model3D {
	id: number
	name: string
	owner: string | null
	thumbnail: string | null
	source_name: string | null
	status: ModelStatus
	tileset_url: string | null
	location: GeoPoint | null
	height_offset: number
	is_public: boolean
	is_visible: boolean
	created_at: string
	updated_at: string
	latest_job: Job | null
	can_edit: boolean
	distance_m: number | null
}

export interface LabelIcon {
	id: number
	name: string
	image: string
	owner: string | null
	can_edit: boolean
}

export interface Label {
	id: number
	model: number
	name: string
	icon: number | null
	icon_url: string | null
	position: GeoPoint
	properties: Record<string, unknown>
}

export interface CameraPose {
	position: GeoPoint
	direction: [ number, number, number ]
	up: [ number, number, number ]
}

export interface FlightPath {
	id: number
	model: number
	name: string
	points: CameraPose[]
}

export interface Page<T> {
	count: number
	next: string | null
	previous: string | null
	results: T[]
}
