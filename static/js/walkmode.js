$(function(){	
	let walkFlag = false;
	$('#viewer_walk').click(function(){
		if(!walkFlag)
		{
			SetWalkMode(viewer, handler_walkmode, 1);
			walkFlag = !walkFlag;
		}
		else
		{
			SetWalkMode(viewer,handler_walkmode,0);
			walkFlag = !walkFlag;
		}
	});
	$('#viewer_cancel').click(function(){
		SetWalkMode(viewer,handler_walkmode,0);
		walkFlag = !walkFlag;
	});
});
function SetWalkMode(viewer,handler,flag)
{
	let controller = viewer.scene.screenSpaceCameraController;
	
	let width = viewer.container.clientWidth/2;
	let height = viewer.container.clientHeight/2;
	
	
	let mousedown = false;
	let front = 1;
	let right = 1;
	let xoffset=1;
	let yoffset=1;
	
	let mouseCurrent = null;
	
	let moveFunc = function(e){
			if(mousedown)
			{
				let camera = Cesium.Cartographic.fromCartesian(viewer.camera.positionWC);
				if(!viewer.scene.pickPosition(new Cesium.Cartesian2(width,height)))
				{
					return;
				}
				let mid = Cesium.Cartographic.fromCartesian(viewer.scene.pickPosition(new Cesium.Cartesian2(width,height)));
				let cameracar3=viewer.camera.positionWC;
				let midcar3=Cesium.Cartesian3.fromRadians(mid.longitude,mid.latitude,camera.height);
				let dist=Cesium.Cartesian3.distance(midcar3, cameracar3);
				let direcar3=new Cesium.Cartesian3((midcar3.x-cameracar3.x)*front/dist,(midcar3.y-cameracar3.y)*front/dist,(midcar3.z-cameracar3.z)*front/dist);
				
				viewer.camera.move(direcar3,yoffset);
				viewer.camera.look(viewer.camera.position,0.008*right*xoffset);
			}
		};

	if(flag)
	{//set handler
		//set mouse
		controller.tiltEventTypes = Cesium.CameraEventType.RIGHT_DRAG;
		controller.zoomEventTypes = Cesium.CameraEventType.WHEEL;
		controller.rotateEventTypes = null;
		
		viewer.scene.postRender.addEventListener(moveFunc);
		
		//down
		handler.setInputAction(function(mouse) {
			mousedown = true;
			mouseCurrent = mouse.position;
			
			let camera = Cesium.Cartographic.fromCartesian(viewer.camera.positionWC);
			if(!viewer.scene.pickPosition(new Cesium.Cartesian2(width,height)))
			{
				return;
			}
			let mid = Cesium.Cartographic.fromCartesian(viewer.scene.pickPosition(new Cesium.Cartesian2(width,height)));
			let cameracar3=viewer.camera.positionWC;
			let midcar3=Cesium.Cartesian3.fromRadians(mid.longitude,mid.latitude,camera.height);
			let dist=Cesium.Cartesian3.distance(midcar3, cameracar3);
			let direcar3=new Cesium.Cartesian3((midcar3.x-cameracar3.x)*front/dist,(midcar3.y-cameracar3.y)*front/dist,(midcar3.z-cameracar3.z)*front/dist);
			
			viewer.camera.move(direcar3,yoffset);
			viewer.camera.look(viewer.camera.position,0.008*right*xoffset);
		}, Cesium.ScreenSpaceEventType.LEFT_DOWN);
		
		//move
		handler.setInputAction(function(mouse) {
			xoffset=2*Math.abs(mouse.endPosition.x-width)/width;
			yoffset=3*Math.abs(mouse.endPosition.y-height)/height;
			if(mouse.endPosition.y<(height-25))
			{
				front=1;
			}
			else if(mouse.endPosition.y>(height+25))
			{
				front=-1;
			}
			else
			{
				front=0;
			}
			if(mouse.endPosition.x>(width+25))
			{
				right=1;
			}
			else if(mouse.endPosition.x<(width-25))
			{
				right=-1;
			}
			else
			{
				right=0;
			}
			mouseCurrent = mouse.endPosition;
		}, Cesium.ScreenSpaceEventType.MOUSE_MOVE);
		
		//up
		handler.setInputAction(function(mouse) {
			mousedown = false;
		}, Cesium.ScreenSpaceEventType.LEFT_UP);
	}
	else
	{//unset handler
		handler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOWN);
		handler.removeInputAction(Cesium.ScreenSpaceEventType.MOUSE_MOVE);
		handler.removeInputAction(Cesium.ScreenSpaceEventType.LEFT_DOUBLE_CLICK);
		viewer.scene.postRender.removeEventListener(moveFunc);
		//set mouse
		if (!judgeDevice()) {//移动设备上禁掉以下几个选项，可以相对更加流畅
			controller = viewer.scene.screenSpaceCameraController;
			controller.tiltEventTypes = [Cesium.CameraEventType.MIDDLE_DRAG, Cesium.CameraEventType.PINCH, {
					eventType : Cesium.CameraEventType.LEFT_DRAG,
					modifier : Cesium.KeyboardEventModifier.CTRL
				}, {
					eventType : Cesium.CameraEventType.RIGHT_DRAG,
					modifier : Cesium.KeyboardEventModifier.CTRL
				}];
			controller.zoomEventTypes = [Cesium.CameraEventType.RIGHT_DRAG, Cesium.CameraEventType.WHEEL, Cesium.CameraEventType.PINCH];
			controller.rotateEventTypes = Cesium.CameraEventType.LEFT_DRAG;
			viewer.scene.fog.enabled = false;
			viewer.scene.skyAtmosphere.show = false;
			viewer.scene.postProcessStages.fxaa.enabled = false;
		}
		else{
			controller = viewer.scene.screenSpaceCameraController;
			controller.tiltEventTypes = Cesium.CameraEventType.RIGHT_DRAG;
			controller.zoomEventTypes = Cesium.CameraEventType.WHEEL;
			controller.rotateEventTypes = Cesium.CameraEventType.LEFT_DRAG;
		}
	}
}