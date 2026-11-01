// The map viewer's tools, in toolbar order.
import { defineComponent, h, markRaw } from 'vue'
import LabelEditor from '@/labels/LabelEditor.vue'
import { defineTools } from '@/tools'
import FlightTool from './FlightTool.vue'
import HeightTool from './HeightTool.vue'
import MeasureTool from './MeasureTool.vue'
import ModePanel, { type ToolMode } from './ModePanel.vue'
import SightlineTool from './SightlineTool.vue'
import ViewshedTool from './ViewshedTool.vue'
import WalkTool from './WalkTool.vue'

/** A tool whose panel switches between modes; see ModePanel. */
function modeTool( label: string, prompt: string, modes: ToolMode[] ) {
	const raw = modes.map( m => ( { ...m, component: markRaw( m.component ) } ) )
	return defineComponent( { name: label.replace( /\W/g, '' ), setup: () => () => h( ModePanel, { label, prompt, modes: raw } ) } )
}

const ViewerTool = modeTool( 'Viewer mode', 'Choose a viewer mode: Flight or Walk.', [
	{ id: 'flight', title: 'Flight', icon: 'flight', component: FlightTool, hint: 'Replay saved camera tours, or record one.' },
	{ id: 'walk', title: 'Walk', icon: 'walk', component: WalkTool, hint: 'Walk on the model at eye height.' },
] )

const AnalyzeTool = modeTool( 'Analysis', 'Choose an analysis: Sight line or Viewshed.', [
	{ id: 'sightline', title: 'Sight line', icon: 'sightline', component: SightlineTool, hint: 'Can the observer see one target point?' },
	{ id: 'viewshed', title: 'Viewshed', icon: 'viewshed', component: ViewshedTool, hint: 'What can the observer see across a field of view?' },
] )

export const MAP_TOOLS = defineTools( [
	{ id: 'measure', title: 'Measure', icon: 'measure', component: MeasureTool },
	{ id: 'labels', title: 'Labels', icon: 'labels', component: LabelEditor, editOnly: true },
	{ id: 'viewer', title: 'Viewer', icon: 'viewer', component: ViewerTool },
	{ id: 'analyze', title: 'Analyze', icon: 'analyze', component: AnalyzeTool },
	{ id: 'height', title: 'Height', icon: 'height', component: HeightTool, editOnly: true },
] )
