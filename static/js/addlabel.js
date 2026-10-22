var labelArray = [];
var label_bill_save = [];
var billboards = viewer.scene.primitives.add(new Cesium.BillboardCollection());

function addLabel( label_id ){
	let handler = new Cesium.ScreenSpaceEventHandler( viewer.canvas );
	$("#label_" + label_id).click( function(){
		handler.setInputAction( function( evt ){
			if( viewer.scene !== Cesium.SceneMode.MORPHING ) {
				var pickedObject = viewer.scene.pick( evt.position );
				if ( viewer.scene.pickPositionSupported && Cesium.defined( pickedObject ) ) {
					var cartesian = viewer.scene.pickPosition( evt.position );
					Prompt("请输入名称:  ", function(){
						var name = $.trim($("#promptInput").val());
						if( Cesium.defined( cartesian ) ) 
						{
							var canvas_image = new Image();
							canvas_image.src = $("#label_" + label_id ).attr("src");
							canvas_image.onload = function(){
								billboards.add({
									position : cartesian,
									image : drawCanvas( canvas_image, name ),
									verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
									horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
									disableDepthTestDistance: Number.POSITIVE_INFINITY,
									pixelOffset: new Cesium.Cartesian2( -10, 0 ),
								});
							};
							var labelObject = new Array( name, cartesian.x, cartesian.y, cartesian.z, "", GetURLPara(window.location.href,"id"), label_id );
							labelArray.push( labelObject );
						}
					});	
					if ( handler )
						handler.removeInputAction( Cesium.ScreenSpaceEventType.LEFT_CLICK );
				}
			}
		}, Cesium.ScreenSpaceEventType.LEFT_CLICK );
	});	
	$("#label_" + label_id).dblclick(function(){
		if ( handler )
			handler.removeInputAction( Cesium.ScreenSpaceEventType.LEFT_CLICK );
		Confirm("确定要删除该图标库的图标吗？", function(){		
			$.get( delete_labelbase_url, { 'id' : label_id } ,	function( data ){
							if( data.status == 'success' )
								$('#modelTools').load( modeltool_label_url );
							else
								Alert("删除失败，请检查网络！");
			});
		});
	});
}
$(function(){
	$('#labelbase_file').on('change', function(){
		var imageObj = document.getElementById('labelbase_file').files[0];
		var formData = new FormData();
		formData.append( 'image', imageObj );
		//$.ajaxSetup({ data: { csrfmiddlewaretoken : csrf_token }});
		$.ajax({
			type: 'POST',
			url: addlabel_labelupload_url,
			headers: {"X-CSRFToken":  csrf_token },
			dataType: 'JSON',
			data: formData,
			contentType: false,
			processData: false,
			success: function ( data ) {
				if( "success" == data.status ) 
				{
					//Alert("图标上传成功！");
					$('#modelTools').load( modeltool_label_url );
				}
				else
					Alert("图标上传失败，请检查网络！");
			},	
		});
	});
	
	$('#labelbase_add').click( function(){
		$('#labelbase_file').click();
	});
	
	$('#label_save').click( function(){
		if ( 0 !== labelArray.length )
		{
			$.ajaxSetup( {data: { csrfmiddlewaretoken : csrf_token } } );
			$.ajax({
				type: 'POST',
				url: label_upload_url,
				traditional:true,
				dataType: 'JSON',
				data: { labelArray: labelArray },
				success: function(data) {
					if ( data.status == 'success' ) {
						labelArray = [];
						label_bill_save = [];
						for (var i = 0; i < billboards.length; i++)
						{
							label_bill_save.push( i );
						}
						Alert("保存成功！");
					}
					else {
						Alert("保存失败，请检查网络！");
					}
				},
			});
		}		
	});
	
	$('#label_delete_unsave').click( function(){
		labelArray = [];
		for (var i = billboards.length - 1; i >= 0; i-- )
		{
			if( -1 === label_bill_save.indexOf( i ) )
				billboards.remove( billboards.get( i ) );
		}
		//$("#showLabel").load( showlabel_url + window.location.search );
	});
	$('#label_delete_save').click( function(){
		if( modelshow_bill_save.length || label_bill_save.length )
		{
			Confirm("确定要删除全部已保存的图标吗？", function(){
				$.get( delete_savelabel_url + window.location.search, function( data, status ){
						if( data.status == 'success' )
							Alert("删除成功！");
						else
							Alert("删除失败，请检查网络！");
				});	
				modelshow_bill_save.removeAll();
				for (var i = billboards.length - 1; i >= 0; i-- )
				{
					if( -1 !== label_bill_save.indexOf( i ) )
						billboards.remove( billboards.get( i ) );
				}
				label_bill_save = [];
			});
		}
	});
});