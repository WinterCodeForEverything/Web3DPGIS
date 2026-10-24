<script setup lang="ts">
import { computed, onUnmounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError, api } from '@/api/client'
import type { Job } from '@/api/types'

const ACCEPT = '.zip,.tar,.tar.gz,.tgz,.rar,.glb,.gltf,.obj,.fbx,.dae,.3ds,.ply,.stl,.las,.laz'

const router = useRouter()
const form = reactive( { name: '', isPublic: true, longitude: '', latitude: '', height: '0', srs: '' } )
const file = ref<File | null>( null )
const thumbnail = ref<File | null>( null )
const uploadFraction = ref( 0 )
const job = ref<Job | null>( null )
const modelId = ref<number | null>( null )
const error = ref( '' )
const busy = ref( false )
let poll: number | undefined

const isPointCloud = computed( () => /\.(las|laz)$/i.test( file.value?.name ?? '' ) )
const needsPlacement = computed( () => !!file.value && !/\.(zip|tar|tgz|tar\.gz|rar|las|laz)$/i.test( file.value.name ) )

function chooseFile( e: Event, which: 'file' | 'thumbnail' ) {
	const chosen = ( e.target as HTMLInputElement ).files?.[0] ?? null
	if ( which === 'thumbnail' ) {
		thumbnail.value = chosen
		return
	}
	file.value = chosen
	if ( chosen && !form.name ) form.name = chosen.name.replace( /\.[^.]+$/, '' )
}

async function submit() {
	if ( !file.value ) return
	error.value = ''
	busy.value = true
	const data = new FormData()
	data.append( 'name', form.name.trim() || file.value.name )
	data.append( 'source_file', file.value )
	data.append( 'is_public', String( form.isPublic ) )
	if ( thumbnail.value ) data.append( 'thumbnail', thumbnail.value )
	if ( form.longitude !== '' && form.latitude !== '' ) {
		data.append( 'placement', JSON.stringify( { longitude: Number( form.longitude ), latitude: Number( form.latitude ), height: Number( form.height || 0 ) } ) )
	}
	if ( form.srs.trim() ) data.append( 'source_srs', form.srs.trim() )
	try {
		const model = await api.uploadModel( data, f => { uploadFraction.value = f } )
		modelId.value = model.id
		job.value = model.latest_job
		watchJob()
	} catch ( e ) {
		error.value = e instanceof ApiError ? e.message : String( e )
		busy.value = false
	}
}

async function watchJob() {
	if ( !job.value ) return
	job.value = await api.job( job.value.id )
	if ( job.value.status === 'succeeded' ) router.push( `/models/${modelId.value}` )
	else if ( job.value.status === 'failed' ) busy.value = false
	else poll = window.setTimeout( watchJob, 1000 )
}

onUnmounted( () => window.clearTimeout( poll ) )
</script>

<template>
	<div class="page" style="max-width: 640px">
		<h1>Upload a model</h1>
		<form class="card" @submit.prevent="submit">
			<label class="field">File
				<input type="file" :accept="ACCEPT" required @change="chooseFile( $event, 'file' )" />
				<span class="muted">3D Tiles in a zip/tar/rar archive, a mesh (glTF, GLB, OBJ, FBX, DAE, 3DS, PLY, STL) or a point cloud (LAS, LAZ).</span>
			</label>
			<label class="field">Name
				<input v-model="form.name" maxlength="128" required />
			</label>
			<label class="field">Thumbnail (optional)
				<input type="file" accept="image/*" @change="chooseFile( $event, 'thumbnail' )" />
			</label>
			<fieldset class="field placement">
				<legend>Placement on the globe {{ needsPlacement ? '(recommended for meshes)' : '(only used if the file has no position)' }}</legend>
				<div class="row">
					<input v-model="form.longitude" type="number" step="any" min="-180" max="180" placeholder="Longitude" aria-label="Longitude" />
					<input v-model="form.latitude" type="number" step="any" min="-90" max="90" placeholder="Latitude" aria-label="Latitude" />
					<input v-model="form.height" type="number" step="any" placeholder="Height (m)" aria-label="Height in metres" />
				</div>
			</fieldset>
			<label v-if="isPointCloud" class="field">Coordinate system of the point cloud
				<input v-model="form.srs" placeholder="e.g. EPSG:4547 (leave empty if stored in the file)" />
			</label>
			<label class="check"><input v-model="form.isPublic" type="checkbox" /> Public (anyone can view it)</label>

			<div v-if="busy || job" class="status">
				<template v-if="!job">
					<div class="progress"><div :style="{ width: uploadFraction * 100 + '%' }" /></div>
					<span class="muted">Uploading… {{ Math.round( uploadFraction * 100 ) }}%</span>
				</template>
				<template v-else>
					<div class="progress"><div :style="{ width: job.progress + '%' }" /></div>
					<span class="muted">Processing: {{ job.stage || job.status }} ({{ job.progress }}%)</span>
					<p v-if="job.status === 'failed'" class="error" role="alert">{{ job.message }}</p>
					<p v-else-if="job.stage === 'waiting to retry'" class="muted" role="status">{{ job.message }}</p>
				</template>
			</div>
			<p v-if="error" class="error" role="alert">{{ error }}</p>
			<button class="primary" :disabled="busy || !file">Upload</button>
		</form>
	</div>
</template>

<style scoped>
.placement { border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; }
.placement input { width: 30%; flex: 1; }
.status { margin-bottom: 14px; display: flex; flex-direction: column; gap: 6px; }
</style>
