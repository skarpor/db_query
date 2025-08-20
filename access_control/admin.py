from django.contrib import admin
from .models import AccessControlRule
from django import forms
import json


class AccessControlRuleForm(forms.ModelForm):
    class Meta:
        model = AccessControlRule
        fields = '__all__'
        widgets = {
            'description': forms.Textarea(attrs={'rows': 3}),
            'custom_response': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': '{"message": "自定义消息", "code": 403}'
            }),
        }

    def clean_custom_response(self):
        data = self.cleaned_data['custom_response']
        if data:
            try:
                json.loads(data)
            except json.JSONDecodeError:
                raise forms.ValidationError("请输入有效的JSON格式")
        return data


@admin.register(AccessControlRule)
class AccessControlRuleAdmin(admin.ModelAdmin):
    form = AccessControlRuleForm
    list_display = [
        'name', 'url_pattern', 'match_type', 'methods', 'is_active',
        'require_login', 'priority', 'is_valid_now'
    ]
    list_filter = ['is_active', 'require_login', 'methods', 'match_type', 'valid_from', 'valid_until']
    filter_horizontal = ['allowed_users', 'allowed_groups']
    fieldsets = (
        ('基本信息', {
            'fields': ('name', 'description', 'priority', 'is_active')
        }),
        ('URL匹配', {
            'fields': ('url_pattern', 'match_type', 'methods')
        }),
        ('访问控制', {
            'fields': ('require_login', 'allowed_users', 'allowed_groups')
        }),
        ('时间控制', {
            'fields': ('valid_from', 'valid_until')
        }),
        ('自定义响应', {
            'fields': ('custom_response',),
            'classes': ('collapse',)
        }),
    )

    def is_valid_now(self, obj):
        return obj.is_valid_now()

    is_valid_now.boolean = True
    is_valid_now.short_description = '当前有效'