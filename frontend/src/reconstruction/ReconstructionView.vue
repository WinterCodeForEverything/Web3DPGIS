<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '@/api/http'
import CameraInputs from './CameraInputs.vue'
import PhotoUploader from './PhotoUploader.vue'
import { type Limits, type PhotoInfo, type Preset, type Reconstruction, reconstructionsApi } from './reconstructionsApi'
import ResultsPanel from './ResultsPanel.vue'
import RunPanel from './RunPanel.vue'
import { PRESET_INFO } from './stages'

const props = defineProps<{ id: number }>()
const router = useRouter()
const recon = ref<Reconstruction | null>( null )
const limits = ref<Limits | null>( null )
const photos = ref<PhotoInfo[]>( [] )
const error = ref( '' )
let poll: number | undefined

const active = computed( () => recon.value?.latest_job?.status === 'queued' || recon.value?.latest_job?.status === 'running' )
// nothing can change while a job runs, and a finished reconstruction is changed only by starting over
const locked = computed( () => active.value )

async function load( withPhotos = true ) {
	window.clearTimeout( poll )
	try {
		const [ r, p ] = await Promise.all( [ reconstructionsApi.get( props.id ), withPhotos ? reconstructionsApi.photos( props.id ) : Promise.resolve( photos.value ) ] )
		recon.value = r
		photos.value = p
		error.value = ''
	} catch ( e ) {
		error.value = e instanceof ApiError && e.status === 404 ? 'There is no such reconstruction, or it is not yours.' : e instanceof Error ? e.message : String( e )
		return
	}
	// follow a running job; the photo list only changes through this page, so it is not polled
	if ( active.value ) poll = window.setTimeout( () => load( false ), 2000 )
}

async function setPreset( preset: Preset ) {
	if ( !recon.value || preset === recon.value.preset ) return
	recon.value = await reconstructionsApi.update( props.id, { preset } )
}

async function remove() {
	if ( !recon.value || !confirm( `Delete "${recon.value.name}" with its photos and model?` ) ) return
	await reconstructionsApi.remove( props.id )
	router.push( '/' )
}

onMounted( async () => {
	limits.value = await reconstructionsApi.limits()
	await load()
} )
watch( () => props.id, () => load() )
onUnmounted( () => window.clearTimeout( poll ) )
</script>

<template>
	<div class="page" style="max-width: 860px">
		<p v-if="error" class="error" role="alert">{{ error }}</p>
		<template v-if="recon && limits">
			<div class="row heading">
				<h1>{{ recon.name }}</h1>
				<span class="badge" :class="recon.status">{{ recon.latest_job ? recon.status : 'draft' }}</span>
				<span class="spacer" />
				<label class="row muted">Quality
					<select :value="recon.preset" :disabled="locked" @change="setPreset( ( $event.target as HTMLSelectElement ).value as Preset )">
						<option v-for="( info, key ) in PRESET_INFO" :key="key" :value="key">{{ info.label }}</option>
					</select>
				</label>
				<button class="small danger" :disabled="locked" @click="remove">Delete</button>
			</div>
			<p class="muted">{{ PRESET_INFO[ recon.preset ].text }}</p>

			<div class="stack">
				<PhotoUploader :reconstruction-id="recon.id" :limits="limits" :photos="photos" :disabled="locked" @changed="load()" />
				<CameraInputs :reconstruction="recon" :limits="limits" :photos="photos" :disabled="locked" @changed="load()" />
				<RunPanel :reconstruction="recon" :limits="limits" @changed="load()" />
				<ResultsPanel :reconstruction="recon" />
			</div>
		</template>
		<p v-else-if="!error" class="muted">Loading…</p>
	</div>
</template>

<style scoped>
.heading h1 { margin: 0; }
.heading { margin-bottom: 4px; }
.stack { display: flex; flex-direction: column; gap: 16px; margin-top: 12px; }
</style>
