// What a viewer provides so the shared label editor and popup can work in it. Points are Earth-centred (ECEF) metres.
import type { InjectionKey, ShallowRef } from 'vue'
import type { Model3D } from '@/api/types'
import type { Vec3 } from '@/geo/geometry'
import type { Shape } from '@/geo/shapes'

export interface LabelPointer {
	/** A left click on the model (drags to move the camera don't count). */
	click( point: Vec3 ): void
	/** The pointer moved; point is on the model, or null when it is off it. */
	move( point: Vec3 | null ): void
	/** A right click: finish the shape being drawn. */
	finish(): void
}

export interface LabelHost {
	model: ShallowRef<Model3D | null>
	notify( message: string, kind?: 'info' | 'error' ): void
	/** Start passing pointer input on the model to `input`. Returns a function that stops. */
	listen( input: LabelPointer ): () => void
	/** Draw temporary shapes, e.g. a label while it is being drawn or saved. Returns a function that removes them. */
	draw( shapes: Shape[] ): () => void
}

export const labelHostKey: InjectionKey<LabelHost> = Symbol( 'label-host' )
