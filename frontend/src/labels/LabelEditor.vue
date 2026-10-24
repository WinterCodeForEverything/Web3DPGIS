<script setup lang="ts">
import { inject, onMounted, onUnmounted, ref } from 'vue'
import { ApiError, api } from '@/api/client'
import type { LabelIcon } from '@/api/types'
import { labelHostKey } from './labelHost'
import { labelStoreKey } from './labelStore'

// Place labels on the model (owner only). Works in any viewer that provides a LabelHost; labels are saved immediately.
const host = inject( labelHostKey )!
const store = inject( labelStoreKey )!

const icons = ref<LabelIcon[]>( [] )
const iconId = ref<number | null>( null )
const name = ref( '' )
const placing = ref( false )
const error = ref( '' )

onMounted( async () => {
	icons.value = ( await api.labelIcons() ).results
	iconId.value = icons.value[0]?.id ?? null
} )

async function uploadIcon( e: Event ) {
	const file = ( e.target as HTMLInputElement ).files?.[0]
	if ( !file ) return
	const form = new FormData()
	form.append( 'image', file )
	form.append( 'name', file.name.replace( /\.[^.]+$/, '' ) )
	try {
		const icon = await api.uploadLabelIcon( form )
		icons.value.push( icon )
		iconId.value = icon.id
	} catch ( err ) {
		error.value = err instanceof ApiError ? err.message : String( err )
	}
}

const stopListening = host.onModelClick( async position => {
	if ( !placing.value ) return
	const removeMarker = host.showMarker( position )
	try {
		await store.create( { name: name.value, icon: iconId.value, position } )
		host.notify( 'Label saved' )
	} catch ( err ) {
		host.notify( err instanceof ApiError ? err.message : String( err ), 'error' )
	} finally {
		removeMarker()
	}
} )
onUnmounted( stopListening )

async function removeAll() {
	if ( !confirm( `Delete all ${store.labels.value.length} labels on this model?` ) ) return
	await store.removeAll()
}
</script>

<template>
	<label class="field">Label text
		<input v-model="name" placeholder="e.g. Main entrance" maxlength="128" />
	</label>
	<div class="field">
		<span>Icon</span>
		<div class="icons" role="radiogroup" aria-label="Icon">
			<button class="icon" :class="{ on: iconId === null }" role="radio" :aria-checked="iconId === null" title="Dot" @click="iconId = null">●</button>
			<button v-for="i in icons" :key="i.id" class="icon" :class="{ on: iconId === i.id }" role="radio" :aria-checked="iconId === i.id" :title="i.name" @click="iconId = i.id">
				<img :src="i.image" :alt="i.name" />
			</button>
		</div>
		<label class="muted small">Add icon <input type="file" accept="image/*" @change="uploadIcon" /></label>
	</div>
	<button :class="placing ? 'primary' : ''" @click="placing = !placing">{{ placing ? 'Click the model to place… (stop)' : 'Place labels' }}</button>
	<p v-if="error" class="error">{{ error }}</p>
	<p class="muted small">{{ store.labels.value.length }} labels on this model. Click a label to see or edit its properties.</p>
	<button v-if="store.labels.value.length" class="small danger" @click="removeAll">Delete all labels</button>
</template>

<style scoped>
.icons { display: flex; flex-wrap: wrap; gap: 6px; }
.icon { width: 40px; height: 40px; padding: 4px; justify-content: center; }
.icon.on { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent); }
.icon img { max-width: 100%; max-height: 100%; }
.small { font-size: 13px; }
p { margin: 0; }
</style>
