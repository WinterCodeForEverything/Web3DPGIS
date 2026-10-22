function getTriangleDistance()
{
	var scene = viewer.scene;
	var measure_handler = new Cesium.ScreenSpaceEventHandler( scene.canvas );
	var ellipsoid = scene.globe.ellipsoid;
	var line = [];
	var floatPoint;
	function createTriangle( line )
	{
		var cart0 = ellipsoid.cartesianToCartographic( line[0] );
		var cart1 = ellipsoid.cartesianToCartographic( line[1] );
		if( Math.abs(cart0.height - cart1.height) > 0.5 )
		{
			var cartCompare0 = cart0.height > cart1.height ? cart0 : cart1;
			var cartCompare1 = cartCompare0 === cart1 ? cart0 : cart1;
			var newCartographic = new Cesium.Cartographic( cartCompare1.longitude, cartCompare1.latitude, cartCompare0.height );
			var newCartesian = ellipsoid.cartographicToCartesian( newCartographic );
			line.push( newCartesian );
			line.push( line[0] );
		}
		createPolyline( line );
		for ( var i = 0; i < line.length - 1; i++ )
		{
			var distance = Cesium.Cartesian3.distance( line[i], line[i+1] );
			var message = '距离：' + String(distance.toFixed(2)) + 'm';
			var centerPostion = new Cesium.Cartesian3( (line[i].x+line[i+1].x)/2, (line[i].y+line[i+1].y)/2, (line[i].z+line[i+1].z)/2);
			createLabel( centerPostion, message );
		}
	}
	measure_handler.setInputAction( function( evt ) {
		if( scene !== Cesium.SceneMode.MORPHING ) {
			var pickedObject = scene.pick( evt.position );
			if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) ) {
				var cartesian = scene.pickPosition( evt.position );
				if ( judgeDevice() )
				{
					if( 0 === line.length )
					{
						floatPoint = createPoint( cartesian );
						line.push( cartesian );
						var dynamicPositions = new Cesium.CallbackProperty(function() {
							return line;
						}, false);
						activePolyline = createPolyline( dynamicPositions );
						line.push( cartesian );
						createPoint( cartesian );
					}
					else if( 2 === line.length )
					{
						createTriangle( line );
						if( Cesium.defined( measure_handler ) && !measure_handler.isDestroyed() )
							measure_handler.destroy();
					}
				}
				else
				{
					line.push( cartesian );
					createPoint( cartesian );
					if( 2 === line.length )
					{
						createTriangle( line );
						if( Cesium.defined( measure_handler ) && !measure_handler.isDestroyed() )
							measure_handler.destroy();
					}
				}

			}
		}
	},Cesium.ScreenSpaceEventType.LEFT_CLICK );

	if ( judgeDevice() )
	{
		measure_handler.setInputAction( function( evt ) {
			if( scene !== Cesium.SceneMode.MORPHING ) {
				var pickedObject = scene.pick( evt.endPosition );
				if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) ) {
					var cartesian = scene.pickPosition( evt.endPosition );
					if( 2 === line.length && Cesium.defined(floatPoint) )
					{
						floatPoint.position.setValue( cartesian );
						line.pop();
						line.push( cartesian );
					}	
				}
			}
		}, Cesium.ScreenSpaceEventType.MOUSE_MOVE );
	}
}