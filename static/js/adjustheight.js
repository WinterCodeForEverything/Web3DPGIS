(function() {
	var viewModel = {
		height: relativeheight
	};
	Cesium.knockout.track(viewModel);
	var toolbar = document.getElementById('toolbar');
	Cesium.knockout.applyBindings(viewModel, toolbar);
	//adjust height 
	//viewer.scene.globe.depthTestAgainstTerrain = true;
	Cesium.knockout.getObservable(viewModel, 'height').subscribe(function(height) {
		height = Number(height);
		if (isNaN(height)) {
			return;
		}
	
		var cartographic = Cesium.Cartographic.fromCartesian(tileset.boundingSphere.center);
		var surface = Cesium.Cartesian3.fromRadians(cartographic.longitude, cartographic.latitude, 0.0);
		var offset = Cesium.Cartesian3.fromRadians(cartographic.longitude, cartographic.latitude, height);
		var translation = Cesium.Cartesian3.subtract(offset, surface, new Cesium.Cartesian3());
		tileset.modelMatrix = Cesium.Matrix4.fromTranslation(translation);
		relativeheight = height;
	});
}());

function saveHeight()
{
	Confirm("是否要保存当前高度？", function(){
		{
			$.ajaxSetup({data: {csrfmiddlewaretoken: csrf_token_height}});
			$.ajax({
				type: 'POST',
				url: adjustheight_url,
				traditional: true,
				dataType: 'JSON',
				data: { model_id : GetURLPara( window.location.href, "id"), relativeheight : relativeheight },
				success: function(data) {
					if ( data.status == 'success' )
					{
						Alert("保存成功！");
					}
					else
					{
						Alert("保存失败，请检查网络！");
					}
				},
			});
		}
	});
}