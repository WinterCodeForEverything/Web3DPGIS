<script setup lang="ts">
import * as Cesium from 'cesium'
import { inject, onUnmounted, ref, watch } from 'vue'
import { pickPoint, style, toGeoPoint, toVec3, viewerKey } from '../core'
import { circle, formatArea, formatLength, polygonArea, polylineLength, surfaceArea, triangle } from '../geometry'
import { createSession } from '../session'

type Mode = 'point' | 'distance' | 'area' | 'triangle' | 'circle'
const MODES: { id: Mode; title: string; hint: string }[] = [
	{ id: 'point', title: 'Coordinates', hint: 'Click a point.' },
	{ id: 'distance', title: 'Distance', hint: 'Click points along a path; right-click to finish.' },
	{ id: 'area', title: 'Area', hint: 'Click the corners; right-click to finish.' },
	{ id: 'triangle', title: 'Height difference', hint: 'Click two points.' },
	{ id: 'circle', title: 'Circle', hint: 'Click the centre, then a point on the edge.' },
]

const ctx = inject( viewerKey )!
const viewer = ctx.viewer
const session = createSession( viewer, 'measure' )
onUnmounted( () => session.destroy() )

const mode = ref<Mode>( 'distance' )
const results = ref<string[]>( [] )
let points: Cesium.Cartesian3[] = []
let floating: Cesium.Cartesian3 | undefined
let preview: Cesium.Entity | undefined

// the session's handler and drawings, rebuilt whenever the mode changes
function startMeasurement() {
	points = []
	floating = undefined
	preview = undefined
}

function mark( p: Cesium.Cartesian3 ) {
	session.entities.add( { position: p, point: style.point } )
}

function text( p: Cesium.Cartesian3, value: string ) {
	session.entities.add( { position: p, label: { ...style.label, text: value } } )
}

function line( positions: Cesium.Cartesian3[], color = style.line ) {
	return session.entities.add( { polyline: { positions, width: 2, material: color, depthFailMaterial: color.withAlpha( 0.4 ) } } )
}

function livePreview() {
	if ( preview ) return
	const positions = new Cesium.CallbackProperty( () => ( floating ? [ ...points, floating ] : points ), false )
	preview = mode.value === 'area'
		? session.entities.add( { polygon: { hierarchy: new Cesium.CallbackProperty( () => new Cesium.PolygonHierarchy( floating ? [ ...points, floating ] : points ), false ), material: style.fill, perPositionHeight: true } } )
		: session.entities.add( { polyline: { positions, width: 2, material: style.line } } )
}

function finish() {
	const v = points.map( toVec3 )
	if ( mode.value === 'distance' && points.length >= 2 ) {
		const total = formatLength( polylineLength( v ) )
		text( points[points.length - 1], total )
		results.value.unshift( `Distance: ${total}` )
	} else if ( mode.value === 'area' && points.length >= 3 ) {
		// surface area for walls and roofs, plus the horizontal footprint (plan area) when they differ
		const surface = surfaceArea( v ), plan = polygonArea( v )
		const area = Math.abs( surface - plan ) > 0.01 * surface ? `${formatArea( surface )} (plan ${formatArea( plan )})` : formatArea( surface )
		session.entities.add( { polygon: { hierarchy: new Cesium.PolygonHierarchy( points ), material: style.fill, perPositionHeight: true } } )
		line( [ ...points, points[0] ] )
		text( Cesium.BoundingSphere.fromPoints( points ).center, area )
		results.value.unshift( `Area: ${area}` )
	}
	if ( preview ) session.entities.remove( preview )
	startMeasurement()
	viewer.scene.requestRender()
}

function click( p: Cesium.Cartesian3 ) {
	points.push( p )
	mark( p )
	const v = points.map( toVec3 )
	if ( mode.value === 'point' ) {
		const g = toGeoPoint( p )
		const value = `${g.longitude.toFixed( 6 )}, ${g.latitude.toFixed( 6 )}, ${g.height.toFixed( 2 )} m`
		text( p, value )
		results.value.unshift( `Point: ${value}` )
		startMeasurement()
	} else if ( mode.value === 'triangle' && points.length === 2 ) {
		const t = triangle( v[0], v[1] )
		const [ a, b ] = points
		const up = Cesium.Ellipsoid.WGS84.geodeticSurfaceNormal( a )
		const corner = Cesium.Cartesian3.add( a, Cesium.Cartesian3.multiplyByScalar( up, t.vertical, new Cesium.Cartesian3() ), new Cesium.Cartesian3() )
		line( [ a, b ] )
		line( [ a, corner ], Cesium.Color.DEEPSKYBLUE )
		line( [ corner, b ], Cesium.Color.LIME )
		text( Cesium.Cartesian3.midpoint( a, b, new Cesium.Cartesian3() ), `slant ${formatLength( t.slant )}` )
		text( corner, `vertical ${formatLength( t.vertical )} · horizontal ${formatLength( t.horizontal )}` )
		results.value.unshift( `Horizontal ${formatLength( t.horizontal )}, vertical ${formatLength( t.vertical )}, slant ${formatLength( t.slant )}` )
		if ( preview ) session.entities.remove( preview )
		startMeasurement()
	} else if ( mode.value === 'circle' && points.length === 2 ) {
		const c = circle( v[0], v[1] )
		const height = Cesium.Cartographic.fromCartesian( points[0] ).height
		session.entities.add( { position: points[0], ellipse: { semiMajorAxis: c.radius, semiMinorAxis: c.radius, height, material: style.fill, outline: true, outlineColor: style.line } } )
		text( points[0], `r ${formatLength( c.radius )} · ${formatArea( c.area )}` )
		results.value.unshift( `Circle: radius ${formatLength( c.radius )}, area ${formatArea( c.area )}` )
		if ( preview ) session.entities.remove( preview )
		startMeasurement()
	} else {
		livePreview()
	}
	viewer.scene.requestRender()
}

const handler = session.handler()
handler.setInputAction( ( e: { position: Cesium.Cartesian2 } ) => {
	const p = pickPoint( viewer, e.position )
	if ( p ) click( p )
}, Cesium.ScreenSpaceEventType.LEFT_CLICK )
handler.setInputAction( ( e: { endPosition: Cesium.Cartesian2 } ) => {
	if ( !points.length ) return
	floating = pickPoint( viewer, e.endPosition ) ?? floating
	viewer.scene.requestRender()
}, Cesium.ScreenSpaceEventType.MOUSE_MOVE )
handler.setInputAction( finish, Cesium.ScreenSpaceEventType.RIGHT_CLICK )

watch( mode, () => { if ( preview ) session.entities.remove( preview ); startMeasurement(); viewer.scene.requestRender() } )

function clearAll() {
	session.clear()
	startMeasurement()
	results.value = []
}
</script>

<template>
	<div class="modes" role="radiogroup" aria-label="Measurement">
		<button v-for="m in MODES" :key="m.id" class="small" :class="{ primary: mode === m.id }" role="radio" :aria-checked="mode === m.id" @click="mode = m.id">{{ m.title }}</button>
	</div>
	<p class="muted">{{ MODES.find( m => m.id === mode )!.hint }}</p>
	<ol v-if="results.length" class="results">
		<li v-for="( r, i ) in results" :key="i">{{ r }}</li>
	</ol>
	<button class="small" @click="clearAll">Clear</button>
</template>

<style scoped>
.modes { display: flex; flex-wrap: wrap; gap: 6px; }
.results { margin: 0; padding-left: 20px; font-size: 14px; display: flex; flex-direction: column; gap: 4px; }
p { margin: 0; font-size: 14px; }
</style>
