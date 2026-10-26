#!/usr/bin/env python3
"""Run the reconstruction pipeline (reconstruction/stages.py) by hand on a folder of photos and measure each stage.

    scripts/reconstruct_by_hand.py --images ~/recon-data/odm_data_aukerman/images --count 50 --preset preview \\
        --work ~/recon-work/aukerman-50-preview --tools ~/recon-tools

--tools holds openmvs/ (InterfaceCOLMAP, DensifyPointCloud, …) and obj2tiles/Obj2Tiles; COLMAP comes from PATH.
Running again on the same --work folder resumes after the last finished stage. Stage times, peak memory and disk use
go to <work>/report.json. See reconstruction/stages.py for how the cameras are solved from what is known.
"""
import argparse
import json
import platform
import shutil
import sys
from pathlib import Path

sys.path.insert( 0, str( Path( __file__ ).resolve().parent.parent ) )
from core.geoid import geoid_height  # noqa: E402  (no Django needed)
from reconstruction.camera_inputs import UP_AXES  # noqa: E402
from reconstruction.stages import PRESETS, STAGES, Options, Pipeline, ReconstructionError, TemporaryError, Tools  # noqa: E402


def main():
	ap = argparse.ArgumentParser( description = __doc__, formatter_class = argparse.RawDescriptionHelpFormatter )
	ap.add_argument( '--images', required = True, type = Path )
	ap.add_argument( '--count', type = int, help = 'use the first N photos (sorted by name)' )
	ap.add_argument( '--preset', choices = PRESETS, default = 'preview' )
	ap.add_argument( '--max-image-size', type = int, help = "cap the preset's image size (e.g. 2000 on an 8 GB machine)" )
	ap.add_argument( '--work', required = True, type = Path )
	ap.add_argument( '--tools', required = True, type = Path )
	ap.add_argument( '--use-gpu', action = 'store_true', help = 'COLMAP on the GPU (needs a CUDA build)' )
	ap.add_argument( '--stop-after', choices = STAGES, help = 'stop after this stage, e.g. georeference to test only how the cameras are solved' )
	ap.add_argument( '--no-tiling', action = 'store_true', help = 'stop after the textured OBJ instead of running Obj2Tiles' )
	known = ap.add_argument_group( 'what is known about the cameras' )
	known.add_argument( '--camera-model', default = 'SIMPLE_RADIAL', help = 'COLMAP camera model, e.g. SIMPLE_RADIAL, OPENCV, RADIAL' )
	known.add_argument( '--camera-params', help = 'known intrinsics for that model, comma-separated (e.g. f,cx,cy,k)' )
	known.add_argument( '--fix-intrinsics', action = 'store_true', help = 'hold the intrinsics fixed instead of refining them' )
	known.add_argument( '--poses', type = Path, help = 'camera centres ("name x y z") or full COLMAP poses ("name qw qx qy qz tx ty tz")' )
	known.add_argument( '--prior-std', type = float, default = 0.1, help = 'uncertainty of --poses centres, in their units (default 0.1)' )
	known.add_argument( '--gps-std', default = '3,5', help = 'GPS uncertainty in metres, horizontal,vertical (default 3,5)' )
	known.add_argument( '--ignore-gps', action = 'store_true', help = 'do not use GPS from the photos' )
	known.add_argument( '--altitude-reference', choices = [ 'sea-level', 'ellipsoid' ], default = 'sea-level',
		help = "what the photos' EXIF altitudes are relative to (default sea level, converted with the EGM96 geoid)" )
	known.add_argument( '--placement', help = 'longitude,latitude,height for a model without GPS (default 0,0,0)' )
	known.add_argument( '--masks', type = Path, help = 'folder of masks, <photo name>.png; black areas get no features' )
	known.add_argument( '--full-resolution', action = 'store_true', help = 'extract features at full image size (small or distant objects)' )
	known.add_argument( '--sift-threshold', type = float, help = 'SIFT peak threshold; lower finds more features in dark photos (default 0.00667)' )
	known.add_argument( '--min-track', type = int, default = 2, help = 'keep only 3D points seen in at least this many photos' )
	known.add_argument( '--units-to-metres', type = float, default = 1.0, help = 'scale of the result to metres, e.g. 0.001 for poses in mm' )
	known.add_argument( '--up-axis', choices = list( UP_AXES ), default = '+z', help = 'axis of the result that points up (camera frames: write --up-axis=-y)' )
	known.add_argument( '--up-method', choices = [ 'IMAGE-ORIENTATION', 'MANHATTAN-WORLD' ], default = 'IMAGE-ORIENTATION',
		help = 'how "up" is found without GPS or poses: upright photos, or the lines of buildings' )
	args = ap.parse_args()
	if args.fix_intrinsics and not args.camera_params:
		sys.exit( '--fix-intrinsics needs --camera-params' )

	options = Options(
		preset = args.preset, max_image_size = args.max_image_size, use_gpu = args.use_gpu,
		# OpenMVS 2.4.0's macOS build breaks texture seam levelling (black patches, coloured borders)
		seam_leveling = platform.system() != 'Darwin',
		camera_model = args.camera_model, camera_params = args.camera_params, fix_intrinsics = args.fix_intrinsics,
		poses = args.poses, prior_std = args.prior_std, gps_std = tuple( float( v ) for v in args.gps_std.split( ',' ) ),
		ignore_gps = args.ignore_gps, altitude_reference = args.altitude_reference, masks = args.masks,
		full_resolution = args.full_resolution, sift_threshold = args.sift_threshold, min_track = args.min_track,
		units_to_metres = args.units_to_metres, up_axis = args.up_axis, up_method = args.up_method,
		placement = tuple( float( v ) for v in args.placement.split( ',' ) ) if args.placement else None, count = args.count )
	tools = Tools( colmap = shutil.which( 'colmap' ) or sys.exit( 'colmap is not on PATH' ),
		openmvs = args.tools / 'openmvs', obj2tiles = args.tools / 'obj2tiles' / 'Obj2Tiles' )
	pipeline = Pipeline( args.images, args.work, tools, options, geoid = geoid_height )
	try:
		report = pipeline.run( stop_after = args.stop_after, tile = not args.no_tiling )
	except ( ReconstructionError, TemporaryError ) as exc:
		sys.exit( f'reconstruction stopped: {exc}' )
	print( json.dumps( { k: v for k, v in report.items() if k != 'stages' }, indent = 2 ) )


if __name__ == '__main__':
	main()
