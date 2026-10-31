// Your saved measurements: /api/v1/measurements/
import { query, request } from '@/api/http'
import type { GeoPoint, Page } from '@/api/types'

export type MeasurementKind = 'point' | 'distance' | 'area' | 'height' | 'circle'

/** A saved measurement: its clicked points in order, and the values the server worked out from them (metres, m²). */
export interface Measurement {
	id: number
	model: number
	kind: MeasurementKind
	name: string
	annotation: string
	points: GeoPoint[]
	results: Record<string, number | number[]>
	created_at: string
}

export const measurementsApi = {
	measurements: ( model: number, kind?: MeasurementKind ) => request<Page<Measurement>>( 'GET', '/measurements/' + query( { model, kind } ) ),
	createMeasurement: ( measurement: { model: number; kind: MeasurementKind; points: GeoPoint[]; name?: string } ) =>
		request<Measurement>( 'POST', '/measurements/', measurement ),
	/** Only the name and annotation can change once a measurement is saved. */
	updateMeasurement: ( id: number, changes: { name?: string; annotation?: string } ) =>
		request<Measurement>( 'PATCH', `/measurements/${id}/`, changes ),
	deleteMeasurement: ( id: number ) => request<void>( 'DELETE', `/measurements/${id}/` ),
}
