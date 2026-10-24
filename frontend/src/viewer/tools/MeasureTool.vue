<script setup lang="ts">
import { inject, onUnmounted, provide } from 'vue'
import MeasurePanel from '@/measure/MeasurePanel.vue'
import { measureHostKey } from '@/measure/host'
import { viewerKey } from '../core'
import { cesiumMeasureHost } from '../measure'
import { createSession } from '../session'

// Measuring in the map viewer: the shared panel, drawing into this tool's session so closing the tool cleans up.
const ctx = inject( viewerKey )!
const session = createSession( ctx.viewer, 'measure' )
onUnmounted( () => session.destroy() )
provide( measureHostKey, cesiumMeasureHost( ctx, session ) )
</script>

<template>
	<MeasurePanel />
</template>
