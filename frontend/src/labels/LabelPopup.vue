<script setup lang="ts">
import { computed, inject, nextTick, ref, watch } from 'vue'
import { ApiError } from '@/api/http'
import { labelHostKey } from './labelHost'
import { describeLabel, labelGeometry } from './labelShapes'
import { labelStoreKey } from './labelStore'

// Shows the clicked label's shape and properties; the model's owner can rename, edit, recolour or delete it. It opens ready
// for editing right after a label is added, so the label can be named; the name is optional and keeps its default
// ("Circle 3") when left empty. The same popup is used by every viewer.
const host = inject( labelHostKey )!
const store = inject( labelStoreKey )!
const rows = ref<{ key: string; value: string }[]>( [] )
const name = ref( '' )
const nameInput = ref<HTMLInputElement>()
const editing = ref( false )
const error = ref( '' )

function startEditing() {
	name.value = store.selected.value?.name ?? ''
	editing.value = true
	// ready to type a name over the default one
	void nextTick( () => nameInput.value?.select() )
}

watch( () => store.selected.value, label => {
	editing.value = false
	error.value = ''
	rows.value = Object.entries( label?.properties ?? {} ).map( ( [ key, value ] ) => ( { key, value: typeof value === 'string' ? value : JSON.stringify( value ) } ) )
	if ( label && label.id === store.justCreated.value ) {
		store.justCreated.value = null
		startEditing()
	}
}, { immediate: true } )

const summary = computed( () => store.selected.value ? describeLabel( labelGeometry( store.selected.value ) ) : '' )

async function recolour( e: Event ) {
	const label = store.selected.value
	if ( !label ) return
	try {
		await store.updateColor( label.id, ( e.target as HTMLInputElement ).value )
	} catch ( err ) {
		error.value = err instanceof ApiError ? err.message : String( err )
	}
}

async function save() {
	const label = store.selected.value
	if ( !label ) return
	const properties = Object.fromEntries( rows.value.filter( r => r.key.trim() ).map( r => [ r.key.trim(), r.value ] ) )
	try {
		// an empty name keeps the one the label has
		await store.update( label.id, { name: name.value.trim() || label.name, properties } )
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
		<div class="row">
			<span class="muted small">{{ summary }}</span>
			<span class="spacer" />
			<input v-if="store.selected.value.kind !== 'point' && host.model.value?.can_edit" type="color" class="swatch"
				:value="store.selected.value.color" aria-label="Colour" title="Colour" @change="recolour" />
		</div>
		<table v-if="!editing && rows.length" class="data">
			<tr v-for="r in rows" :key="r.key"><th>{{ r.key }}</th><td>{{ r.value }}</td></tr>
		</table>
		<p v-else-if="!editing" class="muted">No properties.</p>
		<template v-if="editing">
			<label class="field">Name <span class="muted small">(optional)</span>
				<input ref="nameInput" v-model="name" :placeholder="store.selected.value.name" maxlength="128" aria-label="Label name" @keydown.enter="save" />
			</label>
			<span class="muted small">Properties</span>
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
			<button v-else class="small" @click="startEditing">Edit properties</button>
			<span class="spacer" />
			<button class="small danger" @click="remove">Delete</button>
		</div>
	</section>
</template>

<style scoped>
.popup { position: absolute; top: 12px; right: 12px; width: 300px; z-index: 3; border: 1px solid var(--ds-hairline);
	border-radius: var(--ds-rounded-lg); padding: 17px; display: flex; flex-direction: column; gap: 8px; }
.swatch { width: 36px; height: 26px; padding: 2px; }
.small { font-size: 13px; }
</style>
