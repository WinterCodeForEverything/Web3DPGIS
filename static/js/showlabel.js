function drawCanvas( sort, text, textw ) {
	let fontsize = 30;
	let canvas = document.createElement('canvas');//创建canvas标签
	let ctx = canvas.getContext('2d');
	
	ctx.font = fontsize + "px Calibri,sans-serif";
	canvas.width =  ctx.measureText( text ).width + fontsize;//根据文字内容获取宽度
	canvas.height = fontsize;
	ctx.globalAlpha = 0.7;
	ctx.fillStyle = "black";
	ctx.fillRect(fontsize,0,canvas.width,canvas.height);
	if (1 === sort )
		ctx.drawImage( placelabel, 0, 0, fontsize, fontsize );
	else if ( 2 === sort )
		ctx.drawImage( picturelabel, 0, 0, fontsize, fontsize );
	else if ( 3 === sort )
		ctx.drawImage( videolabel, 0, 0, fontsize, fontsize );
	ctx.fillStyle = 'white';
	ctx.globalAlpha = 1;
	ctx.font = fontsize + "px Calibri,sans-serif";
	ctx.fillText( text, fontsize, fontsize*5/6 );
	textw.a = fontsize/2;
	return canvas;
}

function addLabelClickEvent()
{
	let handler = new Cesium.ScreenSpaceEventHandler(viewer.scene.canvas);
	handler.setInputAction(function( movement ){
		let pickObject = viewer.scene.pick(movement.position);
		if( pickObject && pickObject.id && pickObject.id.parent )
		{
			//pick.id.id;
			$.ajaxSetup({data: {csrfmiddlewaretoken: csrf_token_showLabel}});
			$.ajax({
				type: 'POST',
				url: getLabelData_url,
				traditional:true,
				dataType: 'JSON',
				data: { model_id:GetURLPara( url_showLabel, "id" ),label_id : pickObject.id.id },
				success: function(data) {
					if ( data.status == 'success' )
					{
						$.each($.parseJSON(data.data),function( key,val ){
							//根据key查找数据字典
							$.each(dictionary_showLabel,function(i,j){
								//i==house j={}
								if(key==i)
								{
									showModalMarker(j,$.parseJSON(data.data));
								}
							});
						});
					}
				},
			});
		}
	},Cesium.ScreenSpaceEventType.LEFT_CLICK);
}

//显示已有
function showModalMarker(category,data)
{
	//居中
	$("#modal_marker #troot").empty();
	//分析数据字典增加div
	$.each(data,function(key,val){
		$("#modal_marker #troot").append("<tbody><tr><td id=\"table"+key+"\"></td></tr></tbody>");
		$("#modal_marker #table"+key).append("<p class=\"bg-primary\">"+category.description+"</p><table class=\"table\"><tbody></tbody></table>");
		$.each(category,function(i,j){
			if(i=="description")
				return;
			$("#modal_marker #table"+key+" tbody").append("<tr><td>"+j.description+"</td><td id=\"data"+i+"\"></td></tr>");
			//增加数据进入div
			$("#modal_marker #table"+key+" #data"+i).text(val[i]);
		});
	});
	
	//按钮
	$("#modal_marker").modal('show');
}

function getDataDictionary()
{
	$.ajaxSetup({data: {csrfmiddlewaretoken: csrf_token_showLabel}});
	$.ajax({
		type: 'POST',
		url: getDataDictionary_url,
		traditional:true,
		dataType: 'JSON',
		success: function(data) {
			if (data.status == 'success')
			{
				//解析json
				dictionary_showLabel = $.parseJSON(data.data).category;
			}
		},
	});
}

