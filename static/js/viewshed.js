function viewshed()
{
	var scene = viewer.scene;
	var handler = new Cesium.ScreenSpaceEventHandler( viewer.canvas );
	handler.setInputAction( function( evt ) {
		if( scene !== Cesium.SceneMode.MORPHING ) {
			var pickedObject = scene.pick( evt.position );
			if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) ) {
				var cartesian = scene.pickPosition( evt.position );
				var frustum = new Cesium.PerspectiveFrustum({
					fov : Cesium.Math.PI_OVER_THREE / 3,
					aspectRatio : viewer.canvas.clientWidth / viewer.canvas.clientHeight,
					near : 1.0,
					far : 100.0
				});
				var cullVol = frustum.computeCullingVolume( cartesian, 
															new Cesium.Cartesian3( 1.0, 1.0, 1.0 ), 
															new Cesium.Cartesian3( 1.0, 1.0, 1.0 ) );
				var frustumGeo = new Cesium.FrustumGeometry({
					frustum: frustum,
					origin: cartesian,
					orientation: new Cesium.Quaternion( 0.5, 0.5, 0.5, 0.5 ),
				});
				var frustumGeoIns = new Cesium.GeometryInstance({
						geometry : frustumGeo,
						//modelMatrix : Cesium.Matrix4.multiplyByTranslation(Cesium.Transforms.eastNorthUpToFixedFrame(
						//Cesium.Cartesian3.fromDegrees(-75.59777, 40.03883)), new Cesium.Cartesian3(0.0, 0.0, 1000000.0), new Cesium.Matrix4()),
						//attributes : {
						//	color : Cesium.ColorGeometryInstanceAttribute.fromColor(Cesium.Color.AQUA)
						//},
						//id : 'test'
				});
				scene.primitives.add(new Cesium.Primitive({
					geometryInstances : frustumGeo,
					attributes: {
						color: new Cesium.ColorGeometryInstanceAttribute(1.0, 0.0, 0.0, 0.8)
					},
				}));
			}
		}
	},Cesium.ScreenSpaceEventType.LEFT_CLICK );
}