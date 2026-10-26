<script setup lang="ts">
import { computed, onUnmounted, ref, watch } from 'vue'
import { ApiError } from '@/api/http'
import { modelsApi } from '@/api/models'
import { type Limits, type Reconstruction, reconstructionsApi } from './reconstructionsApi'
import { STAGES } from './stages'

const props = defineProps<{ reconstruction: Reconstruction; limits: Limits }>()
const emit = defineEmits<{ changed: [] }>()

const job = computed( () => props.reconstruction.latest_job )
const active = computed( () => job.value?.status === 'queued' || job.value?.status === 'running' )
const photos = computed( () => props.reconstruction.photos )
const ready = computed( () => photos.value.uploaded >= props.limits.min_photos && photos.value.pending === 0 )
const error = ref( '' )
const busy = ref( false )

/** Index in STAGES of the stage now running: the job's own stage, or tiling once the follow-up job has started. */
const current = computed( () => {
	if ( !job.value ) return -1
	if ( job.value.kind === 'tiling' ) return job.value.status === 'succeeded' ? STAGES.length : STAGES.length - 1
	const i = STAGES.findIndex( s => s.key === job.value?.stage )
	return i >= 0 ? i : job.value.stage === 'publishing the mesh' ? STAGES.length - 2 : 0
} )
const stateOf = ( i: number ) => {
	if ( !job.value || i > current.value ) return 'todo'
	if ( i < current.value ) return 'done'
	return job.value.status === 'failed' ? 'failed' : job.value.status === 'succeeded' ? 'done' : 'now'
}

// elapsed time since the reconstruction started, ticking while it runs
const now = ref( Date.now() )
const timer = window.setInterval( () => { now.value = Date.now() }, 1000 )
onUnmounted( () => window.clearInterval( timer ) )
const elapsed = computed( () => {
	const start = props.reconstruction.started_at
	if ( !start ) return ''
	const end = !active.value && job.value?.finished_at ? Date.parse( job.value.finished_at ) : now.value
	const s = Math.max( 0, Math.round( ( end - Date.parse( start ) ) / 1000 ) )
	return s >= 3600 ? `${Math.floor( s / 3600 )} h ${Math.floor( s % 3600 / 60 )} min` : `${Math.floor( s / 60 )} min ${s % 60} s`
} )

// the job's log, fetched while it is open
const showLog = ref( false )
const log = ref( '' )
let logTimer: number | undefined
async function loadLog() {
	window.clearTimeout( logTimer )
	if ( !showLog.value || !job.value ) return
	log.value = ( await modelsApi.job( job.value.id ) ).log?.split( '\n' ).slice( -40 ).join( '\n' ) ?? ''
	if ( active.value ) logTimer = window.setTimeout( loadLog, 3000 )
}
watch( [ showLog, () => job.value?.id, active ], loadLog )
onUnmounted( () => window.clearTimeout( logTimer ) )

async function act( fn: () => Promise<unknown> ) {
	busy.value = true
	error.value = ''
	try {
		await fn()
		emit( 'changed' )
	} catch ( e ) {
		error.value = e instanceof ApiError && e.status === 409 ? 'A job is already running on this reconstruction.' : e instanceof Error ? e.message : String( e )
	} finally {
		busy.value = false
	}
}
const start = () => act( () => reconstructionsApi.start( props.reconstruction.id ) )
const cancel = () => act( () => reconstructionsApi.cancel( props.reconstruction.id ) )
const retryTiling = () => act( () => modelsApi.reprocess( props.reconstruction.model ) )
</script>

<template>
	<section class="card">
		<div class="row">
			<h2>Reconstruction</h2>
			<span v-if="elapsed" class="muted">{{ elapsed }}</span>
			<span class="spacer" />
			<template v-if="reconstruction.status === 'ready'">
				<RouterLink :to="`/models/${reconstruction.model}`" class="button primary">Open in 3D viewer</RouterLink>
				<RouterLink :to="`/models/${reconstruction.model}?viewer=map`" class="button">Open on the map</RouterLink>
			</template>
		</div>

		<template v-if="!job">
			<p v-if="!ready" class="muted">Upload at least {{ limits.min_photos }} photos to start<template v-if="photos.pending"> (and wait for {{ photos.pending }} still uploading)</template>.</p>
			<p v-else class="muted">{{ photos.uploaded }} photos are ready. The model appears in the model list when it is done; you can close this page meanwhile.</p>
			<button class="primary" :disabled="!ready || busy" @click="start">Start reconstruction</button>
		</template>

		<template v-else>
			<ol class="stages">
				<li v-for="( s, i ) in STAGES" :key="s.key" :class="stateOf( i )">
					<span class="dot" aria-hidden="true" />{{ s.label }}
					<span v-if="stateOf( i ) === 'now' && job.kind === 'reconstruction'" class="muted"> {{ job.progress }}%</span>
					<span v-if="reconstruction.stats.stages?.[ s.key ] !== undefined && stateOf( i ) === 'done'" class="muted small"> · {{ Math.round( reconstruction.stats.stages[ s.key ] ) }} s</span>
				</li>
			</ol>
			<div v-if="active" class="progress"><div :style="{ width: ( job.kind === 'tiling' ? 95 : job.progress * 0.95 ) + '%' }" /></div>
			<p v-if="job.stage === 'waiting to retry'" class="muted" role="status">{{ job.message }}</p>
			<p v-if="reconstruction.resolution_shift && active" class="muted small">Running at a lower resolution after running out of memory.</p>
			<p v-if="job.status === 'failed'" class="error" role="alert">{{ job.message }}</p>

			<div class="row">
				<button v-if="active && job.kind === 'reconstruction'" class="danger" :disabled="busy || reconstruction.cancel_requested" @click="cancel">
					{{ reconstruction.cancel_requested ? 'Cancelling…' : 'Cancel' }}</button>
				<template v-if="job.status === 'failed'">
					<button v-if="job.kind === 'reconstruction'" class="primary" :disabled="busy || !ready" @click="start">Try again</button>
					<button v-else class="primary" :disabled="busy" @click="retryTiling">Build the 3D Tiles again</button>
					<span v-if="job.kind === 'reconstruction'" class="muted small">Finished stages are kept; changing photos or settings starts over.</span>
				</template>
				<span class="spacer" />
				<button class="small link" type="button" @click="showLog = !showLog">{{ showLog ? 'Hide log' : 'Show log' }}</button>
			</div>
			<pre v-if="showLog" class="log">{{ log || '…' }}</pre>
		</template>
		<p v-if="error" class="error" role="alert">{{ error }}</p>
	</section>
</template>

<style scoped>
h2 { margin: 0; font-size: 18px; }
.stages { list-style: none; padding: 0; margin: 12px 0; columns: 2; font-size: 14px; }
.stages li { padding: 3px 0; break-inside: avoid; }
.dot { display: inline-block; width: 10px; height: 10px; border-radius: 50%; border: 2px solid var(--border); margin-right: 8px; vertical-align: -1px; }
.done .dot { background: var(--ok); border-color: var(--ok); }
.now { font-weight: 600; }
.now .dot { border-color: var(--accent); background: var(--accent); animation: pulse 1.2s infinite; }
.failed { color: var(--danger); }
.failed .dot { background: var(--danger); border-color: var(--danger); }
.todo { color: var(--muted); }
@keyframes pulse { 50% { opacity: 0.35; } }
.log { background: var(--bg); padding: 10px; border-radius: 6px; max-height: 260px; overflow: auto; font-size: 12px; white-space: pre-wrap; }
.small { font-size: 13px; }
</style>
