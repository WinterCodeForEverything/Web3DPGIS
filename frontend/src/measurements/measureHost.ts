// What a viewer provides so the shared measuring panel can work in it. Points are Earth-centred (ECEF) metres.
import type { InjectionKey, ShallowRef } from 'vue'
import type { Model3D } from '@/api/types'
import type { Vec3 } from '@/geo/geometry'
import type { Shape } from './measurementShapes'

export interface MeasureInput {
	/** A left click on the model. */
	click( point: Vec3 ): void
	/** The pointer moved; point is on the model, or null when it is off it. */
	move( point: Vec3 | null ): void
	/** A right click: finish the measurement. */
	finish(): void
}

export interface MeasureHost {
	model: ShallowRef<Model3D | null>
	notify( message: string, kind?: 'info' | 'error' ): void
	/** Start passing pointer input to `input`. Returns a function that stops. */
	listen( input: MeasureInput ): () => void
	/** Draw shapes. Returns a function that removes them again. */
	draw( shapes: Shape[] ): () => void
	/** Move the camera so these points are in the middle of the view, keeping the direction it looks from. */
	focus( points: Vec3[] ): void
}

export const measureHostKey: InjectionKey<MeasureHost> = Symbol( 'measure-host' )
