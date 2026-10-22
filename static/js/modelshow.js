( function() {
	Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJlMTI5YzA1Yy01MGExLTQ3YWEtYWUzMy1iZmYzOTUyMDU1N2UiLCJpZCI6MzkxMSwic2NvcGVzIjpbImFzciIsImdjIl0sImlhdCI6MTUzOTIxOTU5M30.QRMJyKhjZx-kuAx9v_H_z9q7xFP0ULpWwFRK-pLDZ9o';
	viewer = new Cesium.Viewer('cesiumContainer', {
								animation: false, //是否显示动画控件
								shouldAnimate : true,
								homeButton: false, //是否显示Home按钮
								fullscreenButton: true, //是否显示全屏按钮
								baseLayerPicker: false, //是否显示图层选择控件
								geocoder: false, //是否显示地名查找控件
								timeline: false, //是否显示时间线控件
								sceneModePicker: false, //是否显示投影方式控件
								//navigationHelpButton: false, //是否显示帮助信息控件
								infoBox: false, //是否显示点击要素之后显示的信息
								requestRenderMode: true, //启用请求渲染模式
								scene3DOnly: false, //每个几何实例将只能以3D渲染以节省GPU内存
								sceneMode: 3, //初始场景模式 1 2D模式 2 2D循环模式 3 3D模式  Cesium.SceneMode
								fullscreenElement: document.body, //全屏时渲染的HTML元素 暂时没发现用处
								//shadows: true,
								//terrainProvider: Cesium.createWorldTerrain(),
								//imageryProvider:new Cesium.WebMapServiceImageryProvider({
								//	url : window.location.host + ':8081/geoserver/cesium/wms',							
								//	layers: 'cesium:googlemap'// Here just give layer name
								//}), 
								imageryProvider : Cesium.createTileMapServiceImageryProvider({
									url : Cesium.buildModuleUrl('/static/ThirdParty/Cesium/Assets/Textures/NaturalEarthII'),
								}),
							});
	tileset = new Cesium.Cesium3DTileset({ url : model_url });
	tileset.readyPromise.then(function(tileset) {
			viewer.scene.primitives.add(tileset);
			var cartographic = Cesium.Cartographic.fromCartesian(tileset.boundingSphere.center);
			var surface = Cesium.Cartesian3.fromRadians(cartographic.longitude, cartographic.latitude, 0.0);
			var offset = Cesium.Cartesian3.fromRadians(cartographic.longitude, cartographic.latitude, relativeheight);
			var translation = Cesium.Cartesian3.subtract(offset, surface, new Cesium.Cartesian3());
			tileset.modelMatrix = Cesium.Matrix4.fromTranslation(translation);
			viewer.zoomTo(tileset, new Cesium.HeadingPitchRange(0.0, -0.5, tileset.boundingSphere.radius * 2.0));
		}).otherwise(function(error) {
			console.log(error);
	});
	navigationHelpButtonLang();
	//change the controller
	if (!judgeDevice()) {//移动设备上禁掉以下几个选项，可以相对更加流畅
		viewer.scene.fog.enable = false;
		viewer.scene.skyAtmosphere.show = false;
		viewer.scene.fxaa = false;
	}
	else{
		controller = viewer.scene.screenSpaceCameraController;
		controller.tiltEventTypes = Cesium.CameraEventType.RIGHT_DRAG;
		controller.zoomEventTypes = Cesium.CameraEventType.WHEEL;
		controller.rotateEventTypes = Cesium.CameraEventType.LEFT_DRAG;
	}

	viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
	viewer.cesiumWidget.screenSpaceEventHandler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_CLICK);
	
	//	viewermode/walkmode.js
	handler_walkmode = new Cesium.ScreenSpaceEventHandler( viewer.scene.canvas ); 

	//viewer.scene.imageryLayers.addImageryProvider(new Cesium.createTileMapServiceImageryProvider({
	//	url : "/static/googleMap/earth_jpg",
	//	credit : '',
	//	fileExtension: 'jpg',
	//	maximumLevel: 8,
	//	rectangle: new Cesium.Rectangle(
	//		Cesium.Math.toRadians(-180.0000),
	//		Cesium.Math.toRadians(-90.0000),
	//		Cesium.Math.toRadians(180.0000),
	//		Cesium.Math.toRadians(90.0000))
	//}));	
	//
	//viewer.scene.imageryLayers.addImageryProvider(new Cesium.createTileMapServiceImageryProvider({
	//	url : "/static/googleMap/guangzhou_jpg",
	//	credit : '',
	//	fileExtension: 'jpg',
	//	maximumLevel: 19,
	//	rectangle: new Cesium.Rectangle(
	//		Cesium.Math.toRadians(112.968521),
	//		Cesium.Math.toRadians(22.521906000000005),
	//		Cesium.Math.toRadians(114.06581400000003),
	//		Cesium.Math.toRadians(23.935575999999987))
	//}));
	
	//viewer.extend( Cesium.viewerCesiumInspectorMixin );
//汉化帮助按钮
function navigationHelpButtonLang() {
    //var viewer = this.viewer;
    if (viewer.navigationHelpButton) {
        viewer.navigationHelpButton.viewModel.tooltip = "操作指南";

        var clickHelper = viewer.navigationHelpButton.container.getElementsByClassName("cesium-click-navigation-help")[0];
        var touchHelper = viewer.navigationHelpButton.container.getElementsByClassName("cesium-touch-navigation-help")[0];

        var button = viewer.navigationHelpButton.container.getElementsByClassName("cesium-navigation-button-right")[0]
        button.innerHTML = button.innerHTML.replace(">Touch", ">手势");
        button = viewer.navigationHelpButton.container.getElementsByClassName("cesium-navigation-button-left")[0]
        button.innerHTML = button.innerHTML.replace(">Mouse", ">鼠标");
        
        var click_help_pan = clickHelper.getElementsByClassName("cesium-navigation-help-pan")[0];
        click_help_pan.innerHTML = "平移";
        var click_help_pan_details = click_help_pan.parentNode.getElementsByClassName("cesium-navigation-help-details")[0];
        click_help_pan_details.innerHTML = "按下左键 + 拖动";
        
        var click_help_zoom = clickHelper.getElementsByClassName("cesium-navigation-help-zoom")[0];
        click_help_zoom.innerHTML = "旋转";
        click_help_zoom.parentNode.getElementsByClassName("cesium-navigation-help-details")[0].innerHTML = "按下右键+拖动";
        click_help_zoom.parentNode.getElementsByClassName("cesium-navigation-help-details")[1].innerHTML = "";
        
        var click_help_rotate = clickHelper.getElementsByClassName("cesium-navigation-help-rotate")[0];
        click_help_rotate.innerHTML = "缩放";
        click_help_rotate.parentNode.getElementsByClassName("cesium-navigation-help-details")[0].innerHTML = "滚动鼠标滚轮";
        click_help_rotate.parentNode.getElementsByClassName("cesium-navigation-help-details")[1].innerHTML = "";

        //触屏操作
        var touch_help_pan = touchHelper.getElementsByClassName("cesium-navigation-help-pan")[0];
        touch_help_pan.innerHTML = "平移";
        touch_help_pan.parentNode.getElementsByClassName("cesium-navigation-help-details")[0].innerHTML = "单指拖动";

        var touch_help_zoom = touchHelper.getElementsByClassName("cesium-navigation-help-zoom")[0];
        touch_help_zoom.innerHTML = "缩放";
        touch_help_zoom.parentNode.getElementsByClassName("cesium-navigation-help-details")[0].innerHTML = "双指捏合";

        var touch_help_tilt = touchHelper.getElementsByClassName("cesium-navigation-help-rotate")[0];
        touch_help_tilt.innerHTML = "俯仰";
        touch_help_tilt.parentNode.getElementsByClassName("cesium-navigation-help-details")[0].innerHTML = "双指同向拖动";

        var touch_help_rotate = touchHelper.getElementsByClassName("cesium-navigation-help-tilt")[0];
        touch_help_rotate.innerHTML = "旋转";
        touch_help_rotate.parentNode.getElementsByClassName("cesium-navigation-help-details")[0].innerHTML = "双指反向拖动";

    }

}
}());

