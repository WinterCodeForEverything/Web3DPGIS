<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ApiError } from '@/api/http'
import { CAMERA_PARAM_NAMES, matchMasks, parseCameraParams } from './checks'
import { type CameraOptions, type Limits, type PhotoInfo, type Reconstruction, reconstructionsApi } from './reconstructionsApi'

const props = defineProps<{ reconstruction: Reconstruction; limits: Limits; photos: PhotoInfo[]; disabled: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const UP_AXES = [ '+z', '-z', '+y', '-y', '+x', '-x' ]

// a copy of the options to edit; saved with one PATCH
const form = reactive( { ...props.reconstruction.options, paramsText: '', knowIntrinsics: false } as CameraOptions & { paramsText: string; knowIntrinsics: boolean } )
function reset() {
	Object.assign( form, props.reconstruction.options )
	form.gps_std = [ ...props.reconstruction.options.gps_std ] as [ number, number ]   // a copy, not the loaded array
	form.paramsText = ( props.reconstruction.options.camera_params ?? [] ).join( ', ' )
	form.knowIntrinsics = !!props.reconstruction.options.camera_params?.length || props.reconstruction.options.camera_model !== 'SIMPLE_RADIAL'
}
reset()
watch( () => props.reconstruction.options, reset )

const saving = ref( false )
const saved = ref( false )
const error = ref<ApiError | null>( null )
const params = computed( () => form.knowIntrinsics ? parseCameraParams( form.paramsText, form.camera_model, props.limits ) : { params: undefined } )
/** An error the server returned for one option ({"options": {"camera_params": [...]}}), or our own check's. */
const optionError = ( name: string ) => {
	const options = ( error.value?.data as { options?: Record<string, string[]> } | null )?.options
	return options?.[ name ]?.join( ' ' ) ?? ''
}

async function save() {
	if ( params.value.error ) return
	saving.value = true
	saved.value = false
	error.value = null
	const { paramsText, knowIntrinsics, ...options } = form
	void paramsText
	const changes: Partial<CameraOptions> = { ...options, camera_model: knowIntrinsics ? options.camera_model : 'SIMPLE_RADIAL',
		camera_params: params.value.params ?? [], fix_intrinsics: knowIntrinsics && !!params.value.params && options.fix_intrinsics,
		sift_threshold: options.sift_threshold || null }
	try {
		await reconstructionsApi.update( props.reconstruction.id, { options: changes } )
		saved.value = true
		emit( 'changed' )
	} catch ( e ) {
		error.value = e instanceof ApiError ? e : new ApiError( 0, String( e ) )
	} finally {
		saving.value = false
	}
}

// --- poses file and masks --------------------------------------------------------------

const posesResult = ref( '' )
const posesError = ref( '' )
async function uploadPoses( e: Event ) {
	const input = e.target as HTMLInputElement
	const file = input.files?.[0]
	input.value = ''
	if ( !file ) return
	posesError.value = posesResult.value = ''
	try {
		const result = await reconstructionsApi.uploadPoses( props.reconstruction.id, file )
		posesResult.value = `${result.poses} ${result.kind} read from ${file.name}.`
		emit( 'changed' )
	} catch ( err ) {
		posesError.value = err instanceof ApiError ? err.field( 'file' ) || err.message : String( err )
	}
}
async function removePoses() {
	await reconstructionsApi.removePoses( props.reconstruction.id )
	posesResult.value = ''
	emit( 'changed' )
}

const maskFraction = ref( 0 )
const maskResult = ref<{ matched: string[]; unmatched: string[] } | null>( null )
const maskError = ref( '' )
async function uploadMasks( e: Event ) {
	const input = e.target as HTMLInputElement
	const files = [ ...input.files ?? [] ]
	input.value = ''
	if ( !files.length ) return
	maskError.value = ''
	const preview = matchMasks( files, props.photos.map( p => p.name ) )
	if ( !preview.matched.length ) {
		maskResult.value = preview
		maskError.value = 'None of these masks matches a photo: name them <photo name>.png or <photo name without extension>.png.'
		return
	}
	try {
		maskResult.value = await reconstructionsApi.uploadMasks( props.reconstruction.id, files, f => { maskFraction.value = f } )
		emit( 'changed' )
	} catch ( err ) {
		maskError.value = err instanceof Error ? err.message : String( err )
	} finally {
		maskFraction.value = 0
	}
}
</script>

<template>
	<details class="card">
		<summary><h2>What do you know about the cameras? <span class="muted">(optional)</span></h2></summary>
		<p class="muted">Most photo sets need nothing here: the cameras are worked out from the photos, and GPS in the photos places the model.
			Add what you know when the photos have no GPS, or to make the result more accurate.</p>
		<fieldset :disabled="disabled">
			<h3>Camera intrinsics</h3>
			<label class="check"><input v-model="form.knowIntrinsics" type="checkbox" /> I know the camera's focal length and distortion (from a calibration)</label>
			<div v-if="form.knowIntrinsics" class="indent">
				<label class="field">Camera model
					<select v-model="form.camera_model">
						<option v-for="( count, model ) in limits.camera_models" :key="model" :value="model">{{ model }} ({{ count }} parameters)</option>
					</select>
				</label>
				<label class="field">Parameters: {{ CAMERA_PARAM_NAMES[ form.camera_model ] ?? '' }}
					<input v-model="form.paramsText" placeholder="e.g. 3000, 2000, 1500, 0.01" />
					<span v-if="params.error || optionError( 'camera_params' )" class="error">{{ params.error || optionError( 'camera_params' ) }}</span>
					<span v-else class="muted">In pixels, in COLMAP's order; distortion terms have no unit.</span>
				</label>
				<label class="check"><input v-model="form.fix_intrinsics" type="checkbox" :disabled="!params.params" /> Keep them fixed (otherwise they are refined)</label>
			</div>

			<h3>Camera positions</h3>
			<p class="muted">A text file with one photo per line: <code>name x y z</code> (camera centre) or <code>name qw qx qy qz tx ty tz</code>
				(full pose, world to camera, as COLMAP writes them), in a local frame.</p>
			<div class="row">
				<span v-if="reconstruction.has_poses" class="ok">Positions file uploaded.</span>
				<label class="button small">{{ reconstruction.has_poses ? 'Replace' : 'Upload positions file' }}<input type="file" accept=".txt,.csv,text/plain" hidden @change="uploadPoses" /></label>
				<button v-if="reconstruction.has_poses" class="small link danger" type="button" @click="removePoses">Remove</button>
			</div>
			<p v-if="posesResult" class="muted small">{{ posesResult }}</p>
			<p v-if="posesError" class="error" role="alert">{{ posesError }}</p>
			<div v-if="reconstruction.has_poses" class="row indent">
				<label class="field">Uncertainty of the positions (file units)<input v-model.number="form.prior_std" type="number" min="0.000001" step="any" /></label>
				<label class="field">File units to metres<input v-model.number="form.units_to_metres" type="number" min="0" step="any" />
					<span class="muted">e.g. 0.001 for millimetres</span></label>
				<label class="field">Up axis of the file<select v-model="form.up_axis"><option v-for="a in UP_AXES" :key="a">{{ a }}</option></select></label>
			</div>

			<h3>Masks</h3>
			<p class="muted">Black-and-white PNGs, one per photo, named <code>&lt;photo name&gt;.png</code>: black areas are ignored (background, a turntable, sky).
				{{ reconstruction.photos.masks }} of {{ reconstruction.photos.uploaded }} photos have one.</p>
			<label class="button small">Upload masks<input type="file" multiple accept="image/png" hidden @change="uploadMasks" /></label>
			<div v-if="maskFraction" class="progress" style="margin-top: 6px"><div :style="{ width: maskFraction * 100 + '%' }" /></div>
			<p v-if="maskResult" class="small muted">{{ maskResult.matched.length }} matched<template v-if="maskResult.unmatched.length">;
				no photo for {{ maskResult.unmatched.slice( 0, 5 ).join( ', ' ) }}{{ maskResult.unmatched.length > 5 ? '…' : '' }}</template></p>
			<p v-if="maskError" class="error" role="alert">{{ maskError }}</p>

			<h3>GPS</h3>
			<label class="check"><input v-model="form.ignore_gps" type="checkbox" /> Ignore the GPS in the photos</label>
			<div v-if="!form.ignore_gps" class="row indent">
				<label class="field">EXIF altitudes are relative to
					<select v-model="form.altitude_reference"><option value="sea-level">sea level (most cameras and drones)</option><option value="ellipsoid">the WGS84 ellipsoid</option></select></label>
				<label class="field">GPS accuracy, horizontal (m)<input v-model.number="form.gps_std[0]" type="number" min="0.01" step="any" /></label>
				<label class="field">vertical (m)<input v-model.number="form.gps_std[1]" type="number" min="0.01" step="any" /></label>
			</div>

			<details class="advanced">
				<summary>Advanced</summary>
				<label class="check"><input v-model="form.full_resolution" type="checkbox" /> Find features at full photo size (small or distant objects; slower)</label>
				<div class="row">
					<label class="field">SIFT threshold<input v-model.number="form.sift_threshold" type="number" min="0.00001" max="0.1" step="any" placeholder="0.00667" />
						<span class="muted">Lower finds more features in dark or low-contrast photos</span></label>
					<label class="field">Keep points seen in at least<input v-model.number="form.min_track" type="number" min="2" max="10" /> <span class="muted">photos</span></label>
					<label class="field">How "up" is found without GPS
						<select v-model="form.up_method"><option value="IMAGE-ORIENTATION">upright photos</option><option value="MANHATTAN-WORLD">lines of buildings</option></select></label>
				</div>
			</details>

			<p v-if="error && !optionError( 'camera_params' )" class="error" role="alert">{{ error.message }}</p>
			<div class="row">
				<button class="primary" type="button" :disabled="saving || !!params.error" @click="save">Save camera settings</button>
				<span v-if="saved" class="muted small">Saved.</span>
			</div>
		</fieldset>
	</details>
</template>

<style scoped>
summary h2 { display: inline; margin: 0; font-size: 18px; }
summary { cursor: pointer; }
h3 { font-size: 15px; margin: 18px 0 6px; }
fieldset { border: 0; padding: 0; margin: 0; }
.indent { margin-left: 22px; }
.row .field { flex: 1; min-width: 160px; }
.advanced { margin-top: 18px; }
.ok { color: var(--ok); }
.small { font-size: 13px; }
</style>
