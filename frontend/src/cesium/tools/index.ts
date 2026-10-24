// The map viewer's tools, in toolbar order.
import LabelEditor from '@/labels/LabelEditor.vue'
import { defineTools } from '@/tools'
import FlightTool from './FlightTool.vue'
import HeightTool from './HeightTool.vue'
import MeasureTool from './MeasureTool.vue'
import SightlineTool from './SightlineTool.vue'
import ViewshedTool from './ViewshedTool.vue'
import WalkTool from './WalkTool.vue'

export const MAP_TOOLS = defineTools( [
	{ id: 'measure', title: 'Measure', component: MeasureTool },
	{ id: 'labels', title: 'Labels', component: LabelEditor, editOnly: true },
	{ id: 'flight', title: 'Flight', component: FlightTool },
	{ id: 'walk', title: 'Walk', component: WalkTool },
	{ id: 'sightline', title: 'Sight line', component: SightlineTool },
	{ id: 'viewshed', title: 'Viewshed', component: ViewshedTool },
	{ id: 'height', title: 'Height', component: HeightTool, editOnly: true },
] )
