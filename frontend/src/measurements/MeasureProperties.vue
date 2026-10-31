<script setup lang="ts">
import { ref } from 'vue'

// The property panel of one measurement: its result, and a name and annotation the user may give it (both optional).
// Shown right after a measurement is taken (isNew), and when one is picked from the list. Save is what stores a new measurement;
// closing it instead leaves the measurement listed but unsaved.
const props = defineProps<{ title: string; text: string; name: string; annotation: string; isNew: boolean; savedToAccount: boolean }>()
const emit = defineEmits<{ save: [ { name: string; annotation: string } ]; close: [] }>()

// the parent keys this component by measurement, so these start afresh for each one
const name = ref( props.name )
const annotation = ref( props.annotation )

function save() {
	emit( 'save', { name: name.value.trim(), annotation: annotation.value.trim() } )
}
</script>

<template>
	<section class="popup measure-properties" aria-label="Measurement properties">
		<header class="row">
			<strong>{{ isNew ? `New ${title.toLowerCase()} measurement` : name || title }}</strong>
			<span class="spacer" />
			<button class="icon-circle" aria-label="Close" @click="emit( 'close' )">✕</button>
		</header>
		<p class="result">{{ text }}</p>
		<label class="field">Name
			<input v-model="name" placeholder="Optional" maxlength="128" />
		</label>
		<label class="field">Annotation
			<textarea v-model="annotation" rows="3" placeholder="Optional" />
		</label>
		<p v-if="!savedToAccount" class="muted">Log in to keep these with your measurements.</p>
		<div class="row">
			<button class="small primary" @click="save">Save</button>
			<button v-if="isNew" class="small" @click="emit( 'close' )">Don't save</button>
		</div>
	</section>
</template>

<style scoped>
.popup { position: absolute; top: 12px; right: 12px; width: 300px; z-index: 3; background: var(--panel); border: 1px solid var(--ds-hairline);
	border-radius: var(--ds-rounded-lg); padding: 17px; display: flex; flex-direction: column; gap: 10px; }
header strong { font-size: 17px; font-weight: 600; letter-spacing: -0.374px; }
.result { padding: 8px 12px; border-radius: var(--ds-rounded-md); background: var(--ds-parchment); }
.field { margin: 0; }
textarea { resize: vertical; }
</style>
