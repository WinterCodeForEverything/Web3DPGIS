// Labels in the three.js viewer: draws the shared label store (shapes as meshes, names as HTML) and passes pointer input on.
import { Group } from 'three'
import { watch, type ShallowRef } from 'vue'
import type { Model3D } from '@/api/types'
import type { Label } from '@/labels/labelsApi'
import { iconUrlOf } from '@/labels/defaultIcon'
import type { LabelHost } from '@/labels/labelHost'
import { labelGeometry, nameAnchor, shapesOf } from '@/labels/labelShapes'
import type { LabelStore } from '@/labels/labelStore'
import type { ModelViewer } from './ModelViewer'
import { html, LABEL_STYLE, objectsFor, removeShapes } from './shapes'

function icon( url: string ): HTMLElement {
	const img = document.createElement( 'img' )
	img.src = url
	img.alt = ''
	img.style.cssText = 'width: 28px; height: 28px; display: block'
	return img
}

// the look matches the map viewer's labels: white text on a dark box, above the icon of a point label, always on top
function labelElement( label: Label, onClick: () => void ): HTMLElement {
	const el = document.createElement( 'div' )
	el.style.cssText = 'display: flex; flex-direction: column; align-items: center; gap: 3px; cursor: pointer; pointer-events: auto'
	el.className = 'model-label'
	el.dataset.labelId = String( label.id )
	const text = document.createElement( 'span' )
	text.textContent = label.name
	text.style.cssText = LABEL_STYLE
	el.append( text )
	if ( label.kind === 'point' ) el.append( icon( iconUrlOf( label ) ) )
	else el.style.paddingBottom = '12px'
	el.addEventListener( 'click', onClick )
	// keep a press on a label from starting a camera drag
	el.addEventListener( 'pointerdown', e => e.stopPropagation() )
	return el
}

/** Draw the store's labels and select one when its name is clicked. Returns a function that removes them. */
export function drawLabels( viewer: ModelViewer, store: LabelStore ): () => void {
	let group = new Group()
	let stopWatching = () => {}
	let removed = false

	function draw() {
		removeShapes( group, viewer )
		group = new Group()
		for ( const label of store.labels.value ) {
			const g = labelGeometry( label )
			for ( const shape of shapesOf( g ) ) group.add( ...objectsFor( shape, viewer ) )
			// the bottom of the name (and of a point label's icon) sits on the point, like a Cesium billboard with verticalOrigin BOTTOM
			group.add( html( labelElement( label, () => { store.selected.value = label } ), nameAnchor( g ), viewer, true ) )
		}
		viewer.scene.add( group )
		viewer.requestRender()
	}

	// positions can only be worked out once the tileset has been placed in the scene
	void viewer.placed.then( () => {
		if ( !removed ) stopWatching = watch( store.labels, draw, { immediate: true } )
	} )

	return () => {
		removed = true
		stopWatching()
		removeShapes( group, viewer )
	}
}

/** The LabelHost for the three.js viewer. viewer is a ref because the viewer is created after the page has provided the host. */
export function threeLabelHost( viewer: ShallowRef<ModelViewer | null>, model: ShallowRef<Model3D | null>, notify: LabelHost['notify'] ): LabelHost {
	return {
		model,
		notify,
		listen( input ) {
			const v = viewer.value
			if ( !v ) return () => {}
			// picking only looks at the model, so label shapes in front of it do not catch the pointer
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
	}
}
