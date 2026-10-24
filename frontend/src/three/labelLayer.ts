// Labels in the three.js viewer: draws the shared label store as HTML markers and turns clicks into geographic points.
import { Group } from 'three'
import { CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { watch, type ShallowRef } from 'vue'
import type { GeoPoint, Model3D } from '@/api/types'
import type { Label } from '@/labels/labelsApi'
import type { LabelHost } from '@/labels/labelHost'
import type { LabelStore } from '@/labels/labelStore'
import type { ModelViewer } from './ModelViewer'

// the look matches the map viewer's labels: white outlined text on a dark box above an icon or dot, always on top
const TEXT_STYLE = 'font: 14px sans-serif; color: #fff; background: rgba(0, 0, 0, 0.6); padding: 1px 4px; border-radius: 3px; white-space: nowrap; text-shadow: 0 0 3px #000'

function marker( iconUrl: string | null, color: string ): HTMLElement {
	if ( iconUrl ) {
		const img = document.createElement( 'img' )
		img.src = iconUrl
		img.style.cssText = 'width: 28px; height: 28px; display: block'
		return img
	}
	const dot = document.createElement( 'div' )
	dot.style.cssText = `width: 9px; height: 9px; border-radius: 50%; background: ${color}; border: 1px solid #000`
	return dot
}

function labelElement( label: Label, onClick: () => void ): HTMLElement {
	const el = document.createElement( 'div' )
	el.style.cssText = 'display: flex; flex-direction: column; align-items: center; gap: 3px; cursor: pointer; pointer-events: auto'
	el.className = 'model-label'
	el.dataset.labelId = String( label.id )
	const text = document.createElement( 'span' )
	text.textContent = label.name
	text.style.cssText = TEXT_STYLE
	el.append( text, marker( label.icon_url, '#00bfff' ) )
	el.addEventListener( 'click', onClick )
	// keep a press on a label from starting a camera drag
	el.addEventListener( 'pointerdown', e => e.stopPropagation() )
	return el
}

/** Draw the store's labels and select one when it is clicked. Returns a function that removes them. */
export function drawLabels( viewer: ModelViewer, store: LabelStore ): () => void {
	const group = new Group()
	viewer.scene.add( group )
	let stopWatching = () => {}
	let removed = false

	function draw() {
		for ( const child of [ ...group.children ] ) group.remove( child )
		for ( const label of store.labels.value ) {
			const object = new CSS2DObject( labelElement( label, () => { store.selected.value = label } ) )
			object.position.copy( viewer.geoToLocal( label.position ) )
			object.center.set( 0.5, 1 )   // the bottom of the icon sits on the point, like a Cesium billboard with verticalOrigin BOTTOM
			group.add( object )
		}
		viewer.requestRender()
	}

	// positions can only be worked out once the tileset has been placed in the scene
	void viewer.placed.then( () => {
		if ( !removed ) stopWatching = watch( store.labels, draw, { immediate: true } )
	} )

	return () => {
		removed = true
		stopWatching()
		for ( const child of [ ...group.children ] ) group.remove( child )
		viewer.scene.remove( group )
		viewer.requestRender()
	}
}

/** The LabelHost for the three.js viewer. viewer is a ref because the viewer is created after the page has provided the host. */
export function threeLabelHost( viewer: ShallowRef<ModelViewer | null>, model: ShallowRef<Model3D | null>, notify: LabelHost['notify'] ): LabelHost {
	return {
		model,
		notify,
		onModelClick( fn: ( point: GeoPoint ) => void ) {
			const v = viewer.value
			if ( !v ) return () => {}
			return v.onClick( e => {
				const p = v.pick( e )
				if ( p ) fn( v.localToGeo( p ) )
			} )
		},
		showMarker( point ) {
			const v = viewer.value
			if ( !v ) return () => {}
			const object = new CSS2DObject( marker( null, '#ffff00' ) )
			object.position.copy( v.geoToLocal( point ) )
			v.scene.add( object )
			v.requestRender()
			return () => {
				v.scene.remove( object )
				v.requestRender()
			}
		},
	}
}
