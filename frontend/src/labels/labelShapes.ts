// The kinds of label and their geometry, independent of the viewer: how clicks become a label, what a label draws and
// how it is described. Points are Earth-centred (ECEF) metres, as in measurements; the API stores longitude/latitude/height.
import type { IconName } from '@/icons'
import type { GeoPoint } from '@/api/types'
import type { Label, LabelInput, LabelKind } from '@/labels/labelsApi'
import {
	boundsCentre, distance, ecefToGeodetic, enuBasis, formatArea, formatLength, geodeticToEcef, midpoint, polygonArea, polylineLength,
	triangle, type Vec3,
} from '@/geo/geometry'
import type { Shape, ShapeColor } from '@/geo/shapes'

export interface KindInfo {
	id: LabelKind
	title: string
	icon: IconName
	group: 'Point' | '2D' | '3D'
	hint: string
	/** Clicks that complete the label; undefined when it is finished with a right-click. */
	clicks?: number
	/** Fewest clicks a right-click can finish with. */
	minimum: number
	/** The panel asks for a height (walls, cylinders, cones). */
	hasHeight?: boolean
}

const VERTICES = 'Right-click to finish.'
const ROUND = 'Click the centre, then a point on the edge.'

export const KINDS: KindInfo[] = [
	{ id: 'point', title: 'Point', icon: 'pin', group: 'Point', hint: 'Click the model to place a label.', clicks: 1, minimum: 1 },
	{ id: 'polyline', title: 'Polyline', icon: 'polyline', group: '2D', hint: `Click points along the line. ${VERTICES}`, minimum: 2 },
	{ id: 'polygon', title: 'Polygon', icon: 'polygon', group: '2D', hint: `Click the corners. ${VERTICES}`, minimum: 3 },
	{ id: 'circle', title: 'Circle', icon: 'circle', group: '2D', hint: ROUND, clicks: 2, minimum: 2 },
	{ id: 'wall', title: 'Wall', icon: 'wall', group: '3D', hint: `Click points along the foot of the wall. ${VERTICES}`, minimum: 2, hasHeight: true },
	{ id: 'sphere', title: 'Sphere', icon: 'sphere', group: '3D', hint: ROUND, clicks: 2, minimum: 2 },
	{ id: 'cylinder', title: 'Cylinder', icon: 'cylinder', group: '3D', hint: `Click the centre of the base, then a point on its edge.`, clicks: 2, minimum: 2, hasHeight: true },
	{ id: 'cone', title: 'Cone', icon: 'cone', group: '3D', hint: `Click the centre of the base, then a point on its edge.`, clicks: 2, minimum: 2, hasHeight: true },
]

export const kindInfo = ( id: LabelKind ) => KINDS.find( k => k.id === id )!
export const DEFAULT_COLOR = '#1e90ff'

const toGeo = ( p: Vec3 ): GeoPoint => ecefToGeodetic( p )
const toEcef = ( p: GeoPoint ): Vec3 => geodeticToEcef( p.longitude, p.latitude, p.height )

function above( p: Vec3, by: number ): Vec3 {
	const { up } = enuBasis( p )
	return [ p[0] + up[0] * by, p[1] + up[1] * by, p[2] + up[2] * by ]
}

/** The size a round label gets from its two clicks: the horizontal distance, or the straight-line one for a sphere. */
const radiusOf = ( kind: LabelKind, centre: Vec3, edge: Vec3 ) => kind === 'sphere' ? distance( centre, edge ) : triangle( centre, edge ).horizontal

/** A label's shape in ECEF, as the viewers and the maths need it. */
export interface LabelGeometry {
	kind: LabelKind
	position: Vec3
	points: Vec3[]
	radius: number
	height: number
	color: ShapeColor
}

export function labelGeometry( label: Pick<Label, 'kind' | 'position' | 'points' | 'radius' | 'height' | 'color'> ): LabelGeometry {
	return {
		kind: label.kind, position: toEcef( label.position ), points: label.points.map( toEcef ),
		radius: label.radius ?? 0, height: label.height ?? 0, color: ( label.color || DEFAULT_COLOR ) as ShapeColor,
	}
}

/**
 * The shape the clicks so far make; with a cursor, the shape as it would be if the cursor were clicked next.
 * Null while there are too few points to show anything.
 */
