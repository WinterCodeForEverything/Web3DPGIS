function getPolygonArea()
{
	var scene = viewer.scene;
	var floatingPoint;
	var activePolygon;
	var polygon = [];
	var	noticeLabel;
	var measure_handler = new Cesium.ScreenSpaceEventHandler( viewer.canvas );
	//mobile
	var begintime_ms;
	measure_handler.setInputAction(function( evt ) {
		if( scene !== Cesium.SceneMode.MORPHING ) {
			var pickedObject = scene.pick( evt.position );
			if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) ) {
				var cartesian = scene.pickPosition( evt.position );
				if ( judgeDevice() )
				{
					if( polygon.length === 0 ){
						floatingPoint = createPoint( cartesian );
						noticeLabel = createLabel( cartesian, "左键双击结束", new Cesium.Cartesian3( 0.0, 1.5, 0.0 ) );
						polygon.push( cartesian );
						var dynamicPositions = new Cesium.CallbackProperty( function() {
							return polygon;
						},false);
						activePolygon = createPolygon( dynamicPositions );
					}
				}
				else
				{
					if( polygon.length === 0 )
						noticeLabel = createLabel( cartesian, "双指触屏结束", new Cesium.Cartesian3( 0.0, 1.5, 0.0 ) );
					if( Cesium.defined( noticeLabel ) && viewer.entities.contains( noticeLabel ))
						noticeLabel.position.setValue( cartesian );
					if( Cesium.defined( activePolygon ) && viewer.entities.contains( activePolygon ) )
						viewer.entities.remove( activePolygon );
					activePolygon = createPolygon( polygon );
				}

				polygon.push( cartesian );
				createPoint( cartesian );
			}
		}
	},Cesium.ScreenSpaceEventType.LEFT_CLICK );
	
	if( judgeDevice() )
	{
		measure_handler.setInputAction(function( evt ) {
			if( scene !== Cesium.SceneMode.MORPHING ) {
				var pickedObject = scene.pick( evt.endPosition );
				if ( scene.pickPositionSupported && Cesium.defined( pickedObject ) && Cesium.defined( floatingPoint ) ) { 
					var cartesian = scene.pickPosition( evt.endPosition );
					floatingPoint.position.setValue( cartesian );
					noticeLabel.position.setValue( cartesian );
					polygon.pop();
					polygon.push( cartesian );
				}
			}
		},Cesium.ScreenSpaceEventType.MOUSE_MOVE );
	
		measure_handler.setInputAction(function( evt ) {
			polygon.pop();
			polygon.pop();
			if( Cesium.defined( floatingPoint ) && viewer.entities.contains( floatingPoint ) )
				viewer.entities.remove( floatingPoint );
			if( Cesium.defined( measure_handler ) && !measure_handler.isDestroyed() )
				measure_handler.destroy();
			if( Cesium.defined( noticeLabel ) && viewer.entities.contains( noticeLabel ) )
				viewer.entities.remove( noticeLabel );
			if( polygon.length >= 3 )
			{
				polygon.push(polygon[0]);
				polygon.push(polygon[1]);
				var cross = new Cesium.Cartesian3();
				Cesium.Cartesian3.cross( 
					new Cesium.Cartesian3( polygon[1].x - polygon[0].x, polygon[1].y -polygon[0].y, polygon[1].z -polygon[0].z ),
					new Cesium.Cartesian3(  polygon[2].x - polygon[0].x, polygon[2].y -polygon[0].y, polygon[2].z -polygon[0].z ),
					cross
				);
				var normal = new Cesium.Cartesian3();
				Cesium.Cartesian3.normalize( cross, normal );
				var polygonArea = area3D_Polygon( polygon, normal );
				var message = '面积：'+ String(polygonArea.toFixed(2)) + ' m²';
				createLabel( getPolygonCenter( polygon ), message );
			}
			//polygon = [];
		},Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK );
	}
	else
	{
		measure_handler.setInputAction(function( evt ) {
			begintime_ms = new Date();
		},Cesium.ScreenSpaceEventType.PINCH_START  );
		measure_handler.setInputAction(function(evt) {
			var endtime_ms = new Date(); 
			if( 200 > endtime_ms.getTime() - begintime_ms.getTime() )
			{
				if( Cesium.defined( floatingPoint ) && viewer.entities.contains( floatingPoint ) )
					viewer.entities.remove( floatingPoint );
				if( Cesium.defined( measure_handler ) && !measure_handler.isDestroyed() )
					measure_handler.destroy();
				if( Cesium.defined( noticeLabel ) && viewer.entities.contains( noticeLabel ) )
					viewer.entities.remove( noticeLabel );
				if( polygon.length >= 3 )
				{
					polygon.push(polygon[0]);
					polygon.push(polygon[1]);
					var cross = new Cesium.Cartesian3();
					Cesium.Cartesian3.cross( 
						new Cesium.Cartesian3( polygon[1].x - polygon[0].x, polygon[1].y -polygon[0].y, polygon[1].z -polygon[0].z ),
						new Cesium.Cartesian3(  polygon[2].x - polygon[0].x, polygon[2].y -polygon[0].y, polygon[2].z -polygon[0].z ),
						cross
					);
					var normal = new Cesium.Cartesian3();
					Cesium.Cartesian3.normalize( cross, normal );
					var polygonArea = area3D_Polygon( polygon, normal );
					var message = '面积：'+ String(polygonArea.toFixed(2)) + ' m²';
					createLabel( getPolygonCenter( polygon ), message );
				}
			}
		},Cesium.ScreenSpaceEventType.PINCH_END );
	}

	function createPolygon(positionData) {	
		var polygon = viewer.entities.add({
			name: 'polygon',
			positions : positionData,
			polygon:{
				hierarchy : positionData,
				perPositionHeight: true,
				material: Cesium.Color.YELLOW.withAlpha( 0.7 ),
				outline: true,
				outlineColor: Cesium.Color.RED.withAlpha( 1 ),
			}
		});
		return polygon;
	}

	function getPolygonCenter( pointArr )
	{
		var num = pointArr.length;
		var x = 0.0, y = 0.0, z = 0.0;
		for( var i = 0; i < num; i++ )
		{
			x += pointArr[i].x;
			y += pointArr[i].y;
			z += pointArr[i].z;
		}
		x /= num;
		y /= num;
		z /= num;
		return new Cesium.Cartesian3( x, y, z );
	}

	function area3D_Polygon( pointArr, normal )
	{	
		var area = 0;	
		var an, ax, ay, az;  // abs value of normal and its coords
		var   coord;           // coord to ignore: 1=x, 2=y, 3=z
		var   i, j, k;         // loop indices	
		
		// select largest abs coordinate to ignore for projection	
		ax = (normal.x>0 ? normal.x : -normal.x);     // abs x-coord
		ay = (normal.y>0 ? normal.y : -normal.y);     // abs y-coord	
		az = (normal.z>0 ? normal.z : -normal.z);     // abs z-coord
			
		coord = 3;                     // ignore z-coord	
		if (ax > ay) {
			if (ax > az) coord = 1;    // ignore x-coord	
		}	
		else if (ay > az) coord = 2;   // ignore y-coord	
		
		
		// compute area of the 2D projection	
		for (i=1, j=2, k=0; j < pointArr.length; i++, j++, k++)
			switch ( coord ) {
				case 1:
					area += (pointArr[i].y * (pointArr[j].z - pointArr[k].z));
					continue;	
				case 2:
					area += (pointArr[i].x * (pointArr[j].z - pointArr[k].z));
					continue;	
				case 3:	
					area += (pointArr[i].x * (pointArr[j].y - pointArr[k].y));
					continue;	
			}		
		
		// scale to get area before projection	
		an = Math.sqrt( ax*ax + ay*ay + az*az );  // length of normal vector
		switch (coord) {	
		case 1:	
			area *= (an / (2 * ax));	
			break;	
		case 2:	
			area *= (an / (2 * ay));	
			break;	
		case 3:	
			area *= (an / (2 * az));
		}	
		return Math.abs(area);
	
	}
}