// Measuring in the Cesium viewer: draws the shared measurement shapes as entities and passes on clicks.
import * as Cesium from 'cesium'
import type { MeasureHost } from '@/measurements/measureHost'
import type { LineColor, Shape } from '@/measurements/measurementShapes'
import type { Vec3 } from '../geo/geometry'
import { pickPoint, renderBriefly, drawStyle, toVec3, type MapViewerContext } from './mapViewer'
import type { ToolSession } from './toolSession'

const COLORS: Record<LineColor, Cesium.Color> = { yellow: drawStyle.line, blue: Cesium.Color.DEEPSKYBLUE, green: Cesium.Color.LIME }
const cartesian = ( v: Vec3 ) => new Cesium.Cartesian3( ...v )

function entityOptions( shape: Shape ): Cesium.Entity.ConstructorOptions {
	switch ( shape.type ) {
		case 'mark':
			return { position: cartesian( shape.at ), point: drawStyle.point }
		case 'line': {
			const color = COLORS[ shape.color ]
			return { polyline: { positions: shape.points.map( cartesian ), width: 2, material: color, depthFailMaterial: color.withAlpha( 0.4 ) } }
		}
		case 'label':
			return { position: cartesian( shape.at ), label: { ...drawStyle.label, text: shape.text } }
		case 'polygon':
			return { polygon: { hierarchy: new Cesium.PolygonHierarchy( shape.points.map( cartesian ) ), material: drawStyle.fill, perPositionHeight: true } }
		case 'circle': {
			const height = Cesium.Cartographic.fromCartesian( cartesian( shape.centre ) ).height
			return { position: cartesian( shape.centre ), ellipse: { semiMajorAxis: shape.radius, semiMinorAxis: shape.radius, height, material: drawStyle.fill, outline: true, outlineColor: drawStyle.line } }
		}
	}
}

/** The MeasureHost for the Cesium viewer; drawings and input handlers belong to the tool's session. */
export function cesiumMeasureHost( ctx: MapViewerContext, session: ToolSession ): MeasureHost {
	const viewer = ctx.viewer
	return {
		model: ctx.model,
		notify: ctx.notify,
		listen( input ) {
			const handler = session.handler()
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
			const entities = shapes.map( shape => session.entities.add( entityOptions( shape ) ) )
			// new label text needs a few more frames to show; see renderBriefly
			if ( shapes.some( s => s.type === 'label' ) ) renderBriefly( viewer )
			else viewer.scene.requestRender()
			return () => {
				for ( const e of entities ) session.entities.remove( e )
				viewer.scene.requestRender()
			}
		},
		focus( points ) {
			if ( !points.length ) return
			const sphere = Cesium.BoundingSphere.fromPoints( points.map( p => new Cesium.Cartesian3( ...p ) ) )
			// keep the heading; look down at least a little so the measurement is not edge-on
			const offset = new Cesium.HeadingPitchRange( viewer.camera.heading, Math.min( viewer.camera.pitch, -0.35 ), Math.max( sphere.radius * 4, 40 ) )
			viewer.camera.flyToBoundingSphere( sphere, { offset, duration: 0.8 } )
		},
	}
}