function judgeDevice()
{
	if (navigator.userAgent.toLowerCase().match(/(iphone|ipad|android|ios|windows mobile|windows ce|midp)/i))
		return false;
	return true;
}

function GetURLPara(url,text)
{
	if(url.indexOf(text)<0)
	{
		return null;
	}
	if(url.indexOf('&',url.indexOf(text))<0)
	{
		return url.slice(url.indexOf(text)+text.length+1,url.length);
	}
	else
	{
		return url.slice(url.indexOf(text)+text.length+1,url.indexOf('&',url.indexOf(text)));
	}
}

function Alert(text)
{
	$("#modal_alert p").text(text);
	$("#modal_alert").modal('show');
}

function Confirm(text,callback1)
{
	let callback2 = arguments[2]?arguments[2]:null;
	$("#modal_confirm p").text(text);
	$("#btnConfirmConfirm").unbind("click");
	$("#btnConfirmConfirm").click(callback1);
	$("#btnConfirmCancel").unbind("click");
	$("#btnConfirmCancel").click(callback2);
	$("#modal_confirm").modal('show');
}

function Prompt(text,callback1)
{
	let callback2 = arguments[2]?arguments[2]:null;
	$("#modal_prompt p strong").text(text);
	$("#btnPromptConfirm").unbind("click");
	$("#btnPromptConfirm").click(callback1);
	$("#btnPromptCancel").unbind("click");
	$("#btnPromptCancel").click(callback2);
	$("#promptInput").val("");
	$("#modal_prompt").modal('show');
}