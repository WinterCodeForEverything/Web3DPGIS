<script setup lang="ts">
import type { IconName } from '@/icons'
import AppIcon from './AppIcon.vue'

// A button that shows an icon; its name appears beside it (or below or to its left, tip="below" / "left") while the pointer is on it or it has
// keyboard focus, and is also the button's accessible name. on is left out for buttons that are actions rather than toggles.
// (a boolean prop would otherwise default to false, making every button announce itself as a toggle)
withDefaults( defineProps<{ icon: IconName; label: string; on?: boolean; tip?: 'right' | 'below' | 'left' }>(), { on: undefined, tip: 'right' } )
</script>

<template>
	<button class="icon-button" :class="{ on }" :aria-pressed="on">
		<AppIcon :name="icon" />
		<span class="tip" :class="tip">{{ label }}</span>
	</button>
</template>

<style scoped>
.icon-button { position: relative; width: 44px; height: 44px; padding: 0; justify-content: center; border-radius: var(--ds-rounded-md); }
.tip { position: absolute; z-index: 1; white-space: nowrap; pointer-events: none;
	/* nearly opaque rather than blurred: inside the dock's own backdrop filter a second blur would see nothing behind it */
	padding: 6px 12px; border-radius: var(--ds-pill); background: rgba(29, 29, 31, 0.92); color: #fff; font-size: 14px; letter-spacing: -0.224px; opacity: 0;
	transition: opacity 0.15s ease, transform 0.15s ease; }
.tip.right { left: calc(100% + 14px); top: 50%; transform: translate(-4px, -50%); }
.tip.left { right: calc(100% + 12px); top: 50%; transform: translate(4px, -50%); }
.tip.below { left: 0; top: calc(100% + 8px); transform: translateY(-4px); }
.icon-button:hover .tip, .icon-button:focus-visible .tip { opacity: 1; }
.icon-button:hover .tip.right, .icon-button:focus-visible .tip.right,
.icon-button:hover .tip.left, .icon-button:focus-visible .tip.left { transform: translate(0, -50%); }
.icon-button:hover .tip.below, .icon-button:focus-visible .tip.below { transform: none; }
</style>
