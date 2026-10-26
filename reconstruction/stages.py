"""The reconstruction pipeline: photos → COLMAP (cameras and sparse points) → OpenMVS (dense cloud, mesh, texture)
→ a textured OBJ in metres, ready for the tiling job. Plain Python, no Django: the reconstruction job and
scripts/reconstruct_by_hand.py both drive it.

Each stage writes <stage>.done in the work folder when it finishes, so running the pipeline again on the same folder
resumes after the last finished stage. How the cameras are solved depends on what is known (Options.mode_for):

  photos only        self-calibration from feature matches; "up" found from the photos; scale unknown
  photos with GPS    GPS positions (altitudes converted to ellipsoid heights) are priors while solving; result in
                     east-north-up metres around their centre; photos whose GPS does not fit are dropped
  camera centres     a poses file "name x y z" in any local system; priors while solving; result in that system
  full poses         a poses file "name qw qx qy qz tx ty tz" (COLMAP, world to camera): cameras are not solved,
                     matches are searched along the epipolar lines the poses give, points are triangulated

Known intrinsics can be given in any mode and held fixed; masks keep features (and dense points) off the background.
"""
import json
import math
import os
import platform
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Callable

from . import camera_inputs as ci

# image sizes are the preset's; a machine can cap them (Options.max_image_size), e.g. 2000 on an 8 GB laptop
PRESETS = {
	'preview': { 'max_image_size': 1600, 'densify_level': 1, 'mesh_decimate': 0.5, 'refine': False, 'lods': 3 },
	'standard': { 'max_image_size': 2400, 'densify_level': 1, 'mesh_decimate': 1.0, 'refine': False, 'lods': 3 },
	'high': { 'max_image_size': 3200, 'densify_level': 0, 'mesh_decimate': 1.0, 'refine': True, 'lods': 4 },
}
PHOTO_TYPES = ( '.jpg', '.jpeg', '.tif', '.tiff', '.png' )
STAGES = ( 'prepare', 'features', 'matching', 'sparse', 'georeference', 'undistort', 'densify', 'mesh', 'texture', 'export' )
# rough share of a run each stage takes on a CPU (M1 benchmark), for progress reporting
WEIGHTS = { 'prepare': 1, 'features': 30, 'matching': 12, 'sparse': 3, 'georeference': 1, 'undistort': 3, 'densify': 28, 'mesh': 6,
	'texture': 14, 'export': 2 }
MIN_PHOTOS = 3


class ReconstructionError( Exception ):
	"""A problem with the input (too few photos placed, no overlap, bad poses file …); trying again will not help."""


class Cancelled( ReconstructionError ):
	def __init__( self ):
		super().__init__( 'Cancelled.' )


class TemporaryError( Exception ):
	"""Something around the run went wrong (a tool was killed, the disk filled up); trying again may help."""


class OutOfMemory( TemporaryError ):
	"""A tool ran out of memory; the next attempt should use smaller images (Options.resolution_shift)."""

	def __init__( self, stage, tool ):
		super().__init__( f'{tool} ran out of memory in the {stage} stage' )
		self.stage = stage


@dataclass
class Tools:
	colmap: str = 'colmap'
	openmvs: Path | None = None       # folder with InterfaceCOLMAP, DensifyPointCloud, …
	obj2tiles: Path | None = None     # the Obj2Tiles program; only scripts/reconstruct_by_hand.py tiles by itself


