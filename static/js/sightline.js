function sightline()
{
	var scene = viewer.scene;
	var handler = new Cesium.ScreenSpaceEventHandler( viewer.canvas );
	var floatingPoint, noticeLabel;
	var polyline = [];
	var activePolyline;
	var dynamicPositions;
	//mobile
	//var lastPolylineGeo;
	function createSightLine( polyline )
	{
		var intersection, intPosition;
		var temp = new Cesium.Cartesian3( 0.0, 0.0, 0.0 );
		var direction = Cesium.Cartesian3.normalize( Cesium.Cartesian3.subtract( polyline[1], polyline[0], temp ), temp );
		ray = new Cesium.Ray( polyline[0], direction );
		
		intersection = scene.pickFromRay( ray );
		intPosition = intersection.position;
		if( intersection && intPosition )
		{
			createPolyline( [ polyline[0], intPosition ], Cesium.Color.GREEN );
			createPolyline( [ intPosition, polyline[1] ], Cesium.Color.RED );
			//createPoint( intPosition );
		}
		else
			createPolyline( polyline.concat(), Cesium.Color.GREEN );
	}
	handler.setInputAction(function( evt ) {
		if( scene !== Cesium.SceneMode.MORPHING ) {
			var pickedObject = scene.pick( evt.position );
			if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) )
			{
				var cartesian = scene.pickPosition( evt.position );
				if( judgeDevice() )
				{
					if( 0 === polyline.length )
					{
						floatingPoint = createPoint( cartesian );
						//eyeBillboard = viewer.entities.add({
						//	position : cartesian,
						//	billboard : {
						//		image : '/static/icon/eye.svg',
						//		width : 20,
						//		height : 20,
						//	}
						//});
						noticeLabel = createLabel( cartesian , '右键单击结束分析', new Cesium.Cartesian3( 0.0, 1.5, 0.0 ) );
						polyline.push( cartesian );
						dynamicPositions = new Cesium.CallbackProperty( function() {
							return polyline;
						}, false );
						activePolyline = createPolyline( dynamicPositions );
						polyline.push( cartesian );
					}
					else if( 2 === polyline.length && viewer.entities.contains( floatingPoint ) )
						createSightLine( polyline );
				}
				else
				{
					createPoint( cartesian );
					if( 0 === polyline.length)
						noticeLabel = createLabel( cartesian , '双指触屏结束分析', new Cesium.Cartesian3( 0.0, 1.5, 0.0 ) );
					polyline.push( cartesian );
					if( 2 === polyline.length )
					{
						createSightLine( polyline );
						polyline.pop();
						if( noticeLabel && viewer.entities.contains( noticeLabel ) )
							noticeLabel.position.setValue( cartesian );
					}
				}
			}
		}
		
	},Cesium.ScreenSpaceEventType.LEFT_CLICK );

	if( judgeDevice() )
	{
		handler.setInputAction(function( evt ) {
			if( scene !== Cesium.SceneMode.MORPHING ) {
				var pickedObject = scene.pick( evt.endPosition );
				if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) && Cesium.defined( floatingPoint )  ) { 
					var cartesian = scene.pickPosition( evt.endPosition );
					floatingPoint.position.setValue( cartesian );
					noticeLabel.position.setValue( cartesian );
					polyline.pop();
					polyline.push( cartesian );	
				}
			}
		},Cesium.ScreenSpaceEventType.MOUSE_MOVE );
		handler.setInputAction(function( evt ) {
			if( handler && !handler.isDestroyed() )
				handler.destroy();
			if( activePolyline && viewer.entities.contains( activePolyline ) )
				viewer.entities.remove( activePolyline );
			if( floatingPoint && viewer.entities.contains( floatingPoint ) )
				viewer.entities.remove( floatingPoint );
			if( noticeLabel && viewer.entities.contains(noticeLabel) )
				viewer.entities.remove( noticeLabel );
		},Cesium.ScreenSpaceEventType.RIGHT_CLICK );
	}
	else
	{
		handler.setInputAction(function( evt ) {
			begintime_ms = new Date();
		},Cesium.ScreenSpaceEventType.PINCH_START  );
		handler.setInputAction(function(evt) {
			var endtime_ms = new Date(); 
			if( 200 > endtime_ms.getTime() - begintime_ms.getTime() )
			{
				if( noticeLabel && viewer.entities.contains(noticeLabel) )
					viewer.entities.remove( noticeLabel );
				if( handler && !handler.isDestroyed() )
					handler.destroy();
			}
		},Cesium.ScreenSpaceEventType.PINCH_END );
	}
}



