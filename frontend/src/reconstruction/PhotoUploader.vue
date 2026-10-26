<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import { ApiError } from '@/api/http'
import { choosePhotos, formatBytes, type Rejected } from './checks'
import { type Limits, type PhotoInfo, putToBucket, reconstructionsApi } from './reconstructionsApi'
import { UploadQueue } from './uploadQueue'

const props = defineProps<{ reconstructionId: number; limits: Limits; photos: PhotoInfo[]; disabled: boolean }>()
const emit = defineEmits<{ changed: [] }>()

const send = async ( item: { file: File }, onProgress: ( f: number ) => void ) => {
	const id = props.reconstructionId
	if ( !props.limits.direct_upload ) {
		await reconstructionsApi.uploadPhoto( id, item.file, onProgress )
		return
	}
	// S3 storage: the photo goes straight into the bucket, then the server checks it arrived
	const [ target ] = ( await reconstructionsApi.presignPhotos( id, [ item.file ] ) ).uploads
	await putToBucket( target.url, item.file, target.content_type, onProgress )
	const result = await reconstructionsApi.confirmPhotos( id, [ item.file.name ] )
	if ( !result.confirmed.length ) throw new ApiError( 0, result.too_large.length ? 'Too large for this server' : 'Storage did not receive it' )
}
const queue = reactive( new UploadQueue( send, { concurrency: 4 } ) ) as UploadQueue
const rejected = ref<Rejected[]>( [] )
const dragging = ref( false )
const error = ref( '' )

const onServer = computed( () => props.photos.filter( p => p.uploaded ) )
const totalSize = computed( () => onServer.value.reduce( ( s, p ) => s + p.size, 0 ) )
const showList = ref( false )

async function addFiles( files: File[] ) {
	if ( props.disabled || !files.length ) return
	const { accepted, rejected: left } = choosePhotos( files, props.limits, props.photos )
	rejected.value = left
	queue.add( accepted, new Map( onServer.value.map( p => [ p.name, p.size ] ) ) )
	await run()
}

async function run() {
	await queue.run()
	emit( 'changed' )
}

function retryFailed() {
	queue.retryFailed()
	run()
}

function picked( e: Event ) {
	const input = e.target as HTMLInputElement
	addFiles( [ ...input.files ?? [] ] )
	input.value = ''
}

async function dropped( e: DragEvent ) {
	dragging.value = false
	const items = [ ...e.dataTransfer?.items ?? [] ]
	const entries = items.map( i => i.webkitGetAsEntry?.() ).filter( ( x ): x is FileSystemEntry => !!x )
	addFiles( entries.length ? await filesIn( entries ) : [ ...e.dataTransfer?.files ?? [] ] )
}

/** Every file inside dropped files and folders (folders are read recursively). */
async function filesIn( entries: FileSystemEntry[] ): Promise<File[]> {
	const out: File[] = []
	for ( const entry of entries ) {
		if ( entry.isFile ) {
			out.push( await new Promise<File>( ( resolve, reject ) => ( entry as FileSystemFileEntry ).file( resolve, reject ) ) )
		} else if ( entry.isDirectory ) {
			const reader = ( entry as FileSystemDirectoryEntry ).createReader()
			// readEntries returns at most ~100 entries per call
			for ( let batch: FileSystemEntry[]; ( batch = await new Promise( ( r, j ) => reader.readEntries( r, j ) ) ).length; ) out.push( ...await filesIn( batch ) )
		}
	}
	return out
}

async function removePhoto( name: string ) {
	error.value = ''
	try {
		await reconstructionsApi.removePhotos( props.reconstructionId, [ name ] )
		queue.remove( name )
		emit( 'changed' )
	} catch ( e ) {
		error.value = e instanceof Error ? e.message : String( e )
	}
}

const stateText: Record<string, string> = { waiting: 'waiting', uploading: 'uploading', done: 'uploaded', failed: 'failed', skipped: 'already uploaded' }
</script>

