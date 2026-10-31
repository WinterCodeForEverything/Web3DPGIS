<script setup lang="ts">
import { inject, onMounted, onUnmounted, ref, shallowRef, watch } from 'vue'
import { ApiError } from '@/api/http'
import { measurementsApi } from '@/measurements/measurementsApi'
import { useAuth } from '@/stores/auth'
import AppIcon from '@/components/AppIcon.vue'
import IconButton from '@/components/IconButton.vue'
import { ecefToGeodetic, geodeticToEcef, type Vec3 } from '@/geo/geometry'
import { measureHostKey } from './measureHost'
import { MODES, describeMeasurement, modeInfo, modeOfKind, previewShapes, segmentShapes, type Mode } from './measurementShapes'

// Measuring, shared by every viewer that provides a MeasureHost: clicking, drawing, and saving to the signed-in user's account.
const host = inject( measureHostKey )!
const auth = useAuth()

/** A finished measurement: its line in the results list and a function that removes its drawing. id is set once it is saved. */
interface Entry { key: number; id: number | null; text: string; erase: () => void }
const entries = shallowRef<Entry[]>( [] )
let nextKey = 1

const mode = ref<Mode>( 'distance' )
let points: Vec3[] = []
// what is drawn while a measurement is being clicked, replaced by the finished drawing
let draft: ( () => void )[] = []
let erasePreview = () => {}
let destroyed = false

function drawEntry( mode: Mode, pts: Vec3[] ): Entry {
	const { text, shapes } = describeMeasurement( mode, pts )
	return { key: nextKey++, id: null, text, erase: host.draw( shapes ) }
}

function resetDraft() {
	erasePreview()
	erasePreview = () => {}
	draft.forEach( erase => erase() )
	draft = []
	points = []
}

/** A measurement is complete: draw it for good, list it and save it for the signed-in user. */
async function complete() {
	const m = mode.value, pts = points
	resetDraft()
	const entry = drawEntry( m, pts )
	entries.value = [ entry, ...entries.value ]
	if ( !auth.user ) return
	try {
		const saved = await measurementsApi.createMeasurement( { model: host.model.value!.id, kind: modeInfo( m ).kind, points: pts.map( ecefToGeodetic ) } )
		entry.id = saved.id
		entries.value = [ ...entries.value ]
	} catch ( e ) {
		host.notify( `Measurement not saved: ${e instanceof ApiError ? e.message : e}`, 'error' )
	}
}

const stopListening = host.listen( {
	click( p ) {
		points.push( p )
		draft.push( host.draw( [ { type: 'mark', at: p } ] ) )
		if ( points.length === modeInfo( mode.value ).clicks ) {
			void complete()
			return
		}
		// each clicked segment of a path is drawn straight away, with its length at its middle
		if ( mode.value === 'distance' && points.length >= 2 ) draft.push( host.draw( segmentShapes( points[points.length - 2], p ) ) )
	},
	move( p ) {
		if ( !points.length || !p ) return
		erasePreview()
		erasePreview = host.draw( previewShapes( mode.value, points, p ) )
	},
	finish() {
		if ( points.length >= modeInfo( mode.value ).minimum ) void complete()
		else resetDraft()
	},
} )

watch( mode, resetDraft )

// your saved measurements on this model come back when the panel opens
onMounted( async () => {
	if ( !auth.user ) return
	try {
		const saved = ( await measurementsApi.measurements( host.model.value!.id ) ).results
		if ( destroyed ) return
		const loaded = saved.map( s => ( {
			...drawEntry( modeOfKind( s.kind ), s.points.map( p => geodeticToEcef( p.longitude, p.latitude, p.height ) ) ), id: s.id,
		} ) )
		entries.value = [ ...entries.value, ...loaded ]
	} catch ( e ) {
		host.notify( `Could not load your measurements: ${e instanceof ApiError ? e.message : e}`, 'error' )
	}
} )

onUnmounted( () => {
	destroyed = true
	stopListening()
	resetDraft()
	entries.value.forEach( e => e.erase() )
} )

async function remove( entry: Entry ) {
	try {
		if ( entry.id !== null ) await measurementsApi.deleteMeasurement( entry.id )
	} catch ( e ) {
		host.notify( e instanceof ApiError ? e.message : String( e ), 'error' )
		return
	}
	entry.erase()
	entries.value = entries.value.filter( x => x !== entry )
}

async function clearAll() {
	const saved = entries.value.filter( e => e.id !== null ).length
	if ( saved && !confirm( `Delete all ${saved} saved measurements on this model?` ) ) return
	await Promise.all( entries.value.map( remove ) )
	resetDraft()
}
</script>

<template>
	<div class="segmented" role="radiogroup" aria-label="Measurement">
		<IconButton v-for="m in MODES" :key="m.id" :icon="m.icon" :label="m.title" tip="below" :class="{ on: mode === m.id }"
			role="radio" :aria-checked="mode === m.id" @click="mode = m.id" />
	</div>
	<div class="mode">
		<strong>{{ modeInfo( mode ).title }}</strong>
		<p class="muted">{{ modeInfo( mode ).hint }}</p>
	</div>
	<ol v-if="entries.length" class="list">
		<li v-for="e in entries" :key="e.key">
			<span>{{ e.text }}</span>
			<button class="icon-only" :aria-label="e.id === null ? 'Remove measurement' : 'Delete saved measurement'" title="Delete" @click="remove( e )">
				<AppIcon name="close" :size="14" />
			</button>
		</li>
	</ol>
	<p class="muted small">{{ auth.user ? 'Measurements are saved to your account for this model.' : 'Log in to save your measurements.' }}</p>
	<button class="small" :disabled="!entries.length" @click="clearAll"><AppIcon name="trash" :size="16" />{{ entries.some( e => e.id !== null ) ? 'Delete all' : 'Clear' }}</button>
</template>

<style scoped>
.mode { display: flex; flex-direction: column; gap: 2px; }
.mode strong { font-size: 14px; font-weight: 600; letter-spacing: -0.224px; }
p { margin: 0; font-size: 14px; }
.small { font-size: 13px; }
</style>
