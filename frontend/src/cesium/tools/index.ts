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
	{ id: 'measure', title: 'Measure', icon: 'measure', component: MeasureTool },
	{ id: 'labels', title: 'Labels', icon: 'labels', component: LabelEditor, editOnly: true },
	{ id: 'flight', title: 'Flight', icon: 'flight', component: FlightTool },
	{ id: 'walk', title: 'Walk', icon: 'walk', component: WalkTool },
	{ id: 'sightline', title: 'Sight line', icon: 'sightline', component: SightlineTool },
	{ id: 'viewshed', title: 'Viewshed', icon: 'viewshed', component: ViewshedTool },
	{ id: 'height', title: 'Height', icon: 'height', component: HeightTool, editOnly: true },
] )
