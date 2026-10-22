function createPoint( cartesian )
{
	var point = new Cesium.Entity({
		position : cartesian,
		name : 'point',
		point:{
			outlineWidth : 5,
			outlineColor: Cesium.Color.RED,
		}
	});
	viewer.entities.add( point );
	return point;
}
function createPolyline( positionArray, color )
{
	color = color || Cesium.Color.YELLOW;
	var  polyline = viewer.entities.add({
           name : 'polyline',
           polyline : {
               positions : positionArray,
               material: color,
               width : 2
           }
       });
	return polyline;
}
function createLabel( cartesian, message, eyeOffset )
{
	eyeOffset = eyeOffset || new Cesium.Cartesian3( 0.0, 0.0, -1.0 );
	var label = viewer.entities.add({
		position : cartesian,
		name : 'label',
		label : {
			text: message,
			font: '15px Helvetica',
			fillColor: Cesium.Color.SKYBLUE,
			showBackground: true,
			backgroundColor: new Cesium.Color(0.0, 0.0, 0.0, 0.5),
			style: Cesium.LabelStyle.FILL_AND_OUTLINE,
			scaleByDistance: new Cesium.NearFarScalar(100, 1.0, 200, 0.4),
			eyeOffset : eyeOffset,
		}
	});
	return label;
}

function removeAllEntity()
{
	//for(let i=0;i<viewer.entities.values.length;++i)
	//{
	//	if(viewer.entities.values[i].parent!==static_showLabel)
	//	{
	//		viewer.entities.remove(viewer.entities.values[i]);
	//		--i;
	//	}
	//}
	viewer.entities.removeAll();
	//viewer.screenSpaceEventHandler.removeInputAction( Cesium.ScreenSpaceEventType.LEFT_CLICK );
	//if( Cesium.defined( handler ) && !handler.isDestroyed() )
	//	handler.destroy();


}