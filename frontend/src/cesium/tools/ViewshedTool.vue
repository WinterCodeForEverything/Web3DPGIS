<script setup lang="ts">
import * as Cesium from 'cesium'
import { inject, onUnmounted, ref } from 'vue'
import { pickPoint, drawStyle, mapViewerKey } from '../mapViewer'
import { firstHit, raiseAboveSurface } from '../lineOfSight'
import { createSession } from '../toolSession'

// Sampled viewshed: rays fan out from the observer; each first hit within range is a surface the observer can see.
const ctx = inject( mapViewerKey )!
const viewer = ctx.viewer
const scene = viewer.scene
const session = createSession( viewer, 'viewshed' )

const eyeHeight = ref( 1.6 )
const range = ref( 150 )          // metres
const fov = ref( 90 )             // horizontal field of view, degrees
const columns = ref( 48 )
const rows = ref( 12 )
const progress = ref<number | null>( null )
const summary = ref( '' )
let observer: Cesium.Cartesian3 | null = null
let cancelled = false

const visibleDots = session.addPrimitive( new Cesium.PointPrimitiveCollection() )

async function analyse( from: Cesium.Cartesian3, towards: Cesium.Cartesian3 ) {
	visibleDots.removeAll()
	const enu = Cesium.Transforms.eastNorthUpToFixedFrame( from )
	const toLocal = Cesium.Matrix4.inverse( enu, new Cesium.Matrix4() )
	const local = Cesium.Matrix4.multiplyByPoint( toLocal, towards, new Cesium.Cartesian3() )
	const heading = Math.atan2( local.x, local.y )
	const half = Cesium.Math.toRadians( fov.value ) / 2
	const pitches = Array.from( { length: rows.value }, ( _, i ) => Cesium.Math.toRadians( -60 + ( 75 * i ) / Math.max( rows.value - 1, 1 ) ) )
	const total = columns.value * rows.value
	let done = 0, seen = 0
	cancelled = false
	progress.value = 0
	for ( let c = 0; c < columns.value && !cancelled; c++ ) {
		const h = heading - half + ( 2 * half * c ) / Math.max( columns.value - 1, 1 )
		for ( const pitch of pitches ) {
			const dirLocal = new Cesium.Cartesian3( Math.sin( h ) * Math.cos( pitch ), Math.cos( h ) * Math.cos( pitch ), Math.sin( pitch ) )
			const dir = Cesium.Matrix4.multiplyByPointAsVector( enu, dirLocal, new Cesium.Cartesian3() )
			const hit = firstHit( scene, from, dir, session.entities.values )
			if ( hit && Cesium.Cartesian3.distance( from, hit ) <= range.value ) {
				visibleDots.add( { position: hit, pixelSize: 6, color: Cesium.Color.LIME.withAlpha( 0.85 ), disableDepthTestDistance: 0 } )
				seen++
			}
			done++
		}
		progress.value = done / total
		scene.requestRender()
		await new Promise( r => requestAnimationFrame( r ) )   // keep the page responsive
	}
	summary.value = cancelled ? 'Stopped.' : `${seen} of ${total} sampled directions hit a visible surface within ${range.value} m.`
	progress.value = null
}

const handler = session.handler()
handler.setInputAction( ( e: { position: Cesium.Cartesian2 } ) => {
	if ( progress.value !== null ) return
	const p = pickPoint( viewer, e.position )
	if ( !p ) return
	if ( !observer ) {
		session.entities.removeAll()
		visibleDots.removeAll()
		summary.value = ''
		observer = raiseAboveSurface( p, eyeHeight.value )
		session.entities.add( { position: observer, point: { ...drawStyle.point, color: Cesium.Color.DEEPSKYBLUE } } )
	} else {
		const from = observer
		observer = null
		session.entities.add( { polyline: { positions: [ from, p ], width: 1, material: Cesium.Color.DEEPSKYBLUE } } )
		void analyse( from, p )
	}
	scene.requestRender()
}, Cesium.ScreenSpaceEventType.LEFT_CLICK )

onUnmounted( () => {
	cancelled = true
	session.destroy()
} )
</script>

<template>
	<p class="muted">Click the observer's position, then click in the direction they look. Green dots mark surfaces they can see.</p>
	<label class="row small">Eye height <input v-model.number="eyeHeight" type="number" min="0" step="0.1" style="width: 70px" /> m</label>
	<label class="row small">Range <input v-model.number="range" type="number" min="10" step="10" style="width: 80px" /> m</label>
	<label class="row small">Field of view <input v-model.number="fov" type="number" min="10" max="360" step="5" style="width: 70px" /> °</label>
	<label class="row small">Samples <input v-model.number="columns" type="number" min="8" max="180" style="width: 60px" /> × <input v-model.number="rows" type="number" min="3" max="40" style="width: 55px" /></label>
	<div v-if="progress !== null" class="row">
		<div class="progress" style="flex: 1"><div :style="{ width: progress * 100 + '%' }" /></div>
		<button class="small" @click="cancelled = true">Stop</button>
	</div>
	<p v-if="summary" class="small">{{ summary }}</p>
	<button class="small" @click="session.entities.removeAll(); visibleDots.removeAll(); summary = ''; viewer.scene.requestRender()">Clear</button>
</template>

<style scoped>
p { margin: 0; font-size: 14px; }
.small { font-size: 13px; }
</style>
