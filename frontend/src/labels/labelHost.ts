// What a viewer provides so the shared label editor and popup can work in it.
import type { InjectionKey, ShallowRef } from 'vue'
import type { GeoPoint, Model3D } from '@/api/types'

export interface LabelHost {
	model: ShallowRef<Model3D | null>
	notify( message: string, kind?: 'info' | 'error' ): void
	/** Call fn with the point on the model under each click (drags to move the camera don't count). Returns a function that stops listening. */
	onModelClick( fn: ( point: GeoPoint ) => void ): () => void
	/** Show a temporary marker, e.g. while a new label is being saved. Returns a function that removes it. */
	showMarker( point: GeoPoint ): () => void
}

export const labelHostKey: InjectionKey<LabelHost> = Symbol( 'label-host' )
