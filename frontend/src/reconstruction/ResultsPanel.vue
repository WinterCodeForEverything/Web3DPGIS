<script setup lang="ts">
import { computed } from 'vue'
import type { Reconstruction } from './reconstructionsApi'
import { MODE_TEXT } from './stages'

const props = defineProps<{ reconstruction: Reconstruction }>()
const stats = computed( () => props.reconstruction.stats )
const outliers = computed( () => Object.entries( stats.value.position_outliers ?? {} ) )
const minutes = ( s: number ) => s >= 60 ? `${Math.round( s / 60 )} min` : `${Math.round( s )} s`
</script>

<template>
	<section v-if="reconstruction.mode" class="card">
		<h2>How it went</h2>
		<p>{{ MODE_TEXT[ reconstruction.mode ] ?? reconstruction.mode }}</p>
		<table>
			<tbody>
				<tr v-if="stats.registered_photos !== undefined">
					<th>Photos placed</th>
					<td>{{ stats.registered_photos }} of {{ stats.photos }}
						<span v-if="stats.photos && stats.registered_photos < stats.photos" class="muted">: the others did not overlap enough with the rest</span></td>
				</tr>
				<tr v-if="stats.reprojection_error_px !== undefined">
					<th>Reprojection error</th>
					<td>{{ stats.reprojection_error_px.toFixed( 2 ) }} px <span class="muted">(under 1 px is good)</span></td>
				</tr>
				<tr v-if="stats.position_residual_median !== undefined">
					<th>Distance to GPS</th>
					<td>{{ stats.position_residual_median.toFixed( 2 ) }} m median <span class="muted">between each camera and its GPS position</span></td>
				</tr>
				<tr v-if="outliers.length">
					<th>Photos dropped</th>
					<td>{{ outliers.length }}, their GPS disagreed with the rest: {{ outliers.slice( 0, 5 ).map( ( [ n, r ] ) => `${n} (${r} m)` ).join( ', ' ) }}</td>
				</tr>
				<tr v-if="stats.photos_with_gps !== undefined">
					<th>Photos with GPS</th>
					<td>{{ stats.photos_with_gps }}<template v-if="stats.geoid_corrected">, altitudes converted from sea level</template></td>
				</tr>
				<tr v-if="stats.points"><th>3D points</th><td>{{ stats.points.toLocaleString() }}</td></tr>
				<tr v-if="stats.scale"><th>Scale</th><td>{{ stats.scale }}</td></tr>
				<tr v-if="stats.total_seconds"><th>Time</th><td>{{ minutes( stats.total_seconds ) }}<span v-if="stats.result_mb" class="muted"> · {{ stats.result_mb }} MB textured mesh</span></td></tr>
			</tbody>
		</table>
	</section>
</template>

<style scoped>
h2 { margin: 0 0 8px; font-size: 18px; }
table { border-collapse: collapse; font-size: 14px; }
th { text-align: left; font-weight: 500; padding: 4px 16px 4px 0; vertical-align: top; white-space: nowrap; color: var(--muted); }
td { padding: 4px 0; }
</style>
