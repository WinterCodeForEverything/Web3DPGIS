// The viewers a model can be opened in. The first one is the default, used when ?viewer= is missing or unknown.
export const VIEWERS = [
	{ kind: 'model', title: '3D model', description: 'Look at the model on its own (three.js)' },
	{ kind: 'map', title: 'Map (GIS)', description: 'The model on the globe, with measuring, labels and analysis tools (Cesium)' },
] as const

export type ViewerKind = typeof VIEWERS[ number ][ 'kind' ]

export function viewerFromQuery( value: unknown ): ViewerKind {
	return VIEWERS.find( v => v.kind === value )?.kind ?? VIEWERS[ 0 ].kind
}
