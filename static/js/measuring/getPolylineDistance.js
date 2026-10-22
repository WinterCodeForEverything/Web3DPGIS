function getPolylineDistance()
{
	var scene = viewer.scene;
	var measure_handler = new Cesium.ScreenSpaceEventHandler(scene.canvas);
	var floatingPoint;
	var activePolyline;
	var polyline = [];
	var lastLabel;
	var	noticeLabel;
	var totalLength = 0.0;
	//mobile
	var totalDis_label_position;
	var begintime_ms;
	measure_handler.setInputAction(function( evt ) {
		if( scene !== Cesium.SceneMode.MORPHING ) {
			var pickedObject = scene.pick( evt.position );
			if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) ) {
				var cartesian = scene.pickPosition( evt.position );
				if( judgeDevice() )
				{
					if( 0 === polyline.length )
					{
						floatingPoint = createPoint( cartesian );
						noticeLabel = createLabel( cartesian, "左键双击结束", new Cesium.Cartesian3( 0.0, 1.5, 0.0 ) );
						polyline.push( cartesian );
						var dynamicPositions = new Cesium.CallbackProperty(function() {
							return polyline;
						},false);
						activePolyline = createPolyline( dynamicPositions );
					}
					polyline.push( cartesian );
					createPoint( cartesian );
					//create Label
					var pointNum = polyline.length - 1;
					if( pointNum > 1 )
					{
						var distance = Cesium.Cartesian3.distance( polyline[pointNum-1], polyline[pointNum-2] );
						var message = '距离：' + String(distance.toFixed(2)) + 'm';
						var centerPostion = new Cesium.Cartesian3( (polyline[pointNum-1].x+polyline[pointNum-2].x)/2, 
											(polyline[pointNum-1].y+polyline[pointNum-2].y)/2, (polyline[pointNum-1].z+polyline[pointNum-2].z)/2);
						lastLabel = createLabel( centerPostion, message );
						totalLength += distance;
					}					
				}
				else
				{
					if( 0 === polyline.length )
						noticeLabel = createLabel( cartesian, "双指触屏结束", new Cesium.Cartesian3( 0.0, 1.5, 0.0 ) );
					if( noticeLabel )
						noticeLabel.position.setValue( cartesian );
					polyline.push( cartesian );
					createPoint( cartesian );
					if( Cesium.defined( activePolyline ) && viewer.entities.contains( activePolyline ) )
						viewer.entities.remove( activePolyline );
					activePolyline = createPolyline( polyline );
					//create Label
					var pointNum = polyline.length - 1;
					if( pointNum >= 1 )
					{
						var distance = Cesium.Cartesian3.distance( polyline[pointNum], polyline[pointNum-1] );
						var message = '距离：' + String(distance.toFixed(2)) + 'm';
						var centerPostion = new Cesium.Cartesian3( (polyline[pointNum].x+polyline[pointNum-1].x)/2, 
											(polyline[pointNum].y+polyline[pointNum-1].y)/2, (polyline[pointNum].z+polyline[pointNum-1].z)/2);
						createLabel( centerPostion, message );
						totalLength += distance;
						totalDis_label_position = polyline[pointNum];
					}	
				}

			}
		}
	},Cesium.ScreenSpaceEventType.LEFT_CLICK );
	
	if(judgeDevice())
	{
		measure_handler.setInputAction(function( evt ) {
			if( scene !== Cesium.SceneMode.MORPHING ) {
				var pickedObject = scene.pick( evt.endPosition );
				if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) && Cesium.defined( floatingPoint ) ) {
					var cartesian = scene.pickPosition( evt.endPosition );
					floatingPoint.position.setValue( cartesian );
					noticeLabel.position.setValue( cartesian );
					polyline.pop();
					polyline.push( cartesian );	
				}
			}
		},Cesium.ScreenSpaceEventType.MOUSE_MOVE );
		measure_handler.setInputAction(function( evt ) {
			if( Cesium.defined( measure_handler ) && !measure_handler.isDestroyed() )
				measure_handler.destroy();
			if( Cesium.defined( lastLabel ) && viewer.entities.contains( lastLabel ) )
				viewer.entities.remove( lastLabel );	
			if( Cesium.defined( noticeLabel ) && viewer.entities.contains( noticeLabel ) )
				viewer.entities.remove( noticeLabel );
			var pickedObject = scene.pick( evt.position );
			if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) ) {
				var cartesian = scene.pickPosition( evt.position );		
				createLabel( cartesian, "总距离：" + String(totalLength.toFixed(2)) + 'm' );
			}
		},Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK );
	}
	else
	{
		measure_handler.setInputAction(function( evt ) {
			begintime_ms = new Date();
		},Cesium.ScreenSpaceEventType.PINCH_START  );

		measure_handler.setInputAction(function( evt ) {
			var endtime_ms = new Date(); 
			if( 200 > endtime_ms.getTime() - begintime_ms.getTime() )
			{
				
				if( Cesium.defined( measure_handler ) && !measure_handler.isDestroyed() )
					measure_handler.destroy();
				if( Cesium.defined( noticeLabel ) && viewer.entities.contains( noticeLabel ) )
					viewer.entities.remove( noticeLabel );
				if ( totalDis_label_position ) {
					createLabel( totalDis_label_position, "总距离：" + String(totalLength.toFixed(2)) + 'm' );
				}
			}
		},Cesium.ScreenSpaceEventType.PINCH_END  );
	}
		

}