// Labels in the Cesium viewer: draws the shared label store and turns clicks into geographic points for the shared editor.
import * as Cesium from 'cesium'
import { watch } from 'vue'
import type { LabelHost } from '@/labels/labelHost'
import type { LabelStore } from '@/labels/labelStore'
import { fromGeoPoint, pickPoint, drawStyle, toGeoPoint, type MapViewerContext } from './mapViewer'

/** Draw the store's labels and select one when it is clicked. Returns a function that removes them. */
export function drawLabels( viewer: Cesium.Viewer, store: LabelStore ): () => void {
	const source = new Cesium.CustomDataSource( 'labels' )
	void viewer.dataSources.add( source )

	function draw() {
		source.entities.removeAll()
		for ( const label of store.labels.value ) {
			source.entities.add( {
				id: `label-${label.id}`,
				position: fromGeoPoint( label.position ),
				billboard: label.icon_url
					? { image: label.icon_url, width: 28, height: 28, verticalOrigin: Cesium.VerticalOrigin.BOTTOM, disableDepthTestDistance: Number.POSITIVE_INFINITY }
					: undefined,
				point: label.icon_url ? undefined : { ...drawStyle.point, color: Cesium.Color.DEEPSKYBLUE },
				label: { ...drawStyle.label, text: label.name, pixelOffset: new Cesium.Cartesian2( 0, label.icon_url ? -32 : -12 ) },
			} )
		}
		viewer.scene.requestRender()
	}
	const stopWatching = watch( store.labels, draw, { immediate: true } )

	// a click on a label selects it; clicks elsewhere are left to the active tool
	const handler = new Cesium.ScreenSpaceEventHandler( viewer.scene.canvas )
	handler.setInputAction( ( e: { position: Cesium.Cartesian2 } ) => {
		const picked = viewer.scene.pick( e.position )
		const id = picked?.id instanceof Cesium.Entity ? picked.id.id : ''
		if ( typeof id === 'string' && id.startsWith( 'label-' ) ) {
			store.selected.value = store.labels.value.find( l => `label-${l.id}` === id ) ?? null
		}
	}, Cesium.ScreenSpaceEventType.LEFT_CLICK )

	return () => {
		stopWatching()
		handler.destroy()
		viewer.dataSources.remove( source, true )
	}
}

/** The LabelHost for the Cesium viewer. */
export function cesiumLabelHost( ctx: MapViewerContext ): LabelHost {
	return {
		model: ctx.model,
		notify: ctx.notify,
		onModelClick( fn ) {
			const viewer = ctx.viewer
			const handler = new Cesium.ScreenSpaceEventHandler( viewer.scene.canvas )
			handler.setInputAction( ( e: { position: Cesium.Cartesian2 } ) => {
				const p = pickPoint( viewer, e.position )
				if ( p ) fn( toGeoPoint( p ) )
			}, Cesium.ScreenSpaceEventType.LEFT_CLICK )
			return () => { if ( !handler.isDestroyed() ) handler.destroy() }
		},
		showMarker( point ) {
			const viewer = ctx.viewer
			const marker = viewer.entities.add( { position: fromGeoPoint( point ), point: drawStyle.point } )
			viewer.scene.requestRender()
			return () => {
				viewer.entities.remove( marker )
				viewer.scene.requestRender()
			}
		},
	}
}
