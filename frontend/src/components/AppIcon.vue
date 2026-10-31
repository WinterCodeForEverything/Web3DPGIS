<script setup lang="ts">
import { ICONS, type IconName } from '@/icons'

// An icon from icons.ts, drawn in the current text colour. Decorative: the button or text beside it carries the meaning.
withDefaults( defineProps<{ name: IconName; size?: number }>(), { size: 20 } )
</script>

<template>
	<svg class="app-icon" viewBox="0 0 24 24" :width="size" :height="size" aria-hidden="true" v-html="ICONS[ name ]" />
</template>

<style scoped>
.app-icon { flex-shrink: 0; }
</style>
