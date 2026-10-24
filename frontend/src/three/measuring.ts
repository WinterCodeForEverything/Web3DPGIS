// Measuring in the three.js viewer: draws the shared measurement shapes and passes on clicks.
import { BufferGeometry, DoubleSide, Float32BufferAttribute, Group, Mesh, MeshBasicMaterial, type Object3D } from 'three'
import { Line2 } from 'three/examples/jsm/lines/Line2.js'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'
import { CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import type { ShallowRef } from 'vue'
import type { Model3D } from '@/api/types'
import type { MeasureHost } from '@/measurements/measureHost'
import type { LineColor, Shape } from '@/measurements/measurementShapes'
import { circleRing, type Vec3 } from '@/geo/geometry'
import type { ModelViewer } from './ModelViewer'

// the same look as the map viewer's measurements
const COLORS: Record<LineColor, number> = { yellow: 0xffff00, blue: 0x00bfff, green: 0x00ff00 }
const LABEL_STYLE = 'font: 14px sans-serif; color: #fff; background: rgba(0, 0, 0, 0.6); padding: 1px 4px; border-radius: 3px; white-space: nowrap; text-shadow: 0 0 3px #000'
const TOTAL_STYLE = 'font: bold 15px sans-serif; color: #fff; background: rgba(217, 72, 15, 0.9); padding: 1px 4px; border-radius: 3px; white-space: nowrap'

function html( element: HTMLElement, at: Vec3, viewer: ModelViewer, bottom = false ) {
	const object = new CSS2DObject( element )
	object.position.copy( viewer.ecefToLocal( at ) )
	// labels sit just above their point, like Cesium labels with verticalOrigin BOTTOM and a 12 px offset
	if ( bottom ) object.center.set( 0.5, 1 )
	return object
}

function mark( at: Vec3, viewer: ModelViewer ) {
	const dot = document.createElement( 'div' )
	dot.style.cssText = 'width: 9px; height: 9px; border-radius: 50%; background: #ff0; border: 1px solid #000'
	return html( dot, at, viewer )
}

function label( at: Vec3, text: string, total: boolean, viewer: ModelViewer ) {
	const outer = document.createElement( 'div' )
	outer.style.paddingBottom = '12px'
	const span = document.createElement( 'span' )
	span.textContent = text
	span.style.cssText = total ? TOTAL_STYLE : LABEL_STYLE
	outer.append( span )
	return html( outer, at, viewer, true )
}

function line( points: Vec3[], color: number, viewer: ModelViewer ) {
	const geometry = new LineGeometry().setPositions( points.flatMap( p => viewer.ecefToLocal( p ).toArray() ) )
	const group = new Group()
	// drawn twice: faded where the model hides it, full colour where it is in front, like Cesium's depthFailMaterial
	for ( const hidden of [ true, false ] ) {
		const material = new LineMaterial( { color, linewidth: 2, transparent: hidden, opacity: hidden ? 0.4 : 1, depthTest: !hidden } )
		const object = new Line2( geometry, material )
		object.renderOrder = hidden ? 1 : 2
		object.onBeforeRender = renderer => renderer.getSize( material.resolution )
		group.add( object )
	}
	return group
}

function fill( points: Vec3[], viewer: ModelViewer ) {
	// a fan from the first corner, which covers convex outlines (the usual case for measured areas)
	const local = points.map( p => viewer.ecefToLocal( p ) )
	const positions: number[] = []
	for ( let i = 1; i < local.length - 1; i++ ) positions.push( ...local[0].toArray(), ...local[i].toArray(), ...local[i + 1].toArray() )
	const geometry = new BufferGeometry()
	geometry.setAttribute( 'position', new Float32BufferAttribute( positions, 3 ) )
	return new Mesh( geometry, new MeshBasicMaterial( { color: COLORS.yellow, transparent: true, opacity: 0.3, side: DoubleSide, depthWrite: false } ) )
}

function objectsFor( shape: Shape, viewer: ModelViewer ): Object3D[] {
	switch ( shape.type ) {
		case 'mark': return [ mark( shape.at, viewer ) ]
		case 'label': return [ label( shape.at, shape.text, !!shape.total, viewer ) ]
		case 'line': return [ line( shape.points, COLORS[ shape.color ], viewer ) ]
		case 'polygon': return shape.points.length >= 3 ? [ fill( shape.points, viewer ) ] : []
		case 'circle': {
			const ring = circleRing( shape.centre, shape.radius )
			return [ fill( ring, viewer ), line( [ ...ring, ring[0] ], COLORS.yellow, viewer ) ]
		}
	}
}

function dispose( object: Object3D ) {
	object.traverse( child => {
		if ( child instanceof Mesh || child instanceof Line2 ) {
			child.geometry.dispose()
			;( Array.isArray( child.material ) ? child.material : [ child.material ] ).forEach( m => m.dispose() )
		}
	} )
}

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
			return () => {
				// removing CSS2DObjects from the scene also takes their elements off the page
				v.scene.remove( group )
				const elements: CSS2DObject[] = []
				group.traverse( child => { if ( child instanceof CSS2DObject ) elements.push( child ) } )
				elements.forEach( child => child.removeFromParent() )
				dispose( group )
				v.requestRender()
			}
		},
	}
}
