<script setup lang="ts">
import * as Cesium from 'cesium'
import { inject, onUnmounted, ref } from 'vue'
import { pickPoint, drawStyle, mapViewerKey } from '../mapViewer'
import { lineOfSight, raiseAboveSurface } from '../lineOfSight'
import { createSession } from '../toolSession'
import { formatLength } from '../../geo/geometry'

// Click an observer, then a target: green where the target can be seen, red after the first obstacle.
const ctx = inject( mapViewerKey )!
const viewer = ctx.viewer
const session = createSession( viewer, 'sightline' )
onUnmounted( () => session.destroy() )

const eyeHeight = ref( 1.6 )
const results = ref<string[]>( [] )
let observer: Cesium.Cartesian3 | null = null

function segment( a: Cesium.Cartesian3, b: Cesium.Cartesian3, color: Cesium.Color ) {
	session.entities.add( { polyline: { positions: [ a, b ], width: 3, material: color, depthFailMaterial: color.withAlpha( 0.5 ) } } )
}

const handler = session.handler()
handler.setInputAction( ( e: { position: Cesium.Cartesian2 } ) => {
	const p = pickPoint( viewer, e.position )
	if ( !p ) return
	if ( !observer ) {
		observer = raiseAboveSurface( p, eyeHeight.value )
		session.entities.add( { position: observer, point: { ...drawStyle.point, color: Cesium.Color.DEEPSKYBLUE } } )
	} else {
		const target = raiseAboveSurface( p, 0.05 )   // a hair above the surface so the target itself does not block the ray
		session.entities.add( { position: target, point: drawStyle.point } )
		const result = lineOfSight( viewer.scene, observer, target, session.entities.values )
		if ( result.visible ) {
			segment( observer, target, Cesium.Color.LIME )
			results.value.unshift( `Visible (${formatLength( Cesium.Cartesian3.distance( observer, target ) )})` )
		} else {
			segment( observer, result.obstacle!, Cesium.Color.LIME )
			segment( result.obstacle!, target, Cesium.Color.RED )
			session.entities.add( { position: result.obstacle!, point: { ...drawStyle.point, color: Cesium.Color.RED } } )
			results.value.unshift( `Blocked after ${formatLength( Cesium.Cartesian3.distance( observer, result.obstacle! ) )}` )
		}
		observer = null
	}
	viewer.scene.requestRender()
}, Cesium.ScreenSpaceEventType.LEFT_CLICK )

function clear() {
	session.clear()
	observer = null
	results.value = []
}
</script>

<template>
	<p class="muted">Click where the observer stands, then click the target.</p>
	<div class="settings">
		<label><span>Observer eye height</span><input v-model.number="eyeHeight" type="number" min="0" step="0.1" /><span class="unit">m</span></label>
	</div>
	<ol v-if="results.length" class="list"><li v-for="( r, i ) in results" :key="i"><span>{{ r }}</span></li></ol>
	<button class="small" @click="clear">Clear</button>
</template>

<style scoped>
p { margin: 0; font-size: 14px; }
.small { font-size: 13px; }
</style>
