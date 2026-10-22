$(function(){
	if ( !GetURLPara( window.location.search, 'path' ) )
		$('#label').css( 'display', 'none' );
	let chosen_num = -1;
	$('#label').click( function() {
		if( 4 !== chosen_num )
		{
			chosen_num = 4;
			$('#modelTools').empty();
			$('#modelTools').css('display', 'block');
			$('#modelTools').load( modeltool_label_url );
		}
		else
		{
			chosen_num = -1;
			$('#modelTools').css('display', 'none');
			$('#modelTools').empty();
		}
		removeAllEntity();
	});
	$('#measuring').click( function() {
		if( 0 !== chosen_num )
		{
			chosen_num = 0;
			$('#modelTools').empty();
			$('#modelTools').css('display', 'block');
			$('#modelTools').load( modeltool_measuring_url );
		}
		else
		{
			chosen_num = -1;
			$('#modelTools').css('display', 'none');
			$('#modelTools').empty();
		}
		removeAllEntity();
	});
	$('#viewing').click( function() {
		if( 1 !== chosen_num)
		{
			chosen_num = 1;
			$('#modelTools').empty();
			$('#modelTools').css('display', 'block');
			$('#modelTools').load( modeltool_viewing_url + window.location.search );
			//$('#viewer_cancel').click();
		}
		else
		{
			chosen_num = -1;
			$('#modelTools').css('display', 'none');
			//$('#viewer_cancel').click();
			$('#modelTools').empty();
		}
		removeAllEntity();
	});
	$('#analyze').click( function() {
	
		if( 2 !== chosen_num )
		{
			chosen_num = 2;
			$('#modelTools').empty();
			$('#modelTools').css('display', 'block');
			$('#modelTools').load( modeltool_analyzetool_url + window.location.search );
		}
		else
		{
			chosen_num = -1;
			$('#modelTools').css('display', 'none');
			$('#modelTools').empty();
		}
		removeAllEntity();
	});
	$('#others').click( function() {	
		if( 3 !== chosen_num )
		{
			chosen_num = 3;
			$('#modelTools').empty();
			$('#modelTools').css('display', 'block');
			$('#modelTools').load( modeltool_othertools_url + window.location.search );
		}
		else
		{
			chosen_num = -1;
			$('#modelTools').css('display', 'none');
			$('#modelTools').empty();
		}
		removeAllEntity();
	});
});