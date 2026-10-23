<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { ApiError, api } from '@/api/client'
import type { Model3D } from '@/api/types'
import { useAuth } from '@/stores/auth'

const auth = useAuth()
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
		const page = await api.models( {
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
	if ( models.value.some( m => m.status === 'pending' || m.status === 'processing' ) ) poll = window.setTimeout( load, 2000 )
}

function useMyLocation() {
	navigator.geolocation?.getCurrentPosition(
		pos => { near.value = `${pos.coords.longitude.toFixed( 5 )},${pos.coords.latitude.toFixed( 5 )}`; load() },
		() => { error.value = 'Could not read your location; type longitude,latitude instead.' },
	)
}

async function toggleVisible( model: Model3D ) {
	Object.assign( model, await api.updateModel( model.id, { is_visible: !model.is_visible } ) )
}

async function remove( model: Model3D ) {
	if ( !confirm( `Delete "${model.name}" and all its files, labels and flight paths?` ) ) return
	await api.deleteModel( model.id )
	load()
}

async function reprocess( model: Model3D ) {
	await api.reprocess( model.id )
	load()
}

watch( mine, load )
onMounted( load )
onUnmounted( () => window.clearTimeout( poll ) )

const place = ( m: Model3D ) => m.location ? `${m.location.longitude.toFixed( 4 )}, ${m.location.latitude.toFixed( 4 )}` : '—'
</script>

<template>
	<div class="page">
		<div class="row" style="margin-bottom: 16px">
			<h1 style="margin: 0">Models</h1>
			<span class="muted">{{ count }} found</span>
			<span class="spacer" />
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
					<span class="badge" :class="m.status">{{ m.status }}</span>
				</div>
				<div class="muted small">{{ m.owner }} · {{ place( m ) }}<template v-if="m.distance_m !== null"> · {{ ( m.distance_m / 1000 ).toFixed( 1 ) }} km away</template></div>
				<div v-if="m.status === 'pending' || m.status === 'processing'" class="small">
					<div class="progress"><div :style="{ width: ( m.latest_job?.progress ?? 0 ) + '%' }" /></div>
					<span class="muted">{{ m.latest_job?.stage === 'waiting to retry' ? m.latest_job.message : m.latest_job?.stage }}</span>
				</div>
				<div v-if="m.status === 'failed'" class="error small">{{ m.latest_job?.message }}</div>
				<div class="row actions">
					<RouterLink v-if="m.status === 'ready'" :to="`/models/${m.id}`" class="button small primary">Open</RouterLink>
					<template v-if="m.can_edit">
						<button class="small" @click="toggleVisible( m )">{{ m.is_visible ? 'Hide' : 'Show' }}</button>
						<button v-if="m.status === 'failed'" class="small" @click="reprocess( m )">Retry</button>
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
