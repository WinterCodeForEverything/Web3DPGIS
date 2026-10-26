<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ApiError } from '@/api/http'
import { type Preset, reconstructionsApi } from './reconstructionsApi'
import { PRESET_INFO } from './stages'

const router = useRouter()
const form = reactive( { name: '', isPublic: true, preset: 'standard' as Preset, longitude: '', latitude: '', height: '0' } )
const error = ref<ApiError | null>( null )
const busy = ref( false )

async function create() {
	busy.value = true
	error.value = null
	try {
		const placement = form.longitude !== '' && form.latitude !== ''
			? { longitude: Number( form.longitude ), latitude: Number( form.latitude ), height: Number( form.height || 0 ) } : null
		const recon = await reconstructionsApi.create( { name: form.name.trim(), is_public: form.isPublic, preset: form.preset, placement } )
		router.push( `/reconstructions/${recon.id}` )
	} catch ( e ) {
		error.value = e instanceof ApiError ? e : new ApiError( 0, String( e ) )
		busy.value = false
	}
}
</script>

<template>
	<div class="page" style="max-width: 680px">
		<h1>Reconstruct from photos</h1>
		<p class="muted">Overlapping photos of a place or an object become a textured 3D model. Name it here; you add the photos next.</p>
		<form class="card" @submit.prevent="create">
			<label class="field">Name
				<input v-model="form.name" maxlength="128" required placeholder="e.g. Campus east field, drone survey" />
				<span v-if="error?.field( 'name' )" class="error">{{ error.field( 'name' ) }}</span>
			</label>
			<fieldset class="field presets">
				<legend>Quality</legend>
				<label v-for="( info, key ) in PRESET_INFO" :key="key" class="preset" :class="{ chosen: form.preset === key }">
					<input v-model="form.preset" type="radio" name="preset" :value="key" />
					<span><strong>{{ info.label }}</strong><br /><span class="muted">{{ info.text }}</span></span>
				</label>
			</fieldset>
			<fieldset class="field placement">
				<legend>Placement on the globe (only for photos without GPS)</legend>
				<div class="row">
					<input v-model="form.longitude" type="number" step="any" min="-180" max="180" placeholder="Longitude" aria-label="Longitude" />
					<input v-model="form.latitude" type="number" step="any" min="-90" max="90" placeholder="Latitude" aria-label="Latitude" />
					<input v-model="form.height" type="number" step="any" placeholder="Height (m)" aria-label="Height in metres" />
				</div>
				<span class="muted">Drone photos with GPS place themselves. Leave this empty unless the photos have no position.</span>
				<span v-if="error?.field( 'placement' )" class="error">{{ error.field( 'placement' ) }}</span>
			</fieldset>
			<label class="check"><input v-model="form.isPublic" type="checkbox" /> Public once it is ready (anyone can view it)</label>
			<p v-if="error && !error.field( 'name' ) && !error.field( 'placement' )" class="error" role="alert">{{ error.message }}</p>
			<button class="primary" :disabled="busy">Next: add photos</button>
		</form>
	</div>
</template>

<style scoped>
.presets, .placement { border: 1px solid var(--border); border-radius: 6px; padding: 10px 12px; }
.preset { display: flex; gap: 10px; align-items: flex-start; padding: 8px; border-radius: 6px; cursor: pointer; }
.preset.chosen { background: var(--bg); }
.preset input { margin-top: 4px; }
.placement input { width: 30%; flex: 1; }
</style>
