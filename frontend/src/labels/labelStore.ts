// A model's labels, shared by every viewer: loading, placing, editing and deleting all go through here,
// so the 3D model viewer and the map viewer save labels the same way. Viewers only draw them and report clicks.
import { shallowRef, type InjectionKey, type ShallowRef } from 'vue'
import { labelsApi } from '@/labels/labelsApi'
import type { Label, LabelInput } from '@/labels/labelsApi'

/** A label to create on the store's model. */
export type NewLabel = Omit<LabelInput, 'model'>

export interface LabelStore {
	readonly modelId: number
	labels: ShallowRef<Label[]>
	selected: ShallowRef<Label | null>
	/** The id of a label just added, so its details panel opens ready for a name; the panel clears it. */
	justCreated: ShallowRef<number | null>
	reload(): Promise<void>
	create( label: NewLabel ): Promise<Label>
	updateProperties( id: number, properties: Record<string, unknown> ): Promise<void>
	updateColor( id: number, color: string ): Promise<void>
	update( id: number, changes: Partial<Pick<Label, 'name' | 'color' | 'properties'>> ): Promise<void>
	remove( id: number ): Promise<void>
	removeAll(): Promise<void>
}

export const labelStoreKey: InjectionKey<LabelStore> = Symbol( 'labels' )

export function createLabelStore( modelId: number ): LabelStore {
	const labels = shallowRef<Label[]>( [] )
	const selected = shallowRef<Label | null>( null )
	const justCreated = shallowRef<number | null>( null )

	async function reload() {
		const page = await labelsApi.labels( modelId )
		labels.value = page.results
		if ( selected.value ) selected.value = labels.value.find( l => l.id === selected.value!.id ) ?? null
	}

	async function create( label: NewLabel ) {
		const saved = await labelsApi.createLabel( { ...label, model: modelId, name: label.name.trim() || 'Label' } )
		await reload()
		return saved
	}

	async function updateProperties( id: number, properties: Record<string, unknown> ) {
		await labelsApi.updateLabel( id, { properties } )
		await reload()
	}

	async function updateColor( id: number, color: string ) {
		await update( id, { color } )
	}

	async function update( id: number, changes: Partial<Pick<Label, 'name' | 'color' | 'properties'>> ) {
		await labelsApi.updateLabel( id, changes )
		await reload()
	}

	async function remove( id: number ) {
		await labelsApi.deleteLabel( id )
		if ( selected.value?.id === id ) selected.value = null
		await reload()
	}

	async function removeAll() {
		await Promise.all( labels.value.map( l => labelsApi.deleteLabel( l.id ) ) )
		selected.value = null
		await reload()
	}

	return { modelId, labels, selected, justCreated, reload, create, updateProperties, updateColor, update, remove, removeAll }
}
