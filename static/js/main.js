function management( item_id, show_url, item_canSee ){
	var IsSeen = item_canSee;
	$('#'+item_id+'_a').attr("href", show_url+"&path=True");
	$('#'+item_id+'_a').attr("target", "_blank");
	if (IsSeen)
	{
		$('#'+item_id+'_see img').attr("src", "/static/icon/see.svg");
	}
	else
	{
		$('#'+item_id+'_see img').attr("src", "/static/icon/notsee.svg");
	}
	$('#'+item_id+'_see').click( function() {
		IsSeen = 1 - IsSeen;
		if ( IsSeen )
		{
			$('#'+item_id+'_see img').attr("src", "/static/icon/see.svg");
		}
		else
		{
			$('#'+item_id+'_see img').attr("src", "/static/icon/notsee.svg");
		}
		$.get( canSee_url, {'id' : parseInt(item_id), 'isSeen' : IsSeen });
		return false;
	});
	$('#'+item_id+'_share').click( function() {
		if ( IsSeen )
		{
			$('#model_url').val( window.location.host + show_url );
			$('#share_model').modal('show');
			$('#copy_button').click( function() {
				document.getElementById('model_url').select();
				document.execCommand('Copy');
				$('#share_model').modal('hide');
			});
		}
		else
		{
			$('#cannot_share_model').modal('show');
		}
		return false;
	});
	$('#'+item_id+'_delete').click( function() {
		$.get( delete_url, {'id' : parseInt( item_id ) }, function( result ) {
			window.location.reload();
		});
		return false;
	});
};