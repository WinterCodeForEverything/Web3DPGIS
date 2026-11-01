<script setup lang="ts">
import { computed, inject, onMounted, onUnmounted, ref, watch } from 'vue'
import { ApiError } from '@/api/http'
import IconButton from '@/components/IconButton.vue'
import type { Vec3 } from '@/geo/geometry'
import { labelsApi } from '@/labels/labelsApi'
import type { LabelIcon, LabelKind } from '@/labels/labelsApi'
import { DEFAULT_ICON_URL } from './defaultIcon'
import { labelHostKey } from './labelHost'
import { DEFAULT_COLOR, KINDS, draftShapes, geometryFromClicks, kindInfo, labelInput } from './labelShapes'
import { labelStoreKey } from './labelStore'

// Place labels on the model (owner only): points, 2D shapes and 3D shapes, each with an icon (on the point, at the centre
// of a 2D shape, on top of a 3D one). Works in any viewer that provides a LabelHost; a label is saved as soon as its
// last point is clicked.
const host = inject( labelHostKey )!
const store = inject( labelStoreKey )!

const GROUPS = [ 'Point', '2D', '3D' ] as const
const kind = ref<LabelKind>( 'point' )
const info = computed( () => kindInfo( kind.value ) )
const iconWhere = computed( () => ( { Point: 'on the point', '2D': 'at the centre of the shape', '3D': 'on top of the shape' } )[ info.value.group ] )
const icons = ref<LabelIcon[]>( [] )
const iconId = ref<number | null>( null )
const name = ref( '' )
const color = ref( DEFAULT_COLOR )
const height = ref( 10 )
const placing = ref( false )
const error = ref( '' )
const uploading = ref( false )

onMounted( async () => {
	icons.value = ( await labelsApi.labelIcons() ).results
	iconId.value = icons.value[0]?.id ?? null
} )

async function uploadIcon( e: Event ) {
	const file = ( e.target as HTMLInputElement ).files?.[0]
	if ( !file ) return
	const form = new FormData()
	form.append( 'image', file )
	form.append( 'name', file.name.replace( /\.[^.]+$/, '' ) )
	error.value = ''
	uploading.value = true
	try {
		const icon = await labelsApi.uploadLabelIcon( form )
		icons.value.push( icon )
		iconId.value = icon.id
	} catch ( err ) {
		error.value = err instanceof ApiError ? err.message : String( err )
	} finally {
		uploading.value = false
		// choosing the same file again should upload it again
		;( e.target as HTMLInputElement ).value = ''
	}
}

// the shape being clicked, drawn as it grows
let clicks: Vec3[] = []
let cursor: Vec3 | null = null
let eraseDraft = () => {}

function redraw() {
	eraseDraft()
	eraseDraft = clicks.length ? host.draw( draftShapes( kind.value, clicks, cursor, height.value, color.value ) ) : () => {}
}

function resetDraft() {
	clicks = []
	cursor = null
	redraw()
}

async function save() {
	const g = geometryFromClicks( kind.value, clicks, height.value, color.value )
	// the finished shape stays drawn until the saved label replaces it
	eraseDraft()
	const erase = g ? host.draw( draftShapes( kind.value, clicks, null, height.value, color.value ) ) : () => {}
	eraseDraft = () => {}
	clicks = []
	cursor = null
	if ( !g ) return erase()
	try {
		await store.create( labelInput( store.modelId, name.value, iconId.value, g ) )
		host.notify( 'Label saved' )
	} catch ( err ) {
		host.notify( err instanceof ApiError ? err.message : String( err ), 'error' )
	} finally {
		erase()
	}
}

const stopListening = host.listen( {
	click( p ) {
		if ( !placing.value ) return
		clicks.push( p )
		if ( clicks.length === info.value.clicks ) void save()
		else redraw()
	},
	move( p ) {
		if ( !placing.value || !clicks.length ) return
		cursor = p
		redraw()
	},
	finish() {
		if ( !placing.value || !clicks.length ) return
		if ( info.value.clicks === undefined && clicks.length >= info.value.minimum ) void save()
		else resetDraft()
	},
} )
onUnmounted( () => {
	stopListening()
	eraseDraft()
} )

