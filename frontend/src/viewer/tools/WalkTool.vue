<script setup lang="ts">
import * as Cesium from 'cesium'
import { inject, onUnmounted, ref } from 'vue'
import { pickPoint, viewerKey } from '../core'
import { createSession } from '../session'

// First-person walking: WASD to move, drag to look; the camera follows the model's surface.
const ctx = inject( viewerKey )!
const viewer = ctx.viewer
const scene = viewer.scene
const camera = viewer.camera
const session = createSession( viewer, 'walk' )

const walking = ref( false )
const speed = ref( 2 )        // metres per second
const eyeHeight = ref( 1.7 )  // metres above the surface
const keys = new Set<string>()
let lastTime = 0
let dragging: Cesium.Cartesian2 | null = null

const controller = scene.screenSpaceCameraController
const savedController = { enableInputs: controller.enableInputs }
const savedRequestRender = scene.requestRenderMode

function onKey( e: KeyboardEvent ) {
	if ( ( e.target as HTMLElement ).tagName === 'INPUT' ) return
	const key = e.key.toLowerCase()
	if ( [ 'w', 'a', 's', 'd', 'q', 'e', 'arrowup', 'arrowdown', 'arrowleft', 'arrowright', 'shift' ].includes( key ) ) {
		if ( e.type === 'keydown' ) keys.add( key ); else keys.delete( key )
		e.preventDefault()
	}
}

function step( _: Cesium.Scene, time: Cesium.JulianDate ) {
	const now = Cesium.JulianDate.toDate( time ).getTime()
	const dt = lastTime ? Math.min( ( now - lastTime ) / 1000, 0.1 ) : 0
	lastTime = now
	if ( !walking.value || !dt ) return
	const run = keys.has( 'shift' ) ? 3 : 1
	const distance = speed.value * run * dt
	const forward = ( keys.has( 'w' ) || keys.has( 'arrowup' ) ? 1 : 0 ) - ( keys.has( 's' ) || keys.has( 'arrowdown' ) ? 1 : 0 )
	const sideways = ( keys.has( 'd' ) ? 1 : 0 ) - ( keys.has( 'a' ) ? 1 : 0 )
	const turn = ( keys.has( 'arrowright' ) ? 1 : 0 ) - ( keys.has( 'arrowleft' ) ? 1 : 0 )
	if ( turn ) camera.setView( { orientation: { heading: camera.heading + turn * dt * 1.2, pitch: camera.pitch, roll: 0 } } )
	// move in the horizontal plane, then put the eye back at eyeHeight above whatever is underneath
	const heading = camera.heading
	const enu = Cesium.Transforms.eastNorthUpToFixedFrame( camera.positionWC )
	const east = Cesium.Matrix4.multiplyByPointAsVector( enu, Cesium.Cartesian3.UNIT_X, new Cesium.Cartesian3() )
	const north = Cesium.Matrix4.multiplyByPointAsVector( enu, Cesium.Cartesian3.UNIT_Y, new Cesium.Cartesian3() )
	const ahead = Cesium.Cartesian3.add( Cesium.Cartesian3.multiplyByScalar( north, Math.cos( heading ), new Cesium.Cartesian3() ), Cesium.Cartesian3.multiplyByScalar( east, Math.sin( heading ), new Cesium.Cartesian3() ), new Cesium.Cartesian3() )
	const right = Cesium.Cartesian3.add( Cesium.Cartesian3.multiplyByScalar( north, -Math.sin( heading ), new Cesium.Cartesian3() ), Cesium.Cartesian3.multiplyByScalar( east, Math.cos( heading ), new Cesium.Cartesian3() ), new Cesium.Cartesian3() )
	const move = Cesium.Cartesian3.add( Cesium.Cartesian3.multiplyByScalar( ahead, forward * distance, new Cesium.Cartesian3() ), Cesium.Cartesian3.multiplyByScalar( right, sideways * distance, new Cesium.Cartesian3() ), new Cesium.Cartesian3() )
	const next = Cesium.Cartesian3.add( camera.positionWC, move, new Cesium.Cartesian3() )
	const carto = Cesium.Cartographic.fromCartesian( next )
	const climb = ( keys.has( 'e' ) ? 1 : 0 ) - ( keys.has( 'q' ) ? 1 : 0 )
	const ground = scene.sampleHeightSupported ? scene.sampleHeight( carto ) : undefined
	if ( climb ) eyeHeight.value = Math.max( 0.3, eyeHeight.value + climb * distance )
	carto.height = ground !== undefined ? ground + eyeHeight.value : carto.height + climb * distance
	camera.setView( { destination: Cesium.Cartographic.toCartesian( carto ), orientation: { heading: camera.heading, pitch: camera.pitch, roll: 0 } } )
}

const handler = session.handler()
handler.setInputAction( ( e: { position: Cesium.Cartesian2 } ) => {
	if ( walking.value ) { dragging = e.position.clone(); return }
	const p = pickPoint( viewer, e.position )
	if ( !p ) return
	const carto = Cesium.Cartographic.fromCartesian( p )
	carto.height += eyeHeight.value
	camera.setView( { destination: Cesium.Cartographic.toCartesian( carto ), orientation: { heading: camera.heading, pitch: 0, roll: 0 } } )
	controller.enableInputs = false
	scene.requestRenderMode = false
	walking.value = true
}, Cesium.ScreenSpaceEventType.LEFT_DOWN )
handler.setInputAction( ( e: { endPosition: Cesium.Cartesian2 } ) => {
	if ( !dragging ) return
	const dx = e.endPosition.x - dragging.x, dy = e.endPosition.y - dragging.y
	dragging = e.endPosition.clone()
	const pitch = Cesium.Math.clamp( camera.pitch - dy * 0.004, -1.4, 1.4 )
	camera.setView( { orientation: { heading: camera.heading + dx * 0.004, pitch, roll: 0 } } )
}, Cesium.ScreenSpaceEventType.MOUSE_MOVE )
handler.setInputAction( () => { dragging = null }, Cesium.ScreenSpaceEventType.LEFT_UP )

const removePreRender = scene.preRender.addEventListener( step )
document.addEventListener( 'keydown', onKey )
document.addEventListener( 'keyup', onKey )

function stopWalking() {
	walking.value = false
	keys.clear()
	controller.enableInputs = savedController.enableInputs
	scene.requestRenderMode = savedRequestRender
}

session.onDestroy( () => {
	stopWalking()
	removePreRender()
	document.removeEventListener( 'keydown', onKey )
	document.removeEventListener( 'keyup', onKey )
} )
onUnmounted( () => session.destroy() )
</script>

<template>
	<p v-if="!walking" class="muted">Click a spot on the model or ground to start walking there.</p>
	<template v-else>
		<p class="muted">W/S or ↑/↓ walk, A/D step sideways, ←/→ turn, Q/E lower/raise, Shift to run. Drag to look around.</p>
		<button class="small" @click="stopWalking">Stop walking</button>
	</template>
	<label class="row small">Speed <input v-model.number="speed" type="range" min="0.5" max="20" step="0.5" /> {{ speed }} m/s</label>
	<label class="row small">Eye height <input v-model.number="eyeHeight" type="number" min="0.3" step="0.1" style="width: 70px" /> m</label>
</template>

<style scoped>
p { margin: 0; font-size: 14px; }
.small { font-size: 13px; }
</style>
