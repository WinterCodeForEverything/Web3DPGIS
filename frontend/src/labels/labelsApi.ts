// Labels on a model and the icon library: /api/v1/labels/, /api/v1/label-icons/
import { query, request } from '@/api/http'
import type { GeoPoint, Page } from '@/api/types'

export interface LabelIcon {
	id: number
	name: string
	image: string
	owner: string | null
	can_edit: boolean
}

export type LabelKind = 'point' | 'polyline' | 'polygon' | 'rectangle' | 'circle' | 'wall' | 'cuboid' | 'sphere' | 'cylinder' | 'cone'

/**
 * A point or a shape on a model. `position` is the point itself, the centre of a circle or sphere, the base centre of a
 * cylinder or cone, or (for polylines, polygons, rectangles, walls and cuboids, whose vertices are `points`) where the name is shown.
 * `radius` and `height` are in metres, for the kinds that have them; null otherwise.
 */
export interface Label {
	id: number
	model: number
	kind: LabelKind
	name: string
	icon: number | null
	icon_url: string | null
	position: GeoPoint
	points: GeoPoint[]
	radius: number | null
	height: number | null
	color: string
	properties: Record<string, unknown>
}

/** What is sent to create a label; the kind and shape cannot change afterwards. */
export interface LabelInput {
	model: number
	kind: LabelKind
	name: string
	icon: number | null
	position?: GeoPoint
	points?: GeoPoint[]
	radius?: number
	height?: number
	color?: string
	properties?: Record<string, unknown>
}

export const labelsApi = {
	labelIcons: () => request<Page<LabelIcon>>( 'GET', '/label-icons/' ),
	uploadLabelIcon: ( form: FormData ) => request<LabelIcon>( 'POST', '/label-icons/', form ),
	labels: ( model: number ) => request<Page<Label>>( 'GET', '/labels/' + query( { model } ) ),
	createLabel: ( label: LabelInput ) => request<Label>( 'POST', '/labels/', label ),
	updateLabel: ( id: number, changes: Partial<Pick<Label, 'name' | 'color' | 'properties'>> ) => request<Label>( 'PATCH', `/labels/${id}/`, changes ),
	deleteLabel: ( id: number ) => request<void>( 'DELETE', `/labels/${id}/` ),
}
