// Labels in the Cesium viewer: draws the shared label store and passes pointer input on the model to the shared editor.
import * as Cesium from 'cesium'
import { watch } from 'vue'
import type { LabelHost } from '@/labels/labelHost'
import { iconUrlOf } from '@/labels/defaultIcon'
import { iconAnchor, labelGeometry, shapesOf } from '@/labels/labelShapes'
import type { LabelStore } from '@/labels/labelStore'
import { pickPoint, drawStyle, renderBriefly, toVec3, type MapViewerContext } from './mapViewer'
import { entityOptions } from './shapes'

// every entity of a label has an id starting with label-<id>: its icon and name are label-<id>, its shape parts label-<id>/<n>
const ICON_SIZE = 28
const LABEL_ID = /^label-(\d+)(\/|$)/

/** Draw the store's labels and select one when any part of it is clicked. Returns a function that removes them. */
export function drawLabels( viewer: Cesium.Viewer, store: LabelStore ): () => void {
	const source = new Cesium.CustomDataSource( 'labels' )
	void viewer.dataSources.add( source )

	function draw() {
		source.entities.removeAll()
		for ( const label of store.labels.value ) {
			const g = labelGeometry( label )
			shapesOf( g ).forEach( ( shape, n ) => source.entities.add( { ...entityOptions( shape ), id: `label-${label.id}/${n}` } ) )
			// the icon stands on a point label's point and a 3D shape's top centre, and is centred on a 2D shape's middle
			const { at, standing } = iconAnchor( g )
			source.entities.add( {
				id: `label-${label.id}`,
				position: new Cesium.Cartesian3( ...at ),
				billboard: {
					image: iconUrlOf( label ), width: ICON_SIZE, height: ICON_SIZE, disableDepthTestDistance: Number.POSITIVE_INFINITY,
					verticalOrigin: standing ? Cesium.VerticalOrigin.BOTTOM : Cesium.VerticalOrigin.CENTER,
				},
				// the name sits just above the icon
				label: { ...drawStyle.label, text: label.name, pixelOffset: new Cesium.Cartesian2( 0, -( standing ? ICON_SIZE : ICON_SIZE / 2 ) - 4 ) },
			} )
		}
		renderBriefly( viewer )
	}
	const stopWatching = watch( store.labels, draw, { immediate: true } )

	// a click on a label selects it; clicks elsewhere are left to the active tool
	const handler = new Cesium.ScreenSpaceEventHandler( viewer.scene.canvas )
	handler.setInputAction( ( e: { position: Cesium.Cartesian2 } ) => {
		const picked = viewer.scene.pick( e.position )
		const id = picked?.id instanceof Cesium.Entity ? picked.id.id : ''
		const match = typeof id === 'string' ? LABEL_ID.exec( id ) : null
		if ( match ) store.selected.value = store.labels.value.find( l => l.id === Number( match[1] ) ) ?? null
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
		listen( input ) {
			const viewer = ctx.viewer
			const handler = new Cesium.ScreenSpaceEventHandler( viewer.scene.canvas )
			const pointAt = ( position: Cesium.Cartesian2 ) => {
				const p = pickPoint( viewer, position )
				return p ? toVec3( p ) : null
			}
			handler.setInputAction( ( e: { position: Cesium.Cartesian2 } ) => {
				const p = pointAt( e.position )
				if ( p ) input.click( p )
			}, Cesium.ScreenSpaceEventType.LEFT_CLICK )
			handler.setInputAction( ( e: { endPosition: Cesium.Cartesian2 } ) => input.move( pointAt( e.endPosition ) ), Cesium.ScreenSpaceEventType.MOUSE_MOVE )
			handler.setInputAction( () => input.finish(), Cesium.ScreenSpaceEventType.RIGHT_CLICK )
			return () => { if ( !handler.isDestroyed() ) handler.destroy() }
		},
		draw( shapes ) {
			const viewer = ctx.viewer
			const entities = shapes.map( shape => viewer.entities.add( entityOptions( shape ) ) )
			viewer.scene.requestRender()
			return () => {
				for ( const e of entities ) viewer.entities.remove( e )
				viewer.scene.requestRender()
			}
		},
	}
}
