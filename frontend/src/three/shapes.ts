// The shared shapes (geo/shapes.ts) as three.js objects, for measurements and labels alike; they look like the map viewer's.
import {
	BufferGeometry, ConeGeometry, CylinderGeometry, DoubleSide, Float32BufferAttribute, Group, Mesh, MeshBasicMaterial, MeshStandardMaterial,
	Quaternion, SphereGeometry, Vector3, type Object3D,
} from 'three'
import { Line2 } from 'three/examples/jsm/lines/Line2.js'
import { LineGeometry } from 'three/examples/jsm/lines/LineGeometry.js'
import { LineMaterial } from 'three/examples/jsm/lines/LineMaterial.js'
import { CSS2DObject } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import type { Shape, ShapeColor } from '@/geo/shapes'
import { circleRing, enuBasis, type Vec3 } from '@/geo/geometry'
import type { ModelViewer } from './ModelViewer'

const NAMED: Record<string, number> = { yellow: 0xffff00, blue: 0x00bfff, green: 0x00ff00 }
export const shapeColor = ( c: ShapeColor ): number => NAMED[ c ] ?? parseInt( c.slice( 1 ), 16 )
export const LABEL_STYLE = 'font: 14px sans-serif; color: #fff; background: rgba(0, 0, 0, 0.6); padding: 1px 4px; border-radius: 3px; white-space: nowrap; text-shadow: 0 0 3px #000'

const above = ( p: Vec3, by: number ): Vec3 => {
	const { up } = enuBasis( p )
	return [ p[0] + up[0] * by, p[1] + up[1] * by, p[2] + up[2] * by ]
}

/** An HTML element at an ECEF point; bottom puts the element's bottom edge on the point instead of its centre. */
export function html( element: HTMLElement, at: Vec3, viewer: ModelViewer, bottom = false ) {
	const object = new CSS2DObject( element )
	object.position.copy( viewer.ecefToLocal( at ) )
	if ( bottom ) object.center.set( 0.5, 1 )
	return object
}

function mark( at: Vec3, viewer: ModelViewer ) {
	const dot = document.createElement( 'div' )
	dot.style.cssText = 'width: 9px; height: 9px; border-radius: 50%; background: #ff0; border: 1px solid #000'
	return html( dot, at, viewer )
}