@dataclass
class Options:
	preset: str = 'standard'
	max_image_size: int | None = None         # caps the preset's image size on this machine
	resolution_shift: int = 0                 # densify this many levels lower (raised after an out-of-memory error)
	use_gpu: bool = False
	seam_leveling: bool = True                # off on macOS: OpenMVS 2.4.0's build there breaks it
	camera_model: str = 'SIMPLE_RADIAL'
	camera_params: str | None = None          # known intrinsics, comma-separated, in the model's order
	fix_intrinsics: bool = False
	poses: Path | None = None                 # camera centres or full poses in a local system
	prior_std: float = 0.1                    # uncertainty of the poses file's centres, in its units
	gps_std: tuple = ( 3.0, 5.0 )             # GPS uncertainty in metres, horizontal and vertical
	ignore_gps: bool = False
	altitude_reference: str = 'sea-level'     # what EXIF altitudes are relative to: 'sea-level' or 'ellipsoid'
	masks: Path | None = None                 # <photo name>.png; black = background
	full_resolution: bool = False             # features at full size (small or distant objects)
	sift_threshold: float | None = None       # lower finds more features in dark or low-contrast photos
	min_track: int = 2                        # keep only 3D points seen in at least this many photos
	units_to_metres: float = 1.0              # scale of the result to metres, e.g. 0.001 for poses in mm
	up_axis: str = '+z'                       # axis of the result that points up
	up_method: str = 'IMAGE-ORIENTATION'      # how "up" is found from photos alone
	placement: tuple | None = None            # longitude, latitude, height for a result without GPS
	count: int | None = None                  # use only the first N photos (benchmarks)

	@classmethod
	def from_dict( cls, values ):
		known = { f.name for f in fields( cls ) }
		return cls( **{ k: v for k, v in values.items() if k in known } )

	@property
	def image_size( self ):
		size = PRESETS[ self.preset ]['max_image_size']
		return min( size, self.max_image_size ) if self.max_image_size else size


