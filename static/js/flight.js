$( function(){
	var pointsArray_flight;
	var newFlag_flight = false;
	var pathName_flight;
	var flightFlag_flight = false;
	var prjID_flight;
	
	function GetID()
	{
		let url = url_flight;
		prjID_flight=GetURLPara(url,"id");
		let path=GetURLPara(url,"path");
		if(!path)
		{
			$("#flightButtons").removeClass("btn-group");
			$("#newFlight").css("display","none");
			$("#addPoint").css("display","none");
			$("#savePoints").css("display","none");
			$("#playFlight").css("float","right");
			$("#stopPlayFlight").css("float","right");
			$("#deleteFlight").css("display","none");
		}
	}
	
	$('#viewer_flight').click( function(){
		GetID();
		if(!flightFlag_flight)
		{
			$("#flysight").css("display","block");
			$("#flightPaths").change(SeleteChange);
			$.ajaxSetup({data: {csrfmiddlewaretoken: csrf_token_flight}});
			$.ajax({
				type: 'POST',
				url: getFlightPoints_url,
				traditional:true,
				dataType: 'JSON',
				data: { model_id : prjID_flight },
				success: function(data) {
					if (data.status == 'success')
					{
						for(i in data.model_path)
						{
							$("#flightPaths").append("<option value='"+data.model_path[i]+"'>"+data.model_path[i]+"</option>");
						}
						SeleteChange();
					}
				},
			});
			$("#newFlight").click(NewFlight);
			$("#addPoint").attr("disabled","disabled");
			$("#addPoint").click(PathAddPoint);
			$("#savePoints").attr("disabled","disabled");
			$("#savePoints").click(PathSavePoints);
			$("#playFlight").click(PlayFlight);
			$("#stopPlayFlight").click(StopPlayFlight);
			$("#stopPlayFlight").attr("disabled","disabled");
			$("#deleteFlight").click(function(){Confirm("是否确认删除当前路径？",DeleteFlight)});
			flightFlag_flight=true;
		}
		else
		{
			pointsArray_flight=[];
			$("#flightPaths").empty();
			$("#flightPaths").unbind("change");
			$("#newFlight").unbind("click");
			$("#addPoint").unbind("click");
			$("#savePoints").unbind("click");
			$("#playFlight").unbind("click");
			$("#stopPlayFlight").unbind("click");
			$("#deleteFlight").unbind("click");
			$("#flysight").css("display","none");
			flightFlag_flight=false;
		}
	});

	$('#viewer_cancel').click(function(){
		if( flightFlag_flight )
			$("#viewer_flight").click();
	});
	
	function DeleteFlight()
	{
		$.ajaxSetup({data: {csrfmiddlewaretoken: csrf_token_flight}});
		$.ajax({
			type: 'POST',
			url: deleteFlightPath_url,
			traditional:true,
			dataType: 'JSON',
			data: { model_id : prjID_flight, path_name : $("#flightPaths").val()},
			success: function(data) {
				if (data.status == 'success') {
					Alert("删除成功！");
					$("#flightPaths option[value='"+$("#flightPaths").val()+"']").remove();
					ChangePath(prjID_flight,$("#flightPaths").val());
				}
				else {
					Alert("删除失败，请重试！");
				}
			},
		});
	}
	
	function PathAddPoint()
	{
		pointsArray_flight.push( [ viewer.camera.positionWC.x, viewer.camera.positionWC.y, viewer.camera.positionWC.z, 
							viewer.camera.directionWC.x, viewer.camera.directionWC.y, viewer.camera.directionWC.z, 
							viewer.camera.upWC.x, viewer.camera.upWC.y, viewer.camera.upWC.z ] );
		let i=pointsArray_flight.length-1;
		let id = pathName_flight+"_"+i;
		let point = pointsArray_flight[i];
		$("#flightPoints").append("<div id='"+id+"' class='font-white'>"+i+"</div>");
		$("#"+id).click(function(){
			viewer.camera.flyTo({
				destination : new Cesium.Cartesian3( point[0], point[1], point[2] ),
				orientation : {
					direction : new Cesium.Cartesian3( point[3], point[4], point[5] ),
					up : new Cesium.Cartesian3( point[6], point[7], point[8] )
				}
			});
		});
	}
	
	function PathSavePoints()
	{
		if(pointsArray_flight.length==0)
		{
			Alert("路径为空！");
			return;
		}
		$.ajaxSetup({data: {csrfmiddlewaretoken: csrf_token_flight}});
		$.ajax({
			type: 'POST',
			url: saveFlightPath_url,
			traditional:true,
			dataType: 'JSON',
			data: { model_id : prjID_flight, path_name : pathName_flight, pointsArray: pointsArray_flight },
			success: function(data) {
				if (data.status == 'success') {
					Alert("保存成功！");
					$("#addPoint").attr("disabled","disabled");
					$("#savePoints").attr("disabled","disabled");
					$("#deleteFlight").removeAttr("disabled");
					newFlag_flight=false;
				}
				else {
					Alert("保存失败，请重试！");
				}
			},
		});
	}
	
	function NewFlight()
	{
		if(!newFlag_flight)
		{
			Prompt("请输入路径名：",function(){
				pathName_flight = $.trim($("#promptInput").val());
				if(!pathName_flight)
				{
					return;
				}
				if($("#flightPaths option[value='"+pathName_flight+"']").length>0)
				{
					Alert("路径名重复！");
					return;
				}
				
				$("#flightPaths").append("<option value='"+pathName_flight+"'>"+pathName_flight+"</option>");
				$("#flightPaths").val(pathName_flight);
				pointsArray_flight=[];
				$("#flightPoints").empty();
				
				$("#addPoint").removeAttr("disabled");
				$("#savePoints").removeAttr("disabled");
				$("#deleteFlight").attr("disabled","disabled");
				newFlag_flight=true;
			});
		}
		else
		{
			$("#flightPaths option[value='"+pathName_flight+"']").remove();
			pointsArray_flight=[];
			$("#flightPoints").empty();
			
			$("#addPoint").attr("disabled","disabled");
			$("#savePoints").attr("disabled","disabled");
			$("#deleteFlight").removeAttr("disabled");
			newFlag_flight = false;
		}
		
	}
	
	function SeleteChange()
	{
		if(newFlag_flight)
		{
			Confirm("当前新建路径未保存，是否取消新建？",function(){
				NewFlight();
				ChangePath(prjID_flight,$("#flightPaths").val());
			},function(){
				$("#flightPaths").val(pathName_flight);
				ChangePath(prjID_flight,$("#flightPaths").val());
			});
		}
		else
		{
			ChangePath(prjID_flight,$("#flightPaths").val());
		}
	}
	
	function PlayFlight()
	{
		if(pointsArray_flight.length<2)
		{
			return;
		}
		$("#stopPlayFlight").removeAttr("disabled");
		$("#playFlight").attr("disabled","disabled");
		flyviewer(0);
	}
	
	function StopPlayFlight()
	{
		$("#playFlight").removeAttr("disabled");
		$("#stopPlayFlight").attr("disabled","disabled");
		viewer.camera.cancelFlight();
	}
	
	function flyviewer(index)
	{
		if(index >= pointsArray_flight.length)
		{
			index=0;
		}
		viewer.camera.flyTo({
			destination : new Cesium.Cartesian3( pointsArray_flight[index][0], pointsArray_flight[index][1], pointsArray_flight[index][2] ),
			orientation : {
				direction : new Cesium.Cartesian3( pointsArray_flight[index][3], pointsArray_flight[index][4], pointsArray_flight[index][5] ),
				up : new Cesium.Cartesian3( pointsArray_flight[index][6], pointsArray_flight[index][7], pointsArray_flight[index][8] ),
				//duration : 5,
			},
			complete: function () {
				flyviewer( ++index );
			}
		});
	}
	
	function ChangePath(modelid,pathName_flight)
	{
		pointsArray_flight = [];
		$.ajaxSetup({data: {csrfmiddlewaretoken: csrf_token_flight}});
		$.ajax({
			type: 'POST',
			url: getFlightPoints_url,
			traditional:true,
			dataType: 'JSON',
			data: { model_id : modelid, path_name : pathName_flight },
			success: function(data) {
				if (data.status == 'success')
				{
					let pointsResponse = data.pointsResponse;
					let id;
					$("#flightPoints").empty();
					for( var i in pointsResponse )
					{
						let point=pointsResponse[i];
						pointsArray_flight.push( point.map( function( item ){ return parseFloat( item ) } ) );
						id = pathName_flight+"_"+i;
						$("#flightPoints").append("<div id='"+id+"' class='font-white'>"+i+"</div>");
						$("#"+id).click(function(){
							viewer.camera.flyTo({
								destination : new Cesium.Cartesian3( point[0], point[1], point[2] ),
								orientation : {
									direction : new Cesium.Cartesian3( point[3], point[4], point[5] ),
									up : new Cesium.Cartesian3( point[6], point[7], point[8] )
								}
							});
						});
					}
				}
			},
		});
	}
});