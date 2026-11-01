// The map viewer's tools, in toolbar order.
import LabelEditor from '@/labels/LabelEditor.vue'
import { defineTools } from '@/tools'
import HeightTool from './HeightTool.vue'
import MeasureTool from './MeasureTool.vue'
import SightlineTool from './SightlineTool.vue'
import ViewerTool from './ViewerTool.vue'
import ViewshedTool from './ViewshedTool.vue'

export const MAP_TOOLS = defineTools( [
	{ id: 'measure', title: 'Measure', icon: 'measure', component: MeasureTool },
	{ id: 'labels', title: 'Labels', icon: 'labels', component: LabelEditor, editOnly: true },
	{ id: 'viewer', title: 'Viewer', icon: 'viewer', component: ViewerTool },
	{ id: 'sightline', title: 'Sight line', icon: 'sightline', component: SightlineTool },
	{ id: 'viewshed', title: 'Viewshed', icon: 'viewshed', component: ViewshedTool },
	{ id: 'height', title: 'Height', icon: 'height', component: HeightTool, editOnly: true },
] )
