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

export interface Label {
	id: number
	model: number
	name: string
	icon: number | null
	icon_url: string | null
	position: GeoPoint
	properties: Record<string, unknown>
}

export const labelsApi = {
	labelIcons: () => request<Page<LabelIcon>>( 'GET', '/label-icons/' ),
	uploadLabelIcon: ( form: FormData ) => request<LabelIcon>( 'POST', '/label-icons/', form ),
	labels: ( model: number ) => request<Page<Label>>( 'GET', '/labels/' + query( { model } ) ),
	createLabel: ( label: { model: number; name: string; icon: number | null; position: GeoPoint; properties?: Record<string, unknown> } ) =>
		request<Label>( 'POST', '/labels/', label ),
	updateLabel: ( id: number, changes: Partial<Pick<Label, 'name' | 'properties'>> ) => request<Label>( 'PATCH', `/labels/${id}/`, changes ),
	deleteLabel: ( id: number ) => request<void>( 'DELETE', `/labels/${id}/` ),
}
