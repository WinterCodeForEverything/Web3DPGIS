<script setup lang="ts">
import * as Cesium from 'cesium'
import { computed, inject, onUnmounted, ref, shallowRef } from 'vue'
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
const running = computed( () => progress.value !== null )
// the observer, between the first click and the second
const observer = shallowRef<Cesium.Cartesian3 | null>( null )
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
	summary.value = cancelled ? 'Stopped.' : `${seen} of ${total} rays (${Math.round( ( 100 * seen ) / total )}%) reach a visible surface within ${range.value} m.`
	progress.value = null
}

const handler = session.handler()
handler.setInputAction( ( e: { position: Cesium.Cartesian2 } ) => {
	if ( progress.value !== null ) return
	const p = pickPoint( viewer, e.position )
	if ( !p ) return
	if ( !observer.value ) {
		clear()
		observer.value = raiseAboveSurface( p, eyeHeight.value )
		session.entities.add( { position: observer.value, point: { ...drawStyle.point, color: Cesium.Color.DEEPSKYBLUE } } )
	} else {
		const from = observer.value
		observer.value = null
		session.entities.add( { polyline: { positions: [ from, p ], width: 1, material: Cesium.Color.DEEPSKYBLUE } } )
		void analyse( from, p )
	}
	scene.requestRender()
}, Cesium.ScreenSpaceEventType.LEFT_CLICK )

function clear() {
	session.entities.removeAll()
	visibleDots.removeAll()
	summary.value = ''
	observer.value = null
	scene.requestRender()
}

onUnmounted( () => {
	cancelled = true
	session.destroy()
} )
</script>

<template>
	<p class="muted">{{ observer ? 'Now click in the direction the observer looks.' : 'Click where the observer stands.' }} Green dots mark surfaces they can see.</p>
	<fieldset class="settings" :disabled="running">
		<label><span>Eye height</span><input v-model.number="eyeHeight" type="number" min="0" step="0.1" /><span class="unit">m</span></label>
		<label><span>Range</span><input v-model.number="range" type="number" min="10" step="10" /><span class="unit">m</span></label>
		<label><span>Field of view</span><input v-model.number="fov" type="number" min="10" max="360" step="5" /><span class="unit">°</span></label>
		<label><span>Rays across</span><input v-model.number="columns" type="number" min="8" max="180" /><span class="unit" /></label>
		<label><span>Rays up and down</span><input v-model.number="rows" type="number" min="3" max="40" /><span class="unit" /></label>
	</fieldset>
	<p class="muted settings-note">{{ columns * rows }} rays in all, from 60° below to 15° above level.</p>
	<div v-if="running" class="row">
		<div class="progress" style="flex: 1"><div :style="{ width: progress! * 100 + '%' }" /></div>
		<span class="muted small">{{ Math.round( progress! * 100 ) }}%</span>
		<button class="small" @click="cancelled = true">Stop</button>
	</div>
	<p v-if="summary" class="small">{{ summary }}</p>
	<button v-if="!running && ( summary || observer )" class="small" @click="clear">Clear</button>
</template>

<style scoped>
p { margin: 0; font-size: 14px; }
.small { font-size: 13px; }
fieldset { border: none; min-width: 0; }
fieldset:disabled { opacity: 0.6; }
</style>
