<script setup lang="ts">
import { inject, onUnmounted, ref, shallowRef, watch } from 'vue'
import { ApiError } from '@/api/http'
import { measurementsApi } from '@/measurements/measurementsApi'
import { useAuth } from '@/stores/auth'
import AppIcon from '@/components/AppIcon.vue'
import IconButton from '@/components/IconButton.vue'
import { ecefToGeodetic, geodeticToEcef, type Vec3 } from '@/geo/geometry'
import { measureHostKey } from './measureHost'
import MeasureProperties from './MeasureProperties.vue'
import { MODES, describeMeasurement, modeInfo, previewShapes, segmentShapes, type Mode } from './measurementShapes'

// Measuring, shared by every viewer that provides a MeasureHost: clicking, drawing, and saving to the signed-in user's account.
// Nothing is measured or shown until a kind is chosen; then the list and the viewer show only your measurements of that kind.
const host = inject( measureHostKey )!
const auth = useAuth()

/**
 * A finished measurement: its line in the results list, the user's name and annotation for it, and a function that removes
 * its drawing. id is set once it is saved, which happens only when the user clicks Save in its property panel; saving is
 * that request, so a second Save made meanwhile waits for it instead of saving the measurement twice.
 */
interface Entry {
	key: number
	id: number | null
	points: Vec3[]
	text: string
	name: string
	annotation: string
	saving: Promise<void> | null
	erase: () => void
}
const entries = shallowRef<Entry[]>( [] )
let nextKey = 1

const mode = ref<Mode | null>( null )
// the measurement shown in the property panel; isNew while it is the one just measured
const selected = shallowRef<Entry | null>( null )
const isNew = ref( false )
const loading = ref( false )
let points: Vec3[] = []
// what is drawn while a measurement is being clicked, replaced by the finished drawing
let draft: ( () => void )[] = []
let erasePreview = () => {}
let destroyed = false
// a newer choice of kind makes an older load's answer stale
let loadCount = 0

function drawEntry( mode: Mode, pts: Vec3[], saved?: { id: number; name: string; annotation: string } ): Entry {
	const { text, shapes } = describeMeasurement( mode, pts )
	return { key: nextKey++, id: saved?.id ?? null, points: pts, text, name: saved?.name ?? '', annotation: saved?.annotation ?? '', saving: null, erase: host.draw( shapes ) }
}

function resetDraft() {
	erasePreview()
	erasePreview = () => {}
	draft.forEach( erase => erase() )
	draft = []
	points = []
}

function clearEntries() {
	entries.value.forEach( e => e.erase() )
	entries.value = []
	selected.value = null
}

/** A measurement is complete: draw it for good, list it and open its property panel. It is saved from there, or not at all. */
function complete() {
	const m = mode.value!, pts = points
	resetDraft()
	const entry = drawEntry( m, pts )
	entries.value = [ entry, ...entries.value ]
	selected.value = entry
	isNew.value = true
}

const stopListening = host.listen( {
	click( p ) {
		if ( !mode.value ) return
		points.push( p )
		draft.push( host.draw( [ { type: 'mark', at: p } ] ) )
		if ( points.length === modeInfo( mode.value ).clicks ) {
			complete()
			return
		}
		// each clicked segment of a path is drawn straight away, with its length at its middle
		if ( mode.value === 'distance' && points.length >= 2 ) draft.push( host.draw( segmentShapes( points[points.length - 2], p ) ) )
	},
	move( p ) {
		if ( !mode.value || !points.length || !p ) return
		erasePreview()
		erasePreview = host.draw( previewShapes( mode.value, points, p ) )
	},
	finish() {
		if ( !mode.value ) return
		if ( points.length >= modeInfo( mode.value ).minimum ) complete()
		else resetDraft()
	},
} )

// choosing a kind shows your saved measurements of that kind, and only those
watch( mode, async m => {
	resetDraft()
	clearEntries()
	const load = ++loadCount
	if ( !m || !auth.user ) return
	loading.value = true
	try {
		const saved = ( await measurementsApi.measurements( host.model.value!.id, modeInfo( m ).kind ) ).results
		if ( destroyed || load !== loadCount ) return
		// measurements taken while this loaded stay first in the list; skip any of them the server already returned
		const known = new Set( entries.value.map( e => e.id ) )
		const loaded = saved.filter( s => !known.has( s.id ) ).map( s => drawEntry( m, s.points.map( p => geodeticToEcef( p.longitude, p.latitude, p.height ) ), s ) )
		entries.value = [ ...entries.value, ...loaded ]
	} catch ( e ) {
		host.notify( `Could not load your measurements: ${e instanceof ApiError ? e.message : e}`, 'error' )
	} finally {
		if ( load === loadCount ) loading.value = false
	}
} )

