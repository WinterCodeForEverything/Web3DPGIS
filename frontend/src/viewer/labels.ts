// The label layer: draws a model's saved labels and reports clicks on them. Lives as long as the viewer page.
import * as Cesium from 'cesium'
import { shallowRef, type InjectionKey, type ShallowRef } from 'vue'
import { api } from '@/api/client'
import type { Label } from '@/api/types'
import { fromGeoPoint, style } from './core'

export interface LabelLayer {
	labels: ShallowRef<Label[]>
	selected: ShallowRef<Label | null>
	reload(): Promise<void>
	destroy(): void
}

export const labelLayerKey: InjectionKey<LabelLayer> = Symbol( 'labels' )

export function createLabelLayer( viewer: Cesium.Viewer, modelId: number ): LabelLayer {
	const labels = shallowRef<Label[]>( [] )
	const selected = shallowRef<Label | null>( null )
	const source = new Cesium.CustomDataSource( 'labels' )
	void viewer.dataSources.add( source )

	function draw() {
		source.entities.removeAll()
		for ( const label of labels.value ) {
			source.entities.add( {
				id: `label-${label.id}`,
				position: fromGeoPoint( label.position ),
				billboard: label.icon_url
					? { image: label.icon_url, width: 28, height: 28, verticalOrigin: Cesium.VerticalOrigin.BOTTOM, disableDepthTestDistance: Number.POSITIVE_INFINITY }
					: undefined,
				point: label.icon_url ? undefined : { ...style.point, color: Cesium.Color.DEEPSKYBLUE },
				label: { ...style.label, text: label.name, pixelOffset: new Cesium.Cartesian2( 0, label.icon_url ? -32 : -12 ) },
			} )
		}
		viewer.scene.requestRender()
	}

	// a click on a label selects it; clicks elsewhere are left to the active tool
	const handler = new Cesium.ScreenSpaceEventHandler( viewer.scene.canvas )
	handler.setInputAction( ( e: { position: Cesium.Cartesian2 } ) => {
		const picked = viewer.scene.pick( e.position )
		const id = picked?.id instanceof Cesium.Entity ? picked.id.id : ''
		if ( typeof id === 'string' && id.startsWith( 'label-' ) ) {
			selected.value = labels.value.find( l => `label-${l.id}` === id ) ?? null
		}
	}, Cesium.ScreenSpaceEventType.LEFT_CLICK )

	async function reload() {
		const page = await api.labels( modelId )
		labels.value = page.results
		if ( selected.value ) selected.value = labels.value.find( l => l.id === selected.value!.id ) ?? null
		draw()
	}

	function destroy() {
		handler.destroy()
		viewer.dataSources.remove( source, true )
	}

	return { labels, selected, reload, destroy }
}