<template>
	<section class="card">
		<div class="row">
			<h2>Photos</h2>
			<span class="muted">{{ onServer.length }} uploaded · {{ formatBytes( totalSize ) }}</span>
			<span class="spacer" />
			<button v-if="onServer.length" class="small link" type="button" @click="showList = !showList">{{ showList ? 'Hide list' : 'Show list' }}</button>
		</div>
		<p class="muted">
			{{ limits.min_photos }} to {{ limits.max_photos }} overlapping photos, up to {{ formatBytes( limits.max_photo_size ) }} each
			({{ limits.photo_types.join( ', ' ) }}). Neighbouring photos should overlap by about 60%.
		</p>

		<div class="drop" :class="{ dragging, disabled }" @dragover.prevent="dragging = !disabled" @dragleave="dragging = false" @drop.prevent="dropped">
			<span>Drop photos or a folder here, or</span>
			<label class="button small" :class="{ disabled }">Choose photos<input type="file" multiple accept="image/jpeg,image/png,image/tiff" :disabled="disabled" hidden @change="picked" /></label>
			<label class="button small" :class="{ disabled }">Choose a folder<input type="file" webkitdirectory :disabled="disabled" hidden @change="picked" /></label>
		</div>
		<p v-if="disabled" class="muted small">Photos cannot change while the reconstruction runs.</p>

		<div v-if="queue.items.length" class="queue">
			<div class="progress"><div :style="{ width: queue.progress * 100 + '%' }" /></div>
			<div class="row small">
				<span>{{ queue.counts.done }} of {{ queue.counts.total }} done</span>
				<span v-if="queue.counts.uploading" class="muted">· {{ queue.counts.uploading }} uploading</span>
				<span v-if="queue.counts.failed" class="error">· {{ queue.counts.failed }} failed</span>
				<span class="spacer" />
				<button v-if="queue.counts.failed && !queue.running" class="small" type="button" @click="retryFailed">Retry failed</button>
			</div>
			<ul class="items">
				<li v-for="item in queue.items.filter( i => i.state !== 'done' && i.state !== 'skipped' )" :key="item.name" class="row small">
					<span class="name">{{ item.name }}</span>
					<span v-if="item.state === 'uploading'" class="muted">{{ Math.round( item.progress * 100 ) }}%</span>
					<span v-else :class="item.state === 'failed' ? 'error' : 'muted'">{{ stateText[ item.state ] }}<template v-if="item.error">: {{ item.error }}</template></span>
				</li>
			</ul>
			<p v-if="!queue.running && queue.counts.waiting === 0 && queue.counts.failed === 0" class="muted small">
				All chosen photos are on the server. After a reload, choose the same photos again to upload only the missing ones.
			</p>
		</div>

		<details v-if="rejected.length" class="small">
			<summary class="error">{{ rejected.length }} files left out</summary>
			<ul><li v-for="r in rejected" :key="r.name">{{ r.name }}: {{ r.reason }}</li></ul>
		</details>

		<ul v-if="showList" class="items server">
			<li v-for="p in onServer" :key="p.name" class="row small">
				<span class="name">{{ p.name }}</span>
				<span class="muted">{{ formatBytes( p.size ) }}<template v-if="p.mask"> · mask</template></span>
				<button v-if="!disabled" class="small link danger" type="button" :aria-label="`Remove ${p.name}`" @click="removePhoto( p.name )">Remove</button>
			</li>
		</ul>
		<p v-if="error" class="error" role="alert">{{ error }}</p>
	</section>
</template>

<style scoped>
h2 { margin: 0; font-size: 18px; }
.drop { border: 2px dashed var(--border); border-radius: 8px; padding: 22px; display: flex; gap: 10px; align-items: center; justify-content: center; flex-wrap: wrap; }
.drop.dragging { border-color: var(--accent); background: var(--bg); }
.drop.disabled, .button.disabled { opacity: 0.5; pointer-events: none; }
.queue { margin-top: 12px; display: flex; flex-direction: column; gap: 6px; }
.items { list-style: none; padding: 0; margin: 6px 0 0; max-height: 220px; overflow: auto; }
.items li { padding: 2px 0; border-bottom: 1px solid var(--border); }
.name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.small { font-size: 13px; }
</style>
