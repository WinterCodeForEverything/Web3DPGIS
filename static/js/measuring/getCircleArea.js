function getCircleArea()
{
	var scene = viewer.scene;
	var ellipsoid = scene.globe.ellipsoid;
	var center;
	var line = [];
	var floatingPoint;
	var activeline;
	var measure_handler = new Cesium.ScreenSpaceEventHandler( viewer.canvas );
	measure_handler.setInputAction(function( evt ) {
		if( scene !== Cesium.SceneMode.MORPHING ) {
			var pickedObject = scene.pick( evt.position );
			if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) ) {
				var cartesian = scene.pickPosition( evt.position );
				if( 0 === line.length )
				{
					center = cartesian;
					createPoint( center );
					line.push( center );
					floatingPoint = createPoint( center );
					line.push( center );
					var dynamicPositions = new Cesium.CallbackProperty( function() {
						return line;
					},false);
					activeline = createPolyline( dynamicPositions );
				}
				else if( 2 === line.length )
				{
					var centerHeight = ellipsoid.cartesianToCartographic( center ).height;
					var borderCartographic = ellipsoid.cartesianToCartographic( cartesian );
					var borderCartesian = ellipsoid.cartographicToCartesian( new Cesium.Cartographic(borderCartographic.longitude, borderCartographic.latitude, centerHeight ) );
					var radius = Cesium.Cartesian3.distance( center, borderCartesian );
					var radiusPostion = new Cesium.Cartesian3( (center.x+borderCartesian.x)/2, (center.y+borderCartesian.y)/2, (center.z+borderCartesian.z)/2);
					createLabel( radiusPostion, '半径：' + String(radius.toFixed(2)) + ' m' );
					if( Cesium.defined( floatingPoint ) && viewer.entities.contains( floatingPoint ) )
						viewer.entities.remove( floatingPoint );
					if( Cesium.defined( activeline ) && viewer.entities.contains( activeline ) )
						viewer.entities.remove( activeline );
					createCircle( center, radius, centerHeight );
					var circleArea = Math.PI * radius * radius;
					var message = '面积：' + String(circleArea.toFixed(2)) + ' m2';
					createLabel( center, message );
					if( Cesium.defined( measure_handler ) && !measure_handler.isDestroyed() )
						measure_handler.destroy();
				}
			}
		}
	},Cesium.ScreenSpaceEventType.LEFT_CLICK );
	
	measure_handler.setInputAction(function( evt ) {
		if( scene !== Cesium.SceneMode.MORPHING ) {
			var pickedObject = scene.pick( evt.endPosition );
			if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) && Cesium.defined( floatingPoint ) ) {
				var cartesian = scene.pickPosition( evt.endPosition );
				floatingPoint.position.setValue( cartesian );
				line.pop();
				line.push( cartesian );
			}
		}
	},Cesium.ScreenSpaceEventType.MOUSE_MOVE );
	
	function createCircle( center, radius, height )
	{
		var circle = viewer.entities.add({
			name: 'circle',
			position : center,
			ellipse: {
				height : height,
				semiMajorAxis: radius,
				semiMinorAxis: radius,
				material : Cesium.Color.YELLOW.withAlpha( 0.7 ),
				outline : true,
				outlineColor : Cesium.Color.RED
			}
		});
		return circle;
	}
}