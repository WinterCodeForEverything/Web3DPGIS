<script setup lang="ts">
import { inject, ref, watch } from 'vue'
import { ApiError } from '@/api/http'
import { labelHostKey } from './labelHost'
import { labelStoreKey } from './labelStore'

// Shows the clicked label's properties; the model's owner can edit or delete it. The same popup is used by every viewer.
const host = inject( labelHostKey )!
const store = inject( labelStoreKey )!
const rows = ref<{ key: string; value: string }[]>( [] )
const editing = ref( false )
const error = ref( '' )

watch( () => store.selected.value, label => {
	editing.value = false
	error.value = ''
	rows.value = Object.entries( label?.properties ?? {} ).map( ( [ key, value ] ) => ( { key, value: typeof value === 'string' ? value : JSON.stringify( value ) } ) )
}, { immediate: true } )

async function save() {
	const label = store.selected.value
	if ( !label ) return
	const properties = Object.fromEntries( rows.value.filter( r => r.key.trim() ).map( r => [ r.key.trim(), r.value ] ) )
	try {
		await store.updateProperties( label.id, properties )
		editing.value = false
	} catch ( e ) {
		error.value = e instanceof ApiError ? e.message : String( e )
	}
}

async function remove() {
	const label = store.selected.value
	if ( !label || !confirm( `Delete label "${label.name}"?` ) ) return
	await store.remove( label.id )
	host.notify( 'Label deleted' )
}
</script>

<template>
	<section v-if="store.selected.value" class="popup glass" aria-label="Label details">
		<header class="row">
			<strong>{{ store.selected.value.name }}</strong>
			<span class="spacer" />
			<button class="icon-circle" aria-label="Close" @click="store.selected.value = null">✕</button>
		</header>
		<table v-if="!editing && rows.length" class="data">
			<tr v-for="r in rows" :key="r.key"><th>{{ r.key }}</th><td>{{ r.value }}</td></tr>
		</table>
		<p v-else-if="!editing" class="muted">No properties.</p>
		<template v-if="editing">
			<div v-for="( r, i ) in rows" :key="i" class="row">
				<input v-model="r.key" placeholder="Name" aria-label="Property name" style="width: 40%" />
				<input v-model="r.value" placeholder="Value" aria-label="Property value" style="flex: 1" />
				<button class="small" aria-label="Remove property" @click="rows.splice( i, 1 )">✕</button>
			</div>
			<button class="small" @click="rows.push( { key: '', value: '' } )">Add property</button>
		</template>
		<p v-if="error" class="error">{{ error }}</p>
		<div v-if="host.model.value?.can_edit" class="row">
			<template v-if="editing">
				<button class="small primary" @click="save">Save</button>
				<button class="small" @click="editing = false">Cancel</button>
			</template>
			<button v-else class="small" @click="editing = true">Edit properties</button>
			<span class="spacer" />
			<button class="small danger" @click="remove">Delete</button>
		</div>
	</section>
</template>

<style scoped>
.popup { position: absolute; top: 12px; right: 12px; width: 300px; z-index: 3; border: 1px solid var(--ds-hairline);
	border-radius: var(--ds-rounded-lg); padding: 17px; display: flex; flex-direction: column; gap: 8px; }
</style>