// another kind, a new height or colour, or stopping starts the shape again
watch( [ kind, placing ], resetDraft )
watch( [ height, color ], redraw )

function choose( k: LabelKind ) {
	kind.value = k
	placing.value = true
}

async function removeAll() {
	if ( !confirm( `Delete all ${store.labels.value.length} labels on this model?` ) ) return
	await store.removeAll()
}
</script>

<template>
	<div v-for="g in GROUPS" :key="g" class="group">
		<span class="muted small">{{ g === 'Point' ? 'Point' : `${g} shapes` }}</span>
		<div class="segmented" role="radiogroup" :aria-label="`${g} labels`">
			<IconButton v-for="k in KINDS.filter( k => k.group === g )" :key="k.id" :icon="k.icon" :label="k.title" tip="below"
				:class="{ on: kind === k.id }" role="radio" :aria-checked="kind === k.id" @click="choose( k.id )" />
		</div>
	</div>
	<label class="field">Label text
		<input v-model="name" placeholder="e.g. Main entrance" maxlength="128" />
	</label>
	<div class="field">
		<span>Icon <span class="muted small">{{ iconWhere }}</span></span>
		<div class="icons" role="radiogroup" aria-label="Icon">
			<button v-for="i in icons" :key="i.id" class="icon" :class="{ on: iconId === i.id }" role="radio" :aria-checked="iconId === i.id" :title="i.name" @click="iconId = i.id">
				<img :src="i.image" :alt="i.name" />
			</button>
			<button class="icon" :class="{ on: iconId === null }" role="radio" :aria-checked="iconId === null" title="Default pin" @click="iconId = null">
				<img :src="DEFAULT_ICON_URL" alt="Default pin" />
			</button>
			<label class="icon add" :class="{ busy: uploading }" title="Upload your own icon (PNG, JPEG, SVG…)">
				+<input type="file" accept="image/*" aria-label="Upload your own icon" :disabled="uploading" @change="uploadIcon" />
			</label>
		</div>
		<span class="muted small">Click + to upload your own icon; it is added to the list for your labels.</span>
	</div>
	<div v-if="kind !== 'point'" class="row">
		<label class="field">Colour <input v-model="color" type="color" class="swatch" /></label>
		<label v-if="info.hasHeight" class="field">Height (m) <input v-model.number="height" type="number" min="0.1" step="0.5" class="number" /></label>
	</div>
	<button :class="placing ? 'primary' : ''" @click="placing = !placing">{{ placing ? `Drawing ${info.title.toLowerCase()} labels… (stop)` : 'Place labels' }}</button>
	<p v-if="placing" class="muted small">{{ info.hint }}</p>
	<p v-if="error" class="error">{{ error }}</p>
	<p class="muted small">{{ store.labels.value.length }} labels on this model. Click a label to see or edit its properties.</p>
	<button v-if="store.labels.value.length" class="small danger" @click="removeAll">Delete all labels</button>
</template>

<style scoped>
.group { display: flex; flex-direction: column; gap: 4px; }
.icons { display: flex; flex-wrap: wrap; gap: 6px; }
.icons .icon { width: 40px; height: 40px; padding: 4px; justify-content: center; border-radius: var(--ds-rounded-md); }
.icons .icon.on { border: 2px solid var(--ds-primary-focus); padding: 3px; }
.icon img { max-width: 100%; max-height: 100%; }
.icons .add { position: relative; display: inline-flex; align-items: center; justify-content: center; font-size: 22px; cursor: pointer;
	border: 1px dashed var(--border); color: var(--muted); box-sizing: border-box; }
.icons .add:hover { border-color: var(--accent); }
.icons .add.busy { opacity: 0.5; cursor: progress; }
.icons .add input { position: absolute; width: 1px; height: 1px; opacity: 0; }
.swatch { width: 48px; height: 32px; padding: 2px; }
.number { width: 90px; }
.row { gap: 12px; align-items: flex-end; }
.small { font-size: 13px; }
p { margin: 0; }
</style>