export function geometryFromClicks( kind: LabelKind, clicks: Vec3[], height: number, color: string ): LabelGeometry | null {
	const base = { kind, height: kindInfo( kind ).hasHeight ? height : 0, color: color as ShapeColor }
	if ( kind === 'point' ) return clicks.length ? { ...base, position: clicks[0], points: [], radius: 0 } : null
	if ( kindInfo( kind ).clicks === 2 ) {
		if ( clicks.length < 2 ) return null
		return { ...base, position: clicks[0], points: [], radius: radiusOf( kind, clicks[0], clicks[1] ) }
	}
	if ( clicks.length < 2 ) return null
	return { ...base, position: boundsCentre( clicks ), points: clicks, radius: 0 }
}

/** What to send to the API to save a finished label. */
export function labelInput( model: number, name: string, icon: number | null, g: LabelGeometry ): LabelInput {
	const input: LabelInput = { model, kind: g.kind, name: name.trim() || kindInfo( g.kind ).title, icon: g.kind === 'point' ? icon : null }
	if ( g.points.length ) input.points = g.points.map( toGeo )
	else input.position = toGeo( g.position )
	if ( g.kind !== 'point' ) input.color = g.color
	if ( g.radius > 0 ) input.radius = g.radius
	if ( kindInfo( g.kind ).hasHeight ) input.height = g.height
	return input
}

/** Where a label's name goes: above the top of a shape, so it is not hidden inside it. */
export function nameAnchor( g: LabelGeometry ): Vec3 {
	switch ( g.kind ) {
		case 'point': case 'circle': case 'polygon': return g.position
		case 'polyline': return g.points.length === 2 ? midpoint( g.points[0], g.points[1] ) : g.points[Math.floor( g.points.length / 2 )]
		case 'wall': return above( g.position, g.height )
		case 'sphere': return above( g.position, g.radius )
		case 'cylinder': case 'cone': return above( g.position, g.height )
	}
}

/** The drawing of a label's shape, without its name; a point label has none (the viewer draws its icon or dot). */
export function shapesOf( g: LabelGeometry ): Shape[] {
	const color = g.color
	switch ( g.kind ) {
		case 'point': return []
		case 'polyline': return [ { type: 'line', points: g.points, color } ]
		case 'polygon': return [ { type: 'polygon', points: g.points, color }, { type: 'line', points: [ ...g.points, g.points[0] ], color } ]
		case 'circle': return [ { type: 'circle', centre: g.position, radius: g.radius, color } ]
		case 'wall': return [ { type: 'wall', points: g.points, height: g.height, color } ]
		case 'sphere': return [ { type: 'sphere', centre: g.position, radius: g.radius, color } ]
		case 'cylinder': return [ { type: 'cylinder', base: g.position, radius: g.radius, topRadius: g.radius, height: g.height, color } ]
		case 'cone': return [ { type: 'cylinder', base: g.position, radius: g.radius, topRadius: 0, height: g.height, color } ]
	}
}

/** The drawing while a label is being clicked: the clicked points, and the shape as it would be with the cursor clicked. */
export function draftShapes( kind: LabelKind, clicks: Vec3[], cursor: Vec3 | null, height: number, color: string ): Shape[] {
	const marks: Shape[] = clicks.map( at => ( { type: 'mark', at } ) )
	const g = geometryFromClicks( kind, cursor ? [ ...clicks, cursor ] : clicks, height, color )
	if ( !g || kind === 'point' ) return marks
	// a polygon with two corners is still a line
	if ( kind === 'polygon' && g.points.length < 3 ) return [ ...marks, { type: 'line', points: g.points, color: g.color } ]
	return [ ...marks, ...shapesOf( g ) ]
}

/** One line about a label's shape and size, e.g. "Cylinder · radius 3.00 m · height 8.00 m". */
export function describeLabel( g: LabelGeometry ): string {
	const title = kindInfo( g.kind ).title
	switch ( g.kind ) {
		case 'point': return title
		case 'polyline': return `${title} · ${formatLength( polylineLength( g.points ) )}`
		case 'polygon': return `${title} · ${formatArea( polygonArea( g.points ) )}`
		case 'wall': return `${title} · ${formatLength( polylineLength( g.points ) )} long · height ${formatLength( g.height )}`
		case 'circle': case 'sphere': return `${title} · radius ${formatLength( g.radius )}`
		case 'cylinder': case 'cone': return `${title} · radius ${formatLength( g.radius )} · height ${formatLength( g.height )}`
	}
}
