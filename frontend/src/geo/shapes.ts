// What a viewer draws, independent of the viewer: measurements and labels describe their drawings with these, and each
// viewer turns them into its own objects (cesium/shapes.ts, three/shapes.ts). Points are Earth-centred (ECEF) metres.
import type { Vec3 } from './geometry'

/** A CSS hex colour (#rrggbb), or one of the measurement colours. */
export type ShapeColor = 'yellow' | 'blue' | 'green' | `#${string}`

export type Shape =
	| { type: 'mark'; at: Vec3 }
	| { type: 'line'; points: Vec3[]; color: ShapeColor }
	| { type: 'label'; at: Vec3; text: string }
	/** A filled outline; yellow unless a colour is given. */
	| { type: 'polygon'; points: Vec3[]; color?: ShapeColor }
	/** A filled horizontal circle with its outline. */
	| { type: 'circle'; centre: Vec3; radius: number; color?: ShapeColor }
	/** A vertical wall standing on a path, `height` metres tall. */
	| { type: 'wall'; points: Vec3[]; height: number; color: ShapeColor }
	| { type: 'sphere'; centre: Vec3; radius: number; color: ShapeColor }
	/** An upright cylinder standing on `base`; a topRadius of 0 makes it a cone. */
	| { type: 'cylinder'; base: Vec3; radius: number; topRadius: number; height: number; color: ShapeColor }
