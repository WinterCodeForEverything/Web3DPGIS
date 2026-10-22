function on_progress( evt ) {       //看这个函数之前先看upload函数。这个函数可以接收一个evt(event)对象(细节自行查询progress)，他有3个属性lengthComputable，loaded，total，第一个属性是个bool类型的，代表是否支持，第二个代表当前上传的大小，第三个为总的大小，由此便可以计算出实时上传的百分比
	if(evt.lengthComputable) {
		var percent = Math.round((evt.loaded) * 100 / evt.total);
		$('#process_bar').css("width", percent);
		$('#process_text').text( percent.toString() + '%');
	}
}
function upload() {
	if($('#id_name').val() != "" && $('#id_image').val() !== "" && $('#id_data').val() !== "" )
	{
		var xhr = new XMLHttpRequest();
		var files = $('#id_data').prop('files');   //取得文件数据，而.file对象只是文件信息
		var form2 = new FormData();   //FormData是HTML5为实现序列化表单而提供的类，更多细节可自行查询
		form2.append('id_data',files[0]);   //这里为序列化表单对象form添加一个元素，即file
		xhr.upload.addEventListener( 'progress', on_progress, false );     //xhr对象含有一个upload对象，它有一个progress事件，在文件上传过程中会被不断触发，我们为这个事件对应一个处理函数，每当事件触发就会调用这个函数，于是便可利用这个函数来修改当前进度，更多细节可自行查询
		xhr.open( 'POST',"",true );
		xhr.setRequestHeader('X-CSRFTOKEN','{{ request.COOKIES.csrftoken }}');   //此处为Django要求，可无视，或者换成相应后台所要求的CSRF防护，不是django用户请去掉
		xhr.send( form2 );   //发送表单
		xhr.onload = ( function (evt){
			//alert("上传完成，接下来模型会在后台解压，若不能马上显示模型，请稍候！");
			$('#notice_word').text("上传完成，接下来模型会在后台解压，若不能马上显示模型，请稍候！");
			$('#finish_notice').modal();
		});
		xhr.onerror = ( function (evt){
			//alert("上传失败，请检查网络！");
			$('#notice_word').text("上传失败，请检查网络！");
			$('#finish_notice').modal();
		});
	}
}