from django import forms

class ImageLabelForm( forms.Form ):
	#name = forms.CharField( label = '名称', max_length = 128 )
	source = forms.ImageField( label = '图片', max_length  = 50 )
	