// A viewer tool: a toolbar button that opens a panel. Each viewer lists its tools (cesium/tools/index.ts,
// three/tools/index.ts); adding a tool to a viewer is one entry there.
import { markRaw, type Component } from 'vue'
import type { Model3D } from '@/api/types'

export interface ToolDefinition {
	id: string
	title: string
	/** The panel; it gets what it needs from the viewer page by inject (e.g. mapViewerKey, measureHostKey). */
	component: Component
	/** Only for the model's owner. */
	editOnly?: boolean
}

export function defineTools( tools: ToolDefinition[] ): ToolDefinition[] {
	return tools.map( t => ( { ...t, component: markRaw( t.component ) } ) )
}

export function availableTools( tools: ToolDefinition[], model: Model3D | null ) {
	return tools.filter( t => !t.editOnly || model?.can_edit )
}
