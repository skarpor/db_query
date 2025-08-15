from django.contrib import admin
from .models import Document


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'file_name',
        'is_visible',
        'is_editable',
        'version',
        'created_at',
        'created_by',  # 改为 IP 字段
        'updated_at',
        'updated_by'  # 改为 IP 字段
    )
    list_filter = ('is_visible', 'is_editable')
    search_fields = ('title', 'file_name')
    readonly_fields = ('version', 'created_at', 'updated_at', 'created_by', 'updated_by')  # 改为 IP 字段
    fieldsets = (
        (None, {
            'fields': ('title', 'file_name', 'content')
        }),
        ('状态设置', {
            'fields': ('is_visible', 'is_editable')
        }),
        ('元数据', {
            'fields': ('version', 'created_at', 'updated_at', 'created_by', 'updated_by'),  # 改为 IP 字段
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        # 获取客户端 IP
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')

        # 如果是新建文档，设置创建 IP
        if not change:
            obj.created_by = ip

        # 始终更新修改 IP
        obj.updated_by = ip

        super().save_model(request, obj, form, change)
