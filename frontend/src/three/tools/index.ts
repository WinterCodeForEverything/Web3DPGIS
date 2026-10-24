// The 3D model viewer's tools, in toolbar order. The panels are the shared ones; ThreeViewerView provides their hosts.
import LabelEditor from '@/labels/LabelEditor.vue'
import MeasurePanel from '@/measurements/MeasurePanel.vue'
import { defineTools } from '@/tools'

export const MODEL_TOOLS = defineTools( [
	{ id: 'measure', title: 'Measure', component: MeasurePanel },
	{ id: 'labels', title: 'Labels', component: LabelEditor, editOnly: true },
] )
