// Saved camera tours of the map viewer: /api/v1/flight-paths/
import { query, request } from '@/api/http'
import type { GeoPoint, Page } from '@/api/types'

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

export const flightPathsApi = {
	flightPaths: ( model: number ) => request<Page<FlightPath>>( 'GET', '/flight-paths/' + query( { model } ) ),
	createFlightPath: ( model: number, name: string, points: CameraPose[] ) => request<FlightPath>( 'POST', '/flight-paths/', { model, name, points } ),
	deleteFlightPath: ( id: number ) => request<void>( 'DELETE', `/flight-paths/${id}/` ),
}
