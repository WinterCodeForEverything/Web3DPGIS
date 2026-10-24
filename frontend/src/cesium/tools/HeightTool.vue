<script setup lang="ts">
import { inject, onUnmounted, ref, watch } from 'vue'
import { ApiError } from '@/api/http'
import { modelsApi } from '@/api/models'
import { setHeightOffset, mapViewerKey } from '../mapViewer'

// Lift or lower the model to sit correctly on the ground; owners can save the offset.
const ctx = inject( mapViewerKey )!
const saved = ctx.model.value.height_offset
const offset = ref( saved )
const busy = ref( false )
const error = ref( '' )

watch( offset, value => {
	const tileset = ctx.tileset.value
	if ( !tileset || !Number.isFinite( value ) ) return
	setHeightOffset( tileset, value )
	ctx.viewer.scene.requestRender()
} )

async function save() {
	busy.value = true
	error.value = ''
	try {
		ctx.model.value = await modelsApi.updateModel( ctx.model.value.id, { height_offset: offset.value } )
		ctx.notify( 'Height saved' )
	} catch ( e ) {
		error.value = e instanceof ApiError ? e.message : String( e )
	} finally {
		busy.value = false
	}
}

// leaving without saving puts the model back where it was
onUnmounted( () => {
	const tileset = ctx.tileset.value
	if ( tileset && offset.value !== ctx.model.value.height_offset ) {
		setHeightOffset( tileset, ctx.model.value.height_offset )
		ctx.viewer.scene.requestRender()
	}
} )
</script>

<template>
	<label class="field">Height offset (m)
		<input v-model.number="offset" type="number" step="0.1" />
	</label>
	<input v-model.number="offset" type="range" min="-200" max="200" step="0.5" aria-label="Height offset slider" />
	<p v-if="error" class="error">{{ error }}</p>
	<div class="row">
		<button class="small primary" :disabled="busy || offset === ctx.model.value.height_offset" @click="save">Save</button>
		<button class="small" @click="offset = saved">Reset</button>
	</div>
</template>
