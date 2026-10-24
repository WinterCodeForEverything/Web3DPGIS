// A model's labels, shared by every viewer: loading, placing, editing and deleting all go through here,
// so the 3D model viewer and the map viewer save labels the same way. Viewers only draw them and report clicks.
import { shallowRef, type InjectionKey, type ShallowRef } from 'vue'
import { api } from '@/api/client'
import type { GeoPoint, Label } from '@/api/types'

export interface NewLabel {
	name: string
	icon: number | null
	position: GeoPoint
}

export interface LabelStore {
	readonly modelId: number
	labels: ShallowRef<Label[]>
	selected: ShallowRef<Label | null>
	reload(): Promise<void>
	create( label: NewLabel ): Promise<Label>
	updateProperties( id: number, properties: Record<string, unknown> ): Promise<void>
	remove( id: number ): Promise<void>
	removeAll(): Promise<void>
}

export const labelStoreKey: InjectionKey<LabelStore> = Symbol( 'labels' )

export function createLabelStore( modelId: number ): LabelStore {
	const labels = shallowRef<Label[]>( [] )
	const selected = shallowRef<Label | null>( null )

	async function reload() {
		const page = await api.labels( modelId )
		labels.value = page.results
		if ( selected.value ) selected.value = labels.value.find( l => l.id === selected.value!.id ) ?? null
	}

	async function create( label: NewLabel ) {
		const saved = await api.createLabel( { model: modelId, name: label.name.trim() || 'Label', icon: label.icon, position: label.position } )
		await reload()
		return saved
	}

	async function updateProperties( id: number, properties: Record<string, unknown> ) {
		await api.updateLabel( id, { properties } )
		await reload()
	}

	async function remove( id: number ) {
		await api.deleteLabel( id )
		if ( selected.value?.id === id ) selected.value = null
		await reload()
	}

	async function removeAll() {
		await Promise.all( labels.value.map( l => api.deleteLabel( l.id ) ) )
		selected.value = null
		await reload()
	}

	return { modelId, labels, selected, reload, create, updateProperties, remove, removeAll }
}
