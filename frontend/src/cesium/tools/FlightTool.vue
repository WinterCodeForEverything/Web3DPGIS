<script setup lang="ts">
import * as Cesium from 'cesium'
import { inject, onMounted, onUnmounted, ref } from 'vue'
import { ApiError, api } from '@/api/client'
import type { CameraPose, FlightPath } from '@/api/types'
import { currentPose, fromGeoPoint, poseOrientation, mapViewerKey } from '../mapViewer'
import { createSession } from '../toolSession'

// Record camera tours, save them on the server, and replay them.
const ctx = inject( mapViewerKey )!
const viewer = ctx.viewer
const session = createSession( viewer, 'flight' )

const paths = ref<FlightPath[]>( [] )
const draft = ref<CameraPose[]>( [] )
const name = ref( '' )
const secondsPerStep = ref( 3 )
const playing = ref<number | null>( null )
const error = ref( '' )
let stopRequested = false

async function load() {
	paths.value = ( await api.flightPaths( ctx.model.value.id ) ).results
}
onMounted( load )

function addView() {
	draft.value.push( currentPose( viewer.camera ) )
	session.entities.add( { position: viewer.camera.positionWC.clone(), point: { pixelSize: 7, color: Cesium.Color.ORANGE } } )
	viewer.scene.requestRender()
}

async function save() {
	error.value = ''
	try {
		await api.createFlightPath( ctx.model.value.id, name.value.trim() || `Tour ${paths.value.length + 1}`, draft.value )
		draft.value = []
		name.value = ''
		session.clear()
		await load()
		ctx.notify( 'Flight path saved' )
	} catch ( e ) {
		error.value = e instanceof ApiError ? e.message : String( e )
	}
}

function flyTo( pose: CameraPose, duration: number ) {
	return new Promise<boolean>( resolve => {
		viewer.camera.flyTo( {
			destination: fromGeoPoint( pose.position ),
			orientation: poseOrientation( pose ),
			duration,
			easingFunction: Cesium.EasingFunction.LINEAR_NONE,
			complete: () => resolve( true ),
			cancel: () => resolve( false ),
		} )
	} )
}

async function play( path: FlightPath ) {
	stop()
	stopRequested = false
	playing.value = path.id
	for ( const [ i, pose ] of path.points.entries() ) {
		const finished = await flyTo( pose, i === 0 ? 1.5 : secondsPerStep.value )
		if ( !finished || stopRequested ) break
	}
	if ( playing.value === path.id ) playing.value = null
}

function stop() {
	stopRequested = true
	viewer.camera.cancelFlight()
	playing.value = null
}

async function remove( path: FlightPath ) {
	if ( !confirm( `Delete flight path "${path.name}"?` ) ) return
	await api.deleteFlightPath( path.id )
	await load()
}

onUnmounted( () => {
	stop()
	session.destroy()
} )
</script>

<template>
	<section>
		<h2>Saved tours</h2>
		<p v-if="!paths.length" class="muted">No saved tours yet.</p>
		<ul class="paths">
			<li v-for="p in paths" :key="p.id" class="row">
				<span class="spacer">{{ p.name }} <span class="muted">({{ p.points.length }} views)</span></span>
				<button v-if="playing === p.id" class="small" @click="stop">Stop</button>
				<button v-else class="small primary" @click="play( p )">Play</button>
				<button v-if="ctx.model.value.can_edit" class="small danger" :aria-label="`Delete ${p.name}`" @click="remove( p )">✕</button>
			</li>
		</ul>
		<label class="row muted small">Seconds between views <input v-model.number="secondsPerStep" type="number" min="0.5" step="0.5" style="width: 70px" /></label>
	</section>
	<section v-if="ctx.model.value.can_edit">
		<h2>Record a tour</h2>
		<p class="muted small">Move the camera, then add the view. Repeat for each stop.</p>
		<div class="row">
			<button class="small" @click="addView">Add current view</button>
			<button class="small" :disabled="!draft.length" @click="draft.pop()">Undo</button>
			<span class="muted small">{{ draft.length }} views</span>
		</div>
		<div class="row" style="margin-top: 8px">
			<input v-model="name" placeholder="Tour name" maxlength="128" style="flex: 1" />
			<button class="small primary" :disabled="draft.length < 2" @click="save">Save</button>
		</div>
		<p v-if="error" class="error">{{ error }}</p>
	</section>
</template>

<style scoped>
section { display: flex; flex-direction: column; gap: 8px; }
h2 { margin: 0; font-size: 14px; }
.paths { list-style: none; margin: 0; padding: 0; display: flex; flex-direction: column; gap: 6px; font-size: 14px; }
.small { font-size: 13px; }
p { margin: 0; }
</style>
