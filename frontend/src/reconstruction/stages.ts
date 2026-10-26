// The stages a reconstruction goes through, as the job reports them (reconstruction/stages.py), then tiling.
import type { Preset } from './reconstructionsApi'

export const STAGES = [
	{ key: 'prepare', label: 'Preparing photos' },
	{ key: 'features', label: 'Finding features' },
	{ key: 'matching', label: 'Matching photos' },
	{ key: 'sparse', label: 'Placing cameras' },
	{ key: 'georeference', label: 'Georeferencing' },
	{ key: 'undistort', label: 'Undistorting photos' },
	{ key: 'densify', label: 'Dense point cloud' },
	{ key: 'mesh', label: 'Building the mesh' },
	{ key: 'texture', label: 'Texturing' },
	{ key: 'export', label: 'Exporting' },
	{ key: 'tiling', label: 'Building 3D Tiles' },
] as const

/** What each preset is for, with what it took on the development Mac (Apple M2, 8 GB, CPU only) in M1. */
export const PRESET_INFO: Record<Preset, { label: string; text: string }> = {
	preview: { label: 'Preview', text: 'Fastest, for checking a photo set. About 25 min and 1.4 GB of memory for 50 photos on an 8 GB laptop.' },
	standard: { label: 'Standard', text: 'More detail. About 35 min and 1.9 GB for 50 photos on the same laptop.' },
	high: { label: 'High', text: 'Most detail, with a refined mesh. Slower and needs more memory; best on a server.' },
}

export const MODE_TEXT: Record<string, string> = {
	gps: 'From the photos’ GPS: placed on the globe, in metres.',
	'camera centres': 'From the camera positions you gave: in that file’s frame and units, at the placement.',
	'full poses': 'Held at the camera poses you gave: in that file’s frame and units, at the placement.',
	'photos only': 'From the photos alone: the size is unknown, and the model sits at the placement.',
}
