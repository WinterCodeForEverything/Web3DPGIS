// What a measurement shows, independent of the viewer: the line for the results list and the shapes to draw.
// Points are Earth-centred (ECEF) metres, so the same maths serves the map viewer and the 3D model viewer.
import type { IconName } from '@/icons'
import type { MeasurementKind } from '@/measurements/measurementsApi'
import {
	boundsCentre, circle, ecefToGeodetic, formatArea, formatLength, midpoint, polygonArea, polylineLength, segmentLengths,
	surfaceArea, triangle, upAt, type Vec3,
} from '@/geo/geometry'
import type { Shape } from '@/geo/shapes'

export type Mode = 'point' | 'distance' | 'area' | 'triangle' | 'circle'

export interface ModeInfo {
	id: Mode
	title: string
	icon: IconName
	hint: string
	kind: MeasurementKind
	/** Clicks that complete the measurement; undefined when it is finished with a right-click. */
	clicks?: number
	/** Fewest points a right-click can finish with. */
	minimum: number
}

export const MODES: ModeInfo[] = [
	{ id: 'point', title: 'Coordinates', icon: 'coordinates', hint: 'Click a point.', kind: 'point', clicks: 1, minimum: 1 },
	{ id: 'distance', title: 'Distance', icon: 'distance', hint: 'Click points along a path; each segment shows its length. Right-click to finish; the total is shown here.', kind: 'distance', minimum: 2 },
	{ id: 'area', title: 'Area', icon: 'area', hint: 'Click the corners; right-click to finish.', kind: 'area', minimum: 3 },
	{ id: 'triangle', title: 'Height difference', icon: 'heightDifference', hint: 'Click two points.', kind: 'height', clicks: 2, minimum: 2 },
	{ id: 'circle', title: 'Circle', icon: 'circle', hint: 'Click the centre, then a point on the edge.', kind: 'circle', clicks: 2, minimum: 2 },
]

export const modeInfo = ( id: Mode ) => MODES.find( m => m.id === id )!
export const modeOfKind = ( kind: MeasurementKind ) => MODES.find( m => m.kind === kind )!.id

/** A segment of a path being measured: the line and its length at its middle. */
export function segmentShapes( a: Vec3, b: Vec3 ): Shape[] {
	return [
		{ type: 'line', points: [ a, b ], color: 'yellow' },
		{ type: 'label', at: midpoint( a, b ), text: formatLength( segmentLengths( [ a, b ] )[0] ) },
	]
}

/** The finished drawing of a measurement and its line in the results list. */
export function describeMeasurement( mode: Mode, points: Vec3[] ): { text: string; shapes: Shape[] } {
	const shapes: Shape[] = points.map( at => ( { type: 'mark', at } ) )
	if ( mode === 'point' ) {
		// shown to two decimal places of a degree; the saved point keeps full precision
		const g = ecefToGeodetic( points[0] )
		const lon = `${Math.abs( g.longitude ).toFixed( 2 )}° ${g.longitude < 0 ? 'W' : 'E'}`
		const lat = `${Math.abs( g.latitude ).toFixed( 2 )}° ${g.latitude < 0 ? 'S' : 'N'}`
		const value = `${lon}, ${lat}, ${g.height.toFixed( 2 )} m`
		shapes.push( { type: 'label', at: points[0], text: value } )
		return { text: `Point: ${value}`, shapes }
	}
	if ( mode === 'distance' ) {
		// the viewer shows every segment with its length at its middle; the panels show only the total
		segmentLengths( points ).forEach( ( _, i ) => shapes.push( ...segmentShapes( points[i], points[i + 1] ) ) )
		return { text: `Distance: ${formatLength( polylineLength( points ) )}`, shapes }
	}
	if ( mode === 'area' ) {
		// surface area for walls and roofs, plus the horizontal footprint (plan area) when they differ
		const surface = surfaceArea( points ), plan = polygonArea( points )
		const area = Math.abs( surface - plan ) > 0.01 * surface ? `${formatArea( surface )} (plan ${formatArea( plan )})` : formatArea( surface )
		shapes.push( { type: 'polygon', points }, { type: 'line', points: [ ...points, points[0] ], color: 'yellow' } )
		shapes.push( { type: 'label', at: boundsCentre( points ), text: area } )
		return { text: `Area: ${area}`, shapes }
	}
	if ( mode === 'triangle' ) {
		const [ a, b ] = points
		const t = triangle( a, b )
		const up = upAt( a )
		const corner: Vec3 = [ a[0] + up[0] * t.vertical, a[1] + up[1] * t.vertical, a[2] + up[2] * t.vertical ]
		shapes.push(
			{ type: 'line', points: [ a, b ], color: 'yellow' },
			{ type: 'line', points: [ a, corner ], color: 'blue' },
			{ type: 'line', points: [ corner, b ], color: 'green' },
			{ type: 'label', at: midpoint( a, b ), text: `slant ${formatLength( t.slant )}` },
			{ type: 'label', at: corner, text: `vertical ${formatLength( t.vertical )} · horizontal ${formatLength( t.horizontal )}` },
		)
		return { text: `Horizontal ${formatLength( t.horizontal )}, vertical ${formatLength( t.vertical )}, slant ${formatLength( t.slant )}`, shapes }
	}
	const c = circle( points[0], points[1] )
	shapes.push( { type: 'circle', centre: points[0], radius: c.radius }, { type: 'label', at: points[0], text: `r ${formatLength( c.radius )} · ${formatArea( c.area )}` } )
	return { text: `Circle: radius ${formatLength( c.radius )}, area ${formatArea( c.area )}`, shapes }
}

/** What follows the cursor while a measurement is being clicked. */
export function previewShapes( mode: Mode, points: Vec3[], cursor: Vec3 ): Shape[] {
	if ( !points.length ) return []
	if ( mode === 'area' ) return [ { type: 'polygon', points: [ ...points, cursor ] } ]
	// a path's finished segments are already drawn, so only the stretch from the last point to the cursor is new
	return [ { type: 'line', points: mode === 'distance' ? [ points[points.length - 1], cursor ] : [ ...points, cursor ], color: 'yellow' } ]
}