onUnmounted( () => {
	destroyed = true
	stopListening()
	resetDraft()
	clearEntries()
} )

/** Show a listed measurement in the property panel and bring it to the middle of the view. */
function open( entry: Entry ) {
	selected.value = entry
	isNew.value = false
	host.focus( entry.points )
}

/** Save from the property panel: the first Save stores the measurement with its name and annotation, later ones change those. */
async function saveProperties( entry: Entry, changes: { name: string; annotation: string } ) {
	Object.assign( entry, changes )
	entries.value = [ ...entries.value ]
	selected.value = null
	if ( !auth.user ) return
	await entry.saving?.catch( () => {} )    // a Save still on its way; its failure was reported by that Save
	try {
		if ( entry.id !== null ) {
			await measurementsApi.updateMeasurement( entry.id, changes )
			return
		}
		entry.saving = measurementsApi.createMeasurement( {
			model: host.model.value!.id, kind: modeInfo( mode.value! ).kind, points: entry.points.map( ecefToGeodetic ), ...changes,
		} ).then( saved => { entry.id = saved.id } )
		await entry.saving
		entries.value = [ ...entries.value ]
	} catch ( e ) {
		host.notify( `Measurement not saved: ${e instanceof ApiError ? e.message : e}`, 'error' )
	} finally {
		entry.saving = null
	}
}

async function remove( entry: Entry ) {
	try {
		await entry.saving?.catch( () => {} )
		if ( entry.id !== null ) await measurementsApi.deleteMeasurement( entry.id )
	} catch ( e ) {
		host.notify( e instanceof ApiError ? e.message : String( e ), 'error' )
		return
	}
	entry.erase()
	entries.value = entries.value.filter( x => x !== entry )
	if ( selected.value === entry ) selected.value = null
}

async function clearAll() {
	const saved = entries.value.filter( e => e.id !== null ).length
	if ( saved && !confirm( `Delete all ${saved} saved ${modeInfo( mode.value! ).title.toLowerCase()} measurements on this model?` ) ) return
	await Promise.all( entries.value.map( remove ) )
	resetDraft()
}
</script>

<template>
	<div class="segmented" role="radiogroup" aria-label="Measurement">
		<IconButton v-for="m in MODES" :key="m.id" :icon="m.icon" :label="m.title" tip="below" :class="{ on: mode === m.id }"
			role="radio" :aria-checked="mode === m.id" @click="mode = m.id" />
	</div>
	<div v-if="mode" class="mode">
		<strong>{{ modeInfo( mode ).title }}</strong>
		<p class="muted">{{ modeInfo( mode ).hint }}</p>
	</div>
	<p v-else class="muted">Choose what to measure. Your saved measurements of that kind are shown with it.</p>
	<p v-if="loading" class="muted small">Loading your measurements…</p>
	<ol v-if="entries.length" class="list">
		<li v-for="e in entries" :key="e.key" :class="{ selected: selected === e }">
			<button class="item" :aria-label="`Show ${e.name || e.text}`" @click="open( e )">
				<strong v-if="e.name">{{ e.name }}</strong>
				<span>{{ e.text }}</span>
				<span v-if="e.annotation" class="muted note">{{ e.annotation }}</span>
				<span v-if="auth.user && e.id === null" class="muted small">Not saved</span>
			</button>
			<button class="icon-only" :aria-label="e.id === null ? 'Remove measurement' : 'Delete saved measurement'" title="Delete" @click="remove( e )">
				<AppIcon name="close" :size="14" />
			</button>
		</li>
	</ol>
	<p v-if="mode" class="muted small">{{ auth.user ? 'Save a measurement in its panel to keep it in your account. Click one to see it.' : 'Log in to save your measurements.' }}</p>
	<button v-if="entries.length" class="small" @click="clearAll"><AppIcon name="trash" :size="16" />{{ entries.some( e => e.id !== null ) ? 'Delete all' : 'Clear' }}</button>

	<!-- the property panel sits on the right of the viewer, outside the tool panel -->
	<Teleport to=".viewer-page">
		<MeasureProperties v-if="selected && mode" :key="selected.key" :title="modeInfo( mode ).title" :text="selected.text" :name="selected.name"
			:annotation="selected.annotation" :is-new="isNew" :saved-to-account="!!auth.user"
			@save="saveProperties( selected, $event )" @close="selected = null" />
	</Teleport>
</template>

<style scoped>
.mode { display: flex; flex-direction: column; gap: 2px; }
.mode strong { font-size: 14px; font-weight: 600; letter-spacing: -0.224px; }
p { margin: 0; font-size: 14px; }
.small { font-size: 13px; }
.note { display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; font-size: 13px; }
</style>
