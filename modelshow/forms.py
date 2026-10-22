from django import forms

class AddItemsForm( forms.Form ):
	name = forms.CharField( label = '模型名称', max_length = 50 )
	image = forms.ImageField( label = '添加图片' )
	data = forms.FileField( label = '添加模型', max_length  = 50 )
	#builder = forms.CharField( label = '创建者', max_length = 50 )
	#isPublic = forms.BooleanField( label = '是否公开', required=False )