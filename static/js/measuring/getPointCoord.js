function getPointCoord()
{
	var scene = viewer.scene;
	var measure_handler = new Cesium.ScreenSpaceEventHandler( scene.canvas );
	var ellipsoid = scene.globe.ellipsoid;
	measure_handler.setInputAction( function( evt ){
		if( scene !== Cesium.SceneMode.MORPHING ) {
			var pickedObject = scene.pick( evt.position );
			if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) ) { 
				var cartesian = scene.pickPosition( evt.position );
				createPoint( cartesian );
				var cartographic = ellipsoid.cartesianToCartographic(cartesian);
				var lng = Cesium.Math.toDegrees(cartographic.longitude);
				var lat = Cesium.Math.toDegrees(cartographic.latitude);
				var alt = cartographic.height;
				var message = '经度：' + String(lng.toFixed(4))+'\n纬度：' + String(lat.toFixed(4)) + '\n高度：' + String(alt.toFixed(4));
				createLabel( Cesium.Cartesian3.fromDegrees(lng, lat, alt + 1), message );
				measure_handler.destroy();
			}
		}
	}, Cesium.ScreenSpaceEventType.LEFT_CLICK );
}