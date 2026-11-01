// The shared shapes (geo/shapes.ts) as Cesium entities, for measurements and labels alike.
import * as Cesium from 'cesium'
import type { Shape, ShapeColor } from '@/geo/shapes'
import { enuBasis, type Vec3 } from '@/geo/geometry'
import { drawStyle } from './mapViewer'

const NAMED: Record<string, Cesium.Color> = { yellow: drawStyle.line, blue: Cesium.Color.DEEPSKYBLUE, green: Cesium.Color.LIME }
const cartesian = ( v: Vec3 ) => new Cesium.Cartesian3( ...v )
const heightOf = ( v: Vec3 ) => Cesium.Cartographic.fromCartesian( cartesian( v ) ).height

export const shapeColor = ( c: ShapeColor ) => NAMED[ c ] ?? Cesium.Color.fromCssColorString( c )
// fills are see-through so the model shows through them; solids a little less
const fill = ( c?: ShapeColor ) => c ? shapeColor( c ).withAlpha( 0.35 ) : drawStyle.fill
const solid = ( c: ShapeColor ) => shapeColor( c ).withAlpha( 0.6 )

/** A point raised `by` metres along the local vertical. */
function above( p: Vec3, by: number ): Vec3 {
	const { up } = enuBasis( p )
	return [ p[0] + up[0] * by, p[1] + up[1] * by, p[2] + up[2] * by ]
}

export function entityOptions( shape: Shape ): Cesium.Entity.ConstructorOptions {
	switch ( shape.type ) {
		case 'mark':
			return { position: cartesian( shape.at ), point: drawStyle.point }
		case 'line': {
			const color = shapeColor( shape.color )
			return { polyline: { positions: shape.points.map( cartesian ), width: 2, material: color, depthFailMaterial: color.withAlpha( 0.4 ) } }
		}
		case 'label':
			return { position: cartesian( shape.at ), label: { ...drawStyle.label, text: shape.text } }
		case 'polygon':
			return { polygon: { hierarchy: new Cesium.PolygonHierarchy( shape.points.map( cartesian ) ), material: fill( shape.color ), perPositionHeight: true } }
		case 'circle':
			return { position: cartesian( shape.centre ), ellipse: { semiMajorAxis: shape.radius, semiMinorAxis: shape.radius, height: heightOf( shape.centre ),
				material: fill( shape.color ), outline: true, outlineColor: shape.color ? shapeColor( shape.color ) : drawStyle.line } }
		case 'wall': {
			const bottoms = shape.points.map( heightOf )
			return { wall: { positions: shape.points.map( cartesian ), minimumHeights: bottoms, maximumHeights: bottoms.map( h => h + shape.height ),
				material: solid( shape.color ), outline: true, outlineColor: shapeColor( shape.color ) } }
		}
		case 'sphere': {
			const r = shape.radius
			return { position: cartesian( shape.centre ), ellipsoid: { radii: new Cesium.Cartesian3( r, r, r ), material: solid( shape.color ) } }
		}
		case 'cylinder':
			// an entity's cylinder is centred on its position and stands along the local vertical there
			return { position: cartesian( above( shape.base, shape.height / 2 ) ),
				cylinder: { length: shape.height, topRadius: shape.topRadius, bottomRadius: shape.radius, material: solid( shape.color ) } }
	}
}
