<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '@/api/http'
import { modelsApi } from '@/api/models'
import type { Model3D } from '@/api/types'
import { reconstructionsApi } from '@/reconstruction/reconstructionsApi'
import { useAuth } from '@/stores/auth'

const auth = useAuth()
const router = useRouter()
const models = ref<Model3D[]>( [] )
const count = ref( 0 )
const loading = ref( false )
const error = ref( '' )
const search = ref( '' )
const mine = ref( false )
const near = ref( '' )
const radiusKm = ref( 10 )
let poll: number | undefined

async function load() {
	loading.value = true
	error.value = ''
	try {
		const page = await modelsApi.models( {
			search: search.value.trim(),
			mine: mine.value || undefined,
			near: near.value.trim() || undefined,
			radius: near.value.trim() ? radiusKm.value * 1000 : undefined,
		} )
		models.value = page.results
		count.value = page.count
	} catch ( e ) {
		error.value = e instanceof ApiError ? e.message : String( e )
	} finally {
		loading.value = false
	}
	// keep refreshing while any of the listed models is still processing
	window.clearTimeout( poll )
	if ( models.value.some( m => busy( m ) ) ) poll = window.setTimeout( load, 2000 )
}

function useMyLocation() {
	navigator.geolocation?.getCurrentPosition(
		pos => { near.value = `${pos.coords.longitude.toFixed( 5 )},${pos.coords.latitude.toFixed( 5 )}`; load() },
		() => { error.value = 'Could not read your location; type longitude,latitude instead.' },
	)
}

async function toggleVisible( model: Model3D ) {
	Object.assign( model, await modelsApi.updateModel( model.id, { is_visible: !model.is_visible } ) )
}

async function remove( model: Model3D ) {
	if ( !confirm( `Delete "${model.name}" and all its files, labels and flight paths?` ) ) return
	await modelsApi.deleteModel( model.id )
	load()
}

// a reconstruction still collecting photos: nothing uploaded or built yet, no job ever started
const isDraft = ( m: Model3D ) => m.status === 'pending' && !m.latest_job && !m.source_name
const busy = ( m: Model3D ) => !!m.latest_job && ( m.status === 'pending' || m.status === 'processing' )
const isReconstruction = ( m: Model3D ) => isDraft( m ) || m.latest_job?.kind === 'reconstruction'
const stageText = ( m: Model3D ) => m.latest_job?.stage === 'waiting to retry' ? m.latest_job.message
	: `${m.latest_job?.kind === 'reconstruction' ? 'Reconstructing' : 'Building 3D Tiles'} · ${m.latest_job?.stage ?? ''}`

async function openReconstruction( model: Model3D ) {
	const recon = await reconstructionsApi.byModel( model.id )
	if ( recon ) router.push( `/reconstructions/${recon.id}` )
	else error.value = 'No reconstruction belongs to this model.'
}

async function reprocess( model: Model3D ) {
	await modelsApi.reprocess( model.id )
	load()
}

watch( mine, load )
onMounted( load )
onUnmounted( () => window.clearTimeout( poll ) )

const formatLocation = ( m: Model3D ) => m.location ? `${m.location.longitude.toFixed( 4 )}, ${m.location.latitude.toFixed( 4 )}` : '—'
</script>

<template>
	<div class="page">
		<div class="row" style="margin-bottom: 16px">
			<h1 style="margin: 0">Models</h1>
			<span class="muted">{{ count }} found</span>
			<span class="spacer" />
			<RouterLink v-if="auth.user" to="/reconstruct" class="button">Reconstruct from photos</RouterLink>
			<RouterLink v-if="auth.user" to="/upload" class="button primary">Upload a model</RouterLink>
		</div>

		<form class="card row filters" @submit.prevent="load">
			<input v-model="search" placeholder="Search by name" aria-label="Search by name" />
			<input v-model="near" placeholder="Near: longitude,latitude" aria-label="Near longitude,latitude" />
			<label class="row muted">within <input v-model.number="radiusKm" type="number" min="1" style="width: 80px" /> km</label>
			<button type="button" @click="useMyLocation">Near me</button>
			<label v-if="auth.user" class="check" style="margin: 0"><input v-model="mine" type="checkbox" /> Only mine</label>
			<button class="primary">Search</button>
		</form>

		<p v-if="error" class="error" role="alert">{{ error }}</p>
		<p v-else-if="!loading && models.length === 0" class="muted">No models yet.</p>

		<div class="grid">
			<article v-for="m in models" :key="m.id" class="card model">
				<RouterLink :to="m.status === 'ready' ? `/models/${m.id}` : ''" class="thumb">
					<img v-if="m.thumbnail" :src="m.thumbnail" :alt="m.name" />
					<span v-else class="muted">{{ m.source_name }}</span>
				</RouterLink>
				<div class="row">
					<strong class="name">{{ m.name }}</strong>
					<span class="badge" :class="m.status">{{ isDraft( m ) ? 'draft' : m.status }}</span>
				</div>
				<div class="muted small">{{ m.owner }} · {{ formatLocation( m ) }}<template v-if="m.distance_m !== null"> · {{ ( m.distance_m / 1000 ).toFixed( 1 ) }} km away</template></div>
				<div v-if="busy( m )" class="small">
					<div class="progress"><div :style="{ width: ( m.latest_job?.progress ?? 0 ) + '%' }" /></div>
					<span class="muted">{{ stageText( m ) }}</span>
				</div>
				<div v-if="isDraft( m )" class="muted small">Reconstruction not started yet</div>
				<div v-if="m.status === 'failed'" class="error small">{{ m.latest_job?.message }}</div>
				<div class="row actions">
					<RouterLink v-if="m.status === 'ready'" :to="`/models/${m.id}`" class="button small primary">Open</RouterLink>
					<template v-if="m.can_edit">
						<button class="small" @click="toggleVisible( m )">{{ m.is_visible ? 'Hide' : 'Show' }}</button>
						<button v-if="isReconstruction( m ) && m.status !== 'ready'" class="small primary" @click="openReconstruction( m )">{{ isDraft( m ) ? 'Continue' : 'Details' }}</button>
						<button v-else-if="m.status === 'failed'" class="small" @click="reprocess( m )">Retry</button>
						<button class="small danger" @click="remove( m )">Delete</button>
					</template>
					<span v-if="!m.is_visible" class="muted small">hidden</span>
					<span v-if="!m.is_public" class="muted small">private</span>
				</div>
			</article>
		</div>
	</div>
</template>

<style scoped>
.filters { margin-bottom: 20px; padding: 12px; }
.grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); gap: 16px; }
.model { padding: 12px; display: flex; flex-direction: column; gap: 8px; }
.thumb { display: flex; align-items: center; justify-content: center; height: 140px; background: var(--bg); border-radius: 6px; overflow: hidden; }
.thumb img { width: 100%; height: 100%; object-fit: cover; }
.name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.small { font-size: 13px; }
.actions { margin-top: auto; }
</style>
