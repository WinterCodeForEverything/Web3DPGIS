// Measuring in the three.js viewer: draws the shared measurement shapes and passes on clicks.
import { Group, Sphere } from 'three'
import type { ShallowRef } from 'vue'
import type { Model3D } from '@/api/types'
import type { MeasureHost } from '@/measurements/measureHost'
import type { ModelViewer } from './ModelViewer'
import { objectsFor, removeShapes } from './shapes'

/** The MeasureHost for the three.js viewer. viewer is a ref because the viewer is created after the page has provided the host. */
export function threeMeasureHost( viewer: ShallowRef<ModelViewer | null>, model: ShallowRef<Model3D | null>, notify: MeasureHost['notify'] ): MeasureHost {
	return {
		model,
		notify,
		listen( input ) {
			const v = viewer.value
			if ( !v ) return () => {}
			const pointAt = ( e: PointerEvent ) => {
				const p = v.pick( e )
				return p ? v.localToEcef( p ) : null
			}
			const stops = [
				v.onClick( e => { const p = pointAt( e ); if ( p ) input.click( p ) } ),
				v.onClick( () => input.finish(), 2 ),
				v.onPointerMove( e => input.move( pointAt( e ) ) ),
			]
			return () => stops.forEach( stop => stop() )
		},
		draw( shapes ) {
			const v = viewer.value
			if ( !v ) return () => {}
			const group = new Group()
			for ( const shape of shapes ) group.add( ...objectsFor( shape, v ) )
			v.scene.add( group )
			v.requestRender()
			return () => removeShapes( group, v )
		},
		focus( points ) {
			const v = viewer.value
			if ( !v || !points.length ) return
			const sphere = new Sphere().setFromPoints( points.map( p => v.ecefToLocal( p ) ) )
			v.focusOn( sphere.center, sphere.radius )
		},
	}
}
