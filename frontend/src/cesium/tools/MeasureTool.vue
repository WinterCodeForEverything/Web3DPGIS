<script setup lang="ts">
import { inject, onUnmounted, provide } from 'vue'
import MeasurePanel from '@/measurements/MeasurePanel.vue'
import { measureHostKey } from '@/measurements/measureHost'
import { mapViewerKey } from '../mapViewer'
import { cesiumMeasureHost } from '../measuring'
import { createSession } from '../toolSession'

// Measuring in the map viewer: the shared panel, drawing into this tool's session so closing the tool cleans up.
const ctx = inject( mapViewerKey )!
const session = createSession( ctx.viewer, 'measure' )
onUnmounted( () => session.destroy() )
provide( measureHostKey, cesiumMeasureHost( ctx, session ) )
</script>

<template>
	<MeasurePanel />
</template>