function label( at: Vec3, text: string, viewer: ModelViewer ) {
	// just above the point, like Cesium labels with verticalOrigin BOTTOM and a 12 px offset
	const outer = document.createElement( 'div' )
	outer.style.paddingBottom = '12px'
	const span = document.createElement( 'span' )
	span.textContent = text
	span.style.cssText = LABEL_STYLE
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

function mesh( positions: number[], material: MeshBasicMaterial | MeshStandardMaterial ) {
	const geometry = new BufferGeometry()
	geometry.setAttribute( 'position', new Float32BufferAttribute( positions, 3 ) )
	geometry.computeVertexNormals()
	return new Mesh( geometry, material )
}

const fillMaterial = ( color: number ) => new MeshBasicMaterial( { color, transparent: true, opacity: 0.3, side: DoubleSide, depthWrite: false } )
const solidMaterial = ( color: number ) => new MeshStandardMaterial( { color, transparent: true, opacity: 0.6, side: DoubleSide, depthWrite: false, roughness: 0.8 } )

function fill( points: Vec3[], color: number, viewer: ModelViewer ) {
	// a fan from the first corner, which covers convex outlines (the usual case)
	const local = points.map( p => viewer.ecefToLocal( p ) )
	const positions: number[] = []
	for ( let i = 1; i < local.length - 1; i++ ) positions.push( ...local[0].toArray(), ...local[i].toArray(), ...local[i + 1].toArray() )
	return mesh( positions, fillMaterial( color ) )
}

function wall( points: Vec3[], height: number, color: number, viewer: ModelViewer ) {
	const bottom = points.map( p => viewer.ecefToLocal( p ).toArray() )
	const top = points.map( p => viewer.ecefToLocal( above( p, height ) ).toArray() )
	const positions: number[] = []
	for ( let i = 0; i < points.length - 1; i++ ) positions.push( ...bottom[i], ...bottom[i + 1], ...top[i + 1], ...bottom[i], ...top[i + 1], ...top[i] )
	const group = new Group()
	group.add( mesh( positions, solidMaterial( color ) ), line( points, color, viewer ), line( points.map( p => above( p, height ) ), color, viewer ) )
	return group
}

function box( points: Vec3[], height: number, color: number, viewer: ModelViewer ) {
	// the sides are a wall around the closed outline; floor and roof are fans of the outline and its raised copy
	const roof = points.map( p => above( p, height ) )
	const group = wall( [ ...points, points[0] ], height, color, viewer )
	for ( const ring of [ points, roof ] ) {
		const local = ring.map( p => viewer.ecefToLocal( p ) )
		const positions: number[] = []
		for ( let i = 1; i < local.length - 1; i++ ) positions.push( ...local[0].toArray(), ...local[i].toArray(), ...local[i + 1].toArray() )
		group.add( mesh( positions, solidMaterial( color ) ) )
	}
	for ( const p of points ) group.add( line( [ p, above( p, height ) ], color, viewer ) )
	return group
}

/** A three.js geometry built along +Y, stood upright at an ECEF point (its centre). */
function upright( geometry: BufferGeometry, centre: Vec3, color: number, viewer: ModelViewer ) {
	const object = new Mesh( geometry, solidMaterial( color ) )
	const at = viewer.ecefToLocal( centre )
	const up = viewer.ecefToLocal( above( centre, 1 ) ).sub( at ).normalize()
	object.position.copy( at )
	object.quaternion.copy( new Quaternion().setFromUnitVectors( new Vector3( 0, 1, 0 ), up ) )
	return object
}

export function objectsFor( shape: Shape, viewer: ModelViewer ): Object3D[] {
	switch ( shape.type ) {
		case 'mark': return [ mark( shape.at, viewer ) ]
		case 'label': return [ label( shape.at, shape.text, viewer ) ]
		case 'line': return [ line( shape.points, shapeColor( shape.color ), viewer ) ]
		case 'polygon': return shape.points.length >= 3 ? [ fill( shape.points, shapeColor( shape.color ?? 'yellow' ), viewer ) ] : []
		case 'circle': {
			const ring = circleRing( shape.centre, shape.radius ), color = shapeColor( shape.color ?? 'yellow' )
			return [ fill( ring, color, viewer ), line( [ ...ring, ring[0] ], color, viewer ) ]
		}
		case 'wall': return shape.points.length >= 2 ? [ wall( shape.points, shape.height, shapeColor( shape.color ), viewer ) ] : []
		case 'box': return shape.points.length >= 3 ? [ box( shape.points, shape.height, shapeColor( shape.color ), viewer ) ] : []
		case 'sphere': return [ upright( new SphereGeometry( shape.radius, 48, 24 ), shape.centre, shapeColor( shape.color ), viewer ) ]
		case 'cylinder': {
			const geometry = shape.topRadius > 0
				? new CylinderGeometry( shape.topRadius, shape.radius, shape.height, 48 )
				: new ConeGeometry( shape.radius, shape.height, 48 )
			return [ upright( geometry, above( shape.base, shape.height / 2 ), shapeColor( shape.color ), viewer ) ]
		}
	}
}

/** Take a group of drawn shapes out of the scene and free their GPU memory. */
export function removeShapes( group: Group, viewer: ModelViewer ) {
	viewer.scene.remove( group )
	// removing CSS2DObjects from the scene also takes their elements off the page
	const elements: CSS2DObject[] = []
	group.traverse( child => {
		if ( child instanceof CSS2DObject ) elements.push( child )
		if ( child instanceof Mesh || child instanceof Line2 ) {
			child.geometry.dispose()
			;( Array.isArray( child.material ) ? child.material : [ child.material ] ).forEach( m => m.dispose() )
		}
	} )
	elements.forEach( child => child.removeFromParent() )
	viewer.requestRender()
}