@dataclass
class Pipeline:
	images: Path                                          # folder with the photos
	work: Path                                            # work folder; keeps the checkpoints between attempts
	tools: Tools
	options: Options
	log: Callable[ [ str ], None ] = print
	progress: Callable[ [ str, float ], None ] | None = None    # ( stage, fraction of the whole run done )
	cancelled: Callable[ [], bool ] = lambda: False
	geoid: Callable[ [ float, float ], float ] | None = None    # geoid height N at ( lon, lat ), for EXIF altitudes
	on_stage_done: Callable[ [ str ], None ] | None = None     # e.g. copy the checkpoint to storage
	report: dict = field( default_factory = dict )

	def __post_init__( self ):
		self.work = Path( self.work ).resolve()
		self.work.mkdir( parents = True, exist_ok = True )
		self.paths = { name: self.work / name for name in ( 'images', 'sparse', 'aligned', 'dense', 'result', 'tiles' ) }
		self.db = self.work / 'database.db'
		self.reference = self.work / 'reference_positions.txt'
		self.report_path = self.work / 'report.json'
		self.report = json.loads( self.report_path.read_text() ) if self.report_path.exists() else { 'stages': {} }
		self.preset = PRESETS[ self.options.preset ]

	# --- running ------------------------------------------------------------------

	def run( self, stop_after = None, tile = False ):
		"""Run the stages that have not finished yet; returns the report. tile=True also runs Obj2Tiles at the end."""
		self.report.update( preset = self.options.preset, host = f'{platform.machine()} {platform.system()} {os.cpu_count()} cores',
			settings = { **self.preset, 'image_size': self.options.image_size, 'resolution_shift': self.options.resolution_shift,
				'seam_leveling': self.options.seam_leveling } )
		total = sum( WEIGHTS.values() ); done = 0
		for name in STAGES:
			self._stage( name, getattr( self, f'_{name}' ), done / total )
			done += WEIGHTS[ name ]
			if name == stop_after:
				return self.report
		if tile:
			self._stage( 'tiling', self._tiling, 1.0 )
		self.report[ 'total_seconds' ] = round( sum( s['seconds'] for s in self.report['stages'].values() ), 1 )
		self._save()
		return self.report

	def _stage( self, name, fn, fraction ):
		marker = self.work / f'{name}.done'
		if marker.exists():
			self.log( f'{name}: done before, skipped' )
			return
		if self.cancelled():
			raise Cancelled()
		if self.progress:
			self.progress( name, fraction )
		self.log( f'{name}: running' )
		start, self._peak = time.monotonic(), 0
		fn()
		seconds = time.monotonic() - start
		self.report['stages'][ name ] = { 'seconds': round( seconds, 1 ), 'peak_memory_mb': self._peak, 'work_disk_mb': disk_mb( self.work ) }
		self._save()
		marker.touch()
		self.log( f'{name}: {seconds:.0f} s, peak {self._peak} MB' )
		if self.on_stage_done:
			self.on_stage_done( name )

	def _save( self ):
		self.report_path.write_text( json.dumps( self.report, indent = 2 ) )

	def _cmd( self, args, stage ):
		"""Run a tool in the work folder (OpenMVS writes log files into the current folder); its output goes to
		commands.log. Cancellation stops it; being killed or running out of memory is a temporary error."""
		args = [ str( a ) for a in args ]
		tool = os.path.basename( args[0] )
		timer = [ '/usr/bin/time', '-l' if platform.system() == 'Darwin' else '-v' ] if os.path.exists( '/usr/bin/time' ) else []
		err_path = self.work / 'last_command.err'
		with open( self.work / 'commands.log', 'a' ) as out, open( err_path, 'w' ) as err:
			out.write( '\n$ ' + ' '.join( args ) + '\n' ); out.flush()
			try:
				proc = subprocess.Popen( timer + args, cwd = self.work, stdout = out, stderr = err )
			except FileNotFoundError:
				raise ReconstructionError( f'{tool} is not installed on this worker' ) from None
			while proc.poll() is None:
				if self.cancelled():
					proc.terminate()
					try:
						proc.wait( 10 )
					except subprocess.TimeoutExpired:
						proc.kill()
					raise Cancelled()
				time.sleep( 1 )
		text = err_path.read_text( errors = 'replace' )
		with open( self.work / 'commands.log', 'a' ) as out:
			out.write( text )
		m = re.search( r'(\d+)\s+maximum resident set size', text ) or re.search( r'Maximum resident set size \(kbytes\): (\d+)', text )
		if m:
			self._peak = max( self._peak, round( int( m.group( 1 ) ) / ( 2 ** 20 if platform.system() == 'Darwin' else 1024 ) ) )
		killed = proc.returncode < 0 or re.search( r'terminated (abnormally|by signal)|signal 9|Killed', text )
		if re.search( r'bad_alloc|out of memory|Cannot allocate memory', text, re.I ) or ( killed and 'signal 9' in text ):
			raise OutOfMemory( stage, tool )
		if killed:
			raise TemporaryError( f'{tool} was stopped by a signal in the {stage} stage' )
		if proc.returncode:
			tail = '\n'.join( text.strip().splitlines()[-15:] )
			self.log( tail )
			raise ReconstructionError( f'{tool} failed in the {stage} stage (exit code {proc.returncode}); see the job log' )

	def _mvs( self, name ):
		if not self.tools.openmvs:
			raise ReconstructionError( 'OpenMVS is not configured on this worker' )
		return Path( self.tools.openmvs ) / name

	def _refine_flags( self, prefix ):
		refine = '0' if self.options.fix_intrinsics else '1'
		return [ f'--{prefix}.ba_refine_focal_length', refine, f'--{prefix}.ba_refine_extra_params', refine, f'--{prefix}.ba_refine_principal_point', '0' ]

	# --- stages -------------------------------------------------------------------

	def _prepare( self ):
		o = self.options
		images = self.paths['images']
		photos = sorted( p for p in Path( self.images ).iterdir() if p.suffix.lower() in PHOTO_TYPES )[: o.count]
		if len( photos ) < MIN_PHOTOS:
			raise ReconstructionError( f'At least {MIN_PHOTOS} photos are needed; found {len( photos )}.' )
		images.mkdir( exist_ok = True )
		for p in photos:
			target = images / p.name
			if not target.exists():
				try:
					os.link( p, target )
				except OSError:
					shutil.copy2( p, target )
		names = { p.name for p in photos }
		geoid = self.geoid if o.altitude_reference == 'sea-level' else None
		gps, origin = ( None, None ) if o.ignore_gps else ci.enu_positions( photos, geoid )
		self.report.update( photos = len( photos ), photos_with_gps = len( gps or {} ), geoid_corrected = bool( gps and geoid ) )
		if o.poses:
			try:
				centres, full = ci.read_poses( o.poses )
			except ci.PoseFileError as exc:
				raise ReconstructionError( f'Camera poses file: {exc}.' ) from None
			missing = sorted( names - set( centres ) )
			if full and missing:
				raise ReconstructionError( f'{len( missing )} photos have no pose in the poses file, for example {", ".join( missing[:5] )}.' )
			positions = { n: c for n, c in centres.items() if n in names }
			if len( positions ) < 3:
				raise ReconstructionError( f'The poses file names only {len( positions )} of the photos; at least 3 are needed.' )
			mode, std = ( 'full poses' if full else 'camera centres' ), ( o.prior_std, ) * 3
			self.report.update( scale = 'units of the poses file', placement = list( o.placement ) if o.placement else None )
			if full:
				( self.work / 'known_poses.json' ).write_text( json.dumps( { n: full[ n ] for n in positions } ) )
		elif gps:
			positions, mode = gps, 'gps'
			h, v = o.gps_std
			std = ( h, h, v )
			self.report.update( scale = 'metres (from GPS)', placement = list( origin ) )
		else:
			positions, mode, std = None, 'photos only', None
			self.report.update( scale = 'unknown (no GPS or poses)', placement = list( o.placement ) if o.placement else None )
		self.report.update( mode = mode, positions_known = len( positions or {} ), prior_std = std )
		if positions:
			self.reference.write_text( ''.join( f'{n} {x:.4f} {y:.4f} {z:.4f}\n' for n, ( x, y, z ) in positions.items() ) )
		if o.masks:
			self.report[ 'masks' ] = sum( 1 for n in names if ( Path( o.masks ) / f'{n}.png' ).exists() )

	def _features( self ):
		o = self.options
		self._cmd( [ self.tools.colmap, 'feature_extractor', '--database_path', self.db, '--image_path', self.paths['images'],
			'--ImageReader.camera_model', o.camera_model, '--ImageReader.single_camera', '1',
			*( [ '--ImageReader.camera_params', o.camera_params ] if o.camera_params else [] ),
			*( [ '--ImageReader.mask_path', Path( o.masks ).resolve() ] if o.masks else [] ),
			'--FeatureExtraction.use_gpu', int( o.use_gpu ), '--FeatureExtraction.max_image_size', -1 if o.full_resolution else o.image_size,
			*( [ '--SiftExtraction.peak_threshold', o.sift_threshold, '--SiftExtraction.domain_size_pooling', 1 ] if o.sift_threshold else [] ) ], 'features' )
		# our reference positions become the pose priors; without any, COLMAP's raw EXIF GPS priors are removed
		positions = { l.split()[0]: tuple( map( float, l.split()[1:4] ) ) for l in self.reference.read_text().splitlines() } if self.reference.exists() else {}
		self.report[ 'priors_written' ] = ci.write_position_priors( self.db, positions, self.report['prior_std'] or ( 1, 1, 1 ) )

	def _matching( self ):
		o = self.options
		if self.report['mode'] == 'full poses':
			# the poses say where each match must lie, so they guide the matching instead of the photos verifying it
			poses = { n: ( tuple( q ), tuple( t ) ) for n, ( q, t ) in json.loads( ( self.work / 'known_poses.json' ).read_text() ).items() }
			self.report[ 'matched_pairs' ], self.report[ 'matches' ] = ci.match_with_known_poses( self.db, poses )
		elif self.report['photos'] > 150 and self.report['positions_known']:
			self._cmd( [ self.tools.colmap, 'spatial_matcher', '--database_path', self.db, '--FeatureMatching.use_gpu', int( o.use_gpu ) ], 'matching' )
		else:
			self._cmd( [ self.tools.colmap, 'exhaustive_matcher', '--database_path', self.db, '--FeatureMatching.use_gpu', int( o.use_gpu ) ], 'matching' )
		self.report[ 'verified_pairs' ] = pairs = ci.verified_pairs( self.db )
		if pairs == 0:
			raise ReconstructionError( 'No two photos share enough matching features. Neighbouring photos need about 60% overlap; '
				'for dark or low-contrast photos, try a lower SIFT threshold.' )

	def _sparse( self ):
		mode, sparse = self.report['mode'], self.paths['sparse']
		base = [ '--database_path', self.db, '--image_path', self.paths['images'], '--output_path', sparse ]
		if mode == 'full poses':
			known = self.work / 'known_model'
			poses = { n: ( tuple( q ), tuple( t ) ) for n, ( q, t ) in json.loads( ( self.work / 'known_poses.json' ).read_text() ).items() }
			ci.write_known_model( self.db, poses, known )
			attempts = [ ( 'triangulated from the given poses', [ self.tools.colmap, 'point_triangulator', '--database_path', self.db,
				'--image_path', self.paths['images'], '--input_path', known, '--output_path', sparse / '0',
				'--refine_intrinsics', '0' if self.options.fix_intrinsics else '1' ] ) ]
		elif mode in ( 'gps', 'camera centres' ):
			attempts = [ ( 'incremental with position priors', [ self.tools.colmap, 'pose_prior_mapper', *base, '--use_robust_loss_on_prior_position', '1',
				*self._refine_flags( 'Mapper' ) ] ),
				( 'global, positions used only to align', [ self.tools.colmap, 'global_mapper', *base, *self._refine_flags( 'GlobalMapper' ) ] ) ]
		else:
			attempts = [ ( 'global', [ self.tools.colmap, 'global_mapper', *base, *self._refine_flags( 'GlobalMapper' ) ] ),
				( 'incremental', [ self.tools.colmap, 'mapper', *base, *self._refine_flags( 'Mapper' ) ] ) ]
		photos = self.report['photos']
		for label, cmd in attempts:
			shutil.rmtree( sparse, ignore_errors = True )
			( sparse / '0' if mode == 'full poses' else sparse ).mkdir( parents = True )
			try:
				self._cmd( cmd, 'sparse' )
			except ReconstructionError:
				if cmd is attempts[-1][1]:
					raise
				continue
			( registered, error ), best = self._best_model()
			self.report.update( mapper = label, registered_photos = registered, reprojection_error_px = error, sparse_model = str( best ) if best else None )
			if registered >= 0.5 * photos:
				break
		registered = self.report.get( 'registered_photos', 0 )
		if registered < max( MIN_PHOTOS, math.ceil( 0.3 * photos ) ):
			raise ReconstructionError( f'Only {registered} of {photos} photos could be placed. The photos need more overlap with each other '
				f'(about 60% between neighbours), and the scene needs texture; plain walls, water and glass give too few features.' )

	def _best_model( self ):
		models = sorted( ( self._model_stats( m ), m ) for m in self.paths['sparse'].iterdir() if ( m / 'images.bin' ).exists() )
		return models[-1] if models else ( ( 0, None ), None )

	def _model_stats( self, model ):
		text = subprocess.run( [ self.tools.colmap, 'model_analyzer', '--path', str( model ) ], capture_output = True, text = True ).stderr
		reg = re.search( r'Registered images:\s*(\d+)', text ); err = re.search( r'Mean reprojection error:\s*([\d.]+)', text )
		pts = re.search( r'Points:\s*(\d+)', text )
		self._last_points = int( pts.group( 1 ) ) if pts else 0
		return int( reg.group( 1 ) ) if reg else 0, float( err.group( 1 ) ) if err else None

	def _georeference( self ):
		"""Put the model in its final frame: the reference positions' (GPS or local), or upright for photos only."""
		mode, aligned, colmap = self.report['mode'], self.paths['aligned'], self.tools.colmap
		shutil.rmtree( aligned, ignore_errors = True ); aligned.mkdir()
		self.report[ 'georeferenced' ] = mode == 'gps'
		if mode == 'full poses':
			shutil.copytree( self.report['sparse_model'], aligned, dirs_exist_ok = True )   # already in the poses' frame
		elif mode == 'photos only':
			# no positions: rotate the model so "up" is +Z; position and scale stay arbitrary
			self._cmd( [ colmap, 'model_orientation_aligner', '--image_path', self.paths['images'], '--input_path', self.report['sparse_model'],
				'--output_path', aligned, '--method', self.options.up_method ], 'georeference' )
		else:
			self._align( self.report['sparse_model'], self.reference )
			self._drop_position_outliers()
		if self.options.min_track > 2:
			# a chance match rarely agrees with a third photo
			filtered = self.work / 'aligned_filtered'
			shutil.rmtree( filtered, ignore_errors = True ); filtered.mkdir()
			self._cmd( [ colmap, 'point_filtering', '--input_path', aligned, '--output_path', filtered, '--min_track_len', self.options.min_track ], 'georeference' )
			shutil.rmtree( aligned ); filtered.rename( aligned )
		self._model_stats( aligned )
		self.report[ 'points' ] = self._last_points

	def _align( self, model, reference ):
		# RANSAC threshold: three standard deviations of the positions' uncertainty
		self._cmd( [ self.tools.colmap, 'model_aligner', '--input_path', model, '--output_path', self.paths['aligned'],
			'--ref_images_path', reference, '--ref_is_gps', '0', '--alignment_type', 'custom',
			'--alignment_max_error', 3 * max( self.report['prior_std'] ) ], 'georeference' )

	def _drop_position_outliers( self ):
		"""Photos whose camera lands far from its GPS (or given) position are removed and the model aligned again."""
		aligned, colmap = self.paths['aligned'], self.tools.colmap
		text_model = self.work / 'aligned_txt'
		shutil.rmtree( text_model, ignore_errors = True ); text_model.mkdir()
		self._cmd( [ colmap, 'model_converter', '--input_path', aligned, '--output_path', text_model, '--output_type', 'TXT' ], 'georeference' )
		reference = { l.split()[0]: tuple( map( float, l.split()[1:4] ) ) for l in self.reference.read_text().splitlines() }
		outliers, residuals = ci.position_outliers( ci.read_model_centres( text_model / 'images.txt' ), reference,
			floor = 3 * max( self.report['prior_std'] ) )
		if residuals:
			self.report[ 'position_residual_median' ] = round( sorted( residuals.values() )[ len( residuals ) // 2 ], 3 )
		self.report[ 'position_outliers' ] = { n: round( r, 2 ) for n, r in outliers.items() }
		if not outliers:
			return
		self.log( f'dropping {len( outliers )} photos whose position does not fit: ' + ', '.join( sorted( outliers ) ) )
		names = self.work / 'outlier_photos.txt'
		names.write_text( '\n'.join( sorted( outliers ) ) + '\n' )
		cleaned = self.work / 'aligned_cleaned'
		shutil.rmtree( cleaned, ignore_errors = True ); cleaned.mkdir()
		self._cmd( [ colmap, 'image_deleter', '--input_path', aligned, '--output_path', cleaned, '--image_names_path', names ], 'georeference' )
		kept = self.work / 'reference_kept.txt'
		kept.write_text( ''.join( l + '\n' for l in self.reference.read_text().splitlines() if l.split()[0] not in outliers ) )
		shutil.rmtree( aligned ); aligned.mkdir()
		self._align( cleaned, kept )
		self.report[ 'registered_photos' ] = self.report['registered_photos'] - len( outliers )

	def _undistort( self ):
		self._cmd( [ self.tools.colmap, 'image_undistorter', '--image_path', self.paths['images'], '--input_path', self.paths['aligned'],
			'--output_path', self.paths['dense'], '--output_type', 'COLMAP', '--max_image_size', self.options.image_size ], 'undistort' )

	def _densify( self ):
		o, dense = self.options, self.paths['dense']
		scene = dense / 'scene.mvs'
		mask_options = []
		if o.masks:
			self._openmvs_masks()
			mask_options = [ '--mask-path', dense / 'masks', '--ignore-mask-label', 0 ]
		# with known poses there are few sparse points, too few for OpenMVS to pick neighbour views from: use the cameras
		neighbours = [ '--force-neighbors-from-images', 1 ] if self.report['mode'] == 'full poses' else []
		self._cmd( [ self._mvs( 'InterfaceCOLMAP' ), '-i', dense, '-o', scene, '--image-folder', dense / 'images' ], 'densify' )
		self._cmd( [ self._mvs( 'DensifyPointCloud' ), '-i', scene, '-w', dense, '--resolution-level', self.preset['densify_level'] + o.resolution_shift,
			'--max-resolution', o.image_size, *mask_options, *neighbours ], 'densify' )
		if not ( dense / 'scene_dense.ply' ).exists():
			raise ReconstructionError( 'The dense reconstruction produced no points; the photos may disagree with their camera positions.' )

	def _openmvs_masks( self ):
		"""The masks for OpenMVS: <photo stem>.mask.png at the undistorted photos' size (background = 0, ignored)."""
		from PIL import Image
		dense = self.paths['dense']
		folder = dense / 'masks'; folder.mkdir( exist_ok = True )
		for photo in ( dense / 'images' ).iterdir():
			mask = Path( self.options.masks ) / f'{photo.name}.png'
			if mask.exists():
				with Image.open( photo ) as img:
					size = img.size
				Image.open( mask ).convert( 'L' ).resize( size ).point( lambda v: 255 if v else 0 ).save( folder / f'{photo.stem}.mask.png' )

	def _mesh( self ):
		dense = self.paths['dense']
		self._cmd( [ self._mvs( 'ReconstructMesh' ), '-i', dense / 'scene_dense.mvs', '-w', dense, '--decimate', self.preset['mesh_decimate'] ], 'mesh' )
		if self.preset['refine']:
			self._cmd( [ self._mvs( 'RefineMesh' ), '-i', dense / 'scene_dense.mvs', '-m', dense / 'scene_dense_mesh.ply', '-w', dense,
				'-o', dense / 'scene_dense_mesh_refine.mvs' ], 'mesh' )

	def _texture( self ):
		dense, leveling = self.paths['dense'], int( self.options.seam_leveling )
		mesh = dense / ( 'scene_dense_mesh_refine.ply' if self.preset['refine'] else 'scene_dense_mesh.ply' )
		self._cmd( [ self._mvs( 'TextureMesh' ), '-i', dense / 'scene_dense.mvs', '-m', mesh, '-w', dense, '-o', dense / 'model.mvs',
			'--export-type', 'obj', '--global-seam-leveling', leveling, '--local-seam-leveling', leveling ], 'texture' )

	def _export( self ):
		"""result/: the textured mesh as model.obj in metres, written Y-up as OBJ files usually are, with its material
		and textures; model_zup.obj in the work folder keeps east-north-up (Z up) for Obj2Tiles."""
		o, dense, result = self.options, self.paths['dense'], self.paths['result']
		shutil.rmtree( result, ignore_errors = True ); result.mkdir()
		ci.transform_obj( dense / 'model.obj', result / 'model.obj', o.units_to_metres, o.up_axis, y_up = True )
		ci.transform_obj( dense / 'model.obj', dense / 'model_zup.obj', o.units_to_metres, o.up_axis )
		mtl = dense / 'model.mtl'
		shutil.copy2( mtl, result )
		for line in mtl.read_text().splitlines():
			if line.strip().startswith( 'map_' ):
				texture = dense / line.split( None, 1 )[1].strip()
				if texture.exists():
					shutil.copy2( texture, result )
		self.report[ 'result_mb' ] = disk_mb( result )

	def _tiling( self ):
		"""3D Tiles with levels of detail straight from Obj2Tiles (benchmarks; the platform's tiling job does this)."""
		lon, lat, alt = self.report.get( 'placement' ) or ( 0.0, 0.0, 0.0 )
		tiles = self.paths['tiles']
		shutil.rmtree( tiles, ignore_errors = True )
		# OpenMVS writes a Z-up OBJ; Obj2Tiles assumes Y-up unless told, and the model would stand on its edge
		self._cmd( [ self.tools.obj2tiles, '--y-up-to-z-up', '--lods', self.preset['lods'], '--divisions', 2, '--lat', lat, '--lon', lon,
			'--alt', alt, self.paths['dense'] / 'model_zup.obj', tiles ], 'tiling' )
		self.report[ 'tiles_mb' ] = disk_mb( tiles )


def disk_mb( path ):
	return round( sum( f.stat().st_size for f in Path( path ).rglob( '*' ) if f.is_file() ) / 2 ** 20 )
