import json
import sqlite3
import time
from urllib.parse import urlencode

import mysql.connector
import oracledb
import psycopg2
from django import forms
from django.contrib import admin, messages
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.urls import reverse, path
from django.utils import timezone
from django.utils.html import format_html
from django_celery_beat.models import PeriodicTask
from import_export.admin import ImportExportModelAdmin

from .models import DatabaseConnection, SQLParameter, QueryInstance, ExecutionResult, ExecutionLog

from .models import Script
# class NotificationConfigInline(admin.TabularInline):
#     model = NotificationConfig
#     extra = 1
#     fields = ('notification_type', 'recipient', 'trigger_on_success', 'trigger_on_failure')
class ScriptForm(forms.ModelForm):
    class Meta:
        model = Script
        fields = '__all__'
        widgets = {
            'code': forms.Textarea(attrs={'rows': 20, 'cols': 80}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance')

        # 根据状态和用户权限设置字段只读
        if instance:
            if instance.status != 'draft' and not self.current_user.has_perm('script.change_any_script'):
                # 非草稿状态且无特殊权限时，所有字段只读
                for field in self.fields:
                    self.fields[field].widget.attrs['readonly'] = True
                    self.fields[field].widget.attrs['disabled'] = True
            elif instance.status == 'submitted' and self.current_user.has_perm('script.review_script'):
                # 审核者可以编辑审核备注
                self.fields['review_notes'].widget.attrs['readonly'] = False
                self.fields['review_notes'].widget.attrs['disabled'] = False

    def clean(self):
        cleaned_data = super().clean()
        instance = self.instance

        if instance and instance.pk and instance.status != 'draft' and not self.current_user.has_perm(
                'script.change_any_script'):
            # 安全地检查每个字段
            for field in ['title', 'code']:
                if field in cleaned_data and cleaned_data[field] != getattr(instance, field):
                    raise forms.ValidationError("已提交的脚本不可修改内容")

        return cleaned_data


@admin.register(Script)
class ScriptAdmin(admin.ModelAdmin):
    form = ScriptForm

    list_display = (
        'title',
        'status_badge',
        'creator',
        'created_at',
        'reviewer',
        'action_links'
    )
    list_filter = ('status', 'creator', 'reviewer')
    search_fields = ('title', 'code', 'review_notes')
    actions = ['submit_for_approval', 'approve_scripts', 'reject_scripts']
    readonly_fields = ('created_at', 'approved_at', 'creator', 'reviewer', 'status')
    fieldsets = (
        (None, {
            'fields': ('title', 'code')
        }),
        ('状态信息', {
            'fields': (
                'status',
                'creator',
                'created_at',
                'reviewer',
                'approved_at',
                'review_notes'
            ),
            'classes': ('collapse',)
        }),
    )

    def get_form(self, request, obj=None, **kwargs):
        # 将当前用户传递给表单
        form = super().get_form(request, obj, **kwargs)
        form.current_user = request.user
        return form

    def save_model(self, request, obj, form, change):
        # 新创建时设置创建者
        if not change:
            obj.creator = request.user

        # 状态变更处理
        if 'status' in form.changed_data:
            if obj.status == 'approved':
                obj.approved_at = timezone.now()
                obj.reviewer = request.user

        super().save_model(request, obj, form, change)

    def get_readonly_fields(self, request, obj=None):
        # 动态设置只读字段
        if obj and obj.status != 'draft':
            return [f.name for f in self.model._meta.fields if f.name != 'review_notes']
        return super().get_readonly_fields(request, obj)

    def status_badge(self, obj):
        status_colors = {
            'draft': 'blue',
            'submitted': 'orange',
            'approved': 'green',
            'rejected': 'red'
        }
        return format_html(
            '<span style="background:{}; color:white; padding:3px 8px; border-radius:10px">{}</span>',
            status_colors.get(obj.status, 'gray'),
            obj.get_status_display()
        )

    status_badge.short_description = '状态'
    status_badge.admin_order_field = 'status'

    def action_links(self, obj):
        links = []
        # request = self.request  # 获取当前请求对象

        # 提交审批按钮
        if obj.status == 'draft':
            links.append(
                '<a href="{}" class="button" style="background-color: #4CAF50; color: white; padding: 5px 10px; text-decoration: none; border-radius: 4px; margin-right: 5px;">提交审批</a>'.format(
                    reverse('admin:submit_script', args=[obj.pk])
                )
            )

        # 审批按钮（只有审批者可见）
        if obj.status == "submitted":# and self.request.has_perm('script.review_script'):
            links.append(
                '<a href="{}" class="button" style="background-color: #2196F3; color: white; padding: 5px 10px; text-decoration: none; border-radius: 4px; margin-right: 5px;">通过</a>'.format(
                    reverse('admin:approve_script', args=[obj.pk])
                )
            )
            links.append(
                '<a href="{}" class="button" style="background-color: #f44336; color: white; padding: 5px 10px; text-decoration: none; border-radius: 4px;">拒绝</a>'.format(
                    reverse('admin:reject_script', args=[obj.pk])
                )
            )

        # 测试执行按钮
        if obj.status == 'approved':
            links.append(
                '<a href="{}" class="button" style="background-color: #FF9800; color: white; padding: 5px 10px; text-decoration: none; border-radius: 4px; margin-right: 5px;">测试执行</a>'.format(
                    reverse('admin:test_execute_script', args=[obj.pk])
                )
            )

            # 创建定时任务按钮
            links.append(
                '<a href="{}" class="button" style="background-color: #9C27B0; color: white; padding: 5px 10px; text-decoration: none; border-radius: 4px;">定时任务</a>'.format(
                    reverse('admin:create_scheduled_task', args=[obj.pk])
                )
            )

        return format_html(' '.join(links))

    action_links.short_description = '操作'

    # 自定义操作：提交审批
    def submit_for_approval(self, request, queryset):
        # 只能提交草稿状态的脚本
        valid_scripts = queryset.filter(status='draft')
        count = valid_scripts.update(status='submitted')

        self.message_user(
            request,
            f"成功提交 {count} 个脚本等待审批",
            messages.SUCCESS
        )

    submit_for_approval.short_description = "提交选中的脚本进行审批"

    # 自定义操作：批准脚本
    def approve_scripts(self, request, queryset):
        # 只能批准待审批状态的脚本
        valid_scripts = queryset.filter(status='submitted')
        count = valid_scripts.update(
            status='approved',
            reviewer=request.user,
            approved_at=timezone.now()
        )

        self.message_user(
            request,
            f"成功批准 {count} 个脚本",
            messages.SUCCESS
        )

    approve_scripts.short_description = "批准选中的脚本"

    # 自定义操作：拒绝脚本
    def reject_scripts(self, request, queryset):
        # 只能拒绝待审批状态的脚本
        valid_scripts = queryset.filter(status='submitted')
        count = valid_scripts.update(
            status='rejected',
            reviewer=request.user
        )

        self.message_user(
            request,
            f"已拒绝 {count} 个脚本",
            messages.WARNING
        )

    reject_scripts.short_description = "拒绝选中的脚本"

    # 添加自定义视图的URL
    def get_urls(self):
        from django.urls import path
        urls = super().get_urls()

        custom_urls = [
            path(
                '<path:object_id>/submit/',
                self.admin_site.admin_view(self.submit_view),
                name='submit_script'
            ),
            path(
                '<path:object_id>/approve/',
                self.admin_site.admin_view(self.approve_view),
                name='approve_script'
            ),
            path(
                '<path:object_id>/reject/',
                self.admin_site.admin_view(self.reject_view),
                name='reject_script'
            ),
            path(
                '<path:object_id>/test-execute/',
                self.admin_site.admin_view(self.test_execute_view),
                name='test_execute_script'
            ),
            path(
                '<path:object_id>/create-task/',
                self.admin_site.admin_view(self.create_task_view),
                name='create_scheduled_task'
            ),
        ]

        return custom_urls + urls

    # 处理通过审批视图
    def approve_view(self, request, object_id):
        script = self.get_object(request, object_id)

        # 权限检查
        if not request.user.has_perm('script.review_script'):
            self.message_user(
                request,
                "您没有审批脚本的权限",
                messages.ERROR
            )
            return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

        # 状态检查
        if script.status != 'submitted':
            self.message_user(
                request,
                "只有待审批状态的脚本可以通过审批",
                messages.ERROR
            )
            return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

        # 更新状态
        script.status = 'approved'
        script.reviewer = request.user
        script.approved_at = timezone.now()
        script.save()

        self.message_user(
            request,
            "脚本已通过审批，现在可以执行",
            messages.SUCCESS
        )
        return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

    # 处理拒绝审批视图
    def reject_view(self, request, object_id):
        script = self.get_object(request, object_id)

        # 权限检查
        if not request.user.has_perm('script.review_script'):
            self.message_user(
                request,
                "您没有审批脚本的权限",
                messages.ERROR
            )
            return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

        # 状态检查
        if script.status != 'submitted':
            self.message_user(
                request,
                "只有待审批状态的脚本可以拒绝",
                messages.ERROR
            )
            return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

        # 更新状态
        script.status = 'rejected'
        script.reviewer = request.user
        script.save()

        self.message_user(
            request,
            "脚本已被拒绝",
            messages.WARNING
        )
        return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

    # 处理提交审批视图
    def submit_view(self, request, object_id):
        script = self.get_object(request, object_id)

        if script.status != 'draft':
            self.message_user(
                request,
                "只有草稿状态的脚本可以提交",
                messages.ERROR
            )
            return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

        script.status = 'submitted'
        script.save()

        self.message_user(
            request,
            "脚本已提交等待审批",
            messages.SUCCESS
        )
        return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

    # 处理测试执行视图
    def test_execute_view(self, request, object_id):
        from .tasks import execute_python_code

        script = self.get_object(request, object_id)

        if script.status != 'approved':
            self.message_user(
                request,
                "只有已批准的脚本可以执行",
                messages.ERROR
            )
            return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

        # 执行脚本
        result = execute_python_code(script.code)
        print(result)
        # 保存执行日志
        ExecutionLog.objects.create(
            script=script,
            output=result['output'],
            error=result['error'],
            success=result['success'],
            triggered_by=request.user
        )

        # 显示结果消息
        if result['success']:
            msg = "脚本执行成功！查看执行日志获取详细信息"
            level = messages.SUCCESS
        else:
            msg = f"脚本执行失败：{result['error'][:100]}"
            level = messages.ERROR

        self.message_user(request, msg, level)
        return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

    # 处理创建定时任务视图
    def create_task_view(self, request, object_id):
        script = self.get_object(request, object_id)

        if script.status != 'approved':
            self.message_user(
                request,
                "只有已批准的脚本可以创建定时任务",
                messages.ERROR
            )
            return HttpResponseRedirect(reverse('admin:dbquery_script_change', args=[object_id]))

        # 重定向到Celery Beat的创建页面
        create_url = reverse('admin:django_celery_beat_periodictask_add')

        # 预填充任务信息
        params = {
            'name': f'Scheduled: {script.title}',
            'task': 'script.tasks.execute_script_task',
            'args': f'[{script.id}]',
            'enabled': 'on'
        }

        return HttpResponseRedirect(f"{create_url}?{urlencode(params)}")


@admin.register(ExecutionLog)
class ExecutionLogAdmin(admin.ModelAdmin):
    list_display = ('script', 'executed_at', 'status_badge', 'triggered_by')
    list_filter = ('success', 'executed_at', 'triggered_by')
    search_fields = ('script__title', 'output', 'error')
    readonly_fields = ('script', 'executed_at', 'output', 'error', 'success', 'triggered_by')
    ordering = ('-executed_at',)

    def status_badge(self, obj):
        if obj.success:
            color = 'green'
            text = '成功'
        else:
            color = 'red'
            text = '失败'
        return format_html(
            '<span style="background:{}; color:white; padding:3px 8px; border-radius:10px">{}</span>',
            color, text
        )

    status_badge.short_description = '状态'

    def has_add_permission(self, request):
        # 禁止手动添加执行日志
        return False


# 集成Celery Beat定时任务
# admin.site.unregister(PeriodicTask)  # 取消默认注册


# @admin.register(PeriodicTask)
# class PeriodicTaskAdmin(admin.ModelAdmin):
#     list_display = ('name', 'task', 'enabled', 'last_run_at')
#     list_filter = ('enabled', 'task')
#     search_fields = ('name', 'task', 'args')
#
#     def get_queryset(self, request):
#         # 只显示与脚本相关的任务
#         qs = super().get_queryset(request)
#         return qs.filter(task='script.tasks.execute_script_task')


@admin.register(DatabaseConnection)
class DatabaseConnectionAdmin(ImportExportModelAdmin): # 使用导入导出的模型
    list_display = ('name', 'db_type', 'host', 'port', 'username', 'database', 'timeout', 'created_at', 'test_connection_link')
    search_fields = ('name', 'host', 'database')
    list_filter = ('db_type', 'created_at')
    # 导入导出配置
    import_export_fields = (
        'name', 'db_type', 'host', 'port', 'username', 'password', 'database', 'timeout'
    )
    export_fields = (
        'name', 'db_type', 'host', 'port', 'username', 'database', 'timeout', 'created_at'
    )
    def test_connection_link(self, obj):
        return format_html('<a href="{}" class="button">测试连接</a>',
                          reverse('admin:test_database_connection', args=[obj.id]))
    test_connection_link.short_description = '连接测试'
    test_connection_link.allow_tags = True


@admin.register(SQLParameter)
class SQLParameterAdmin(ImportExportModelAdmin):
    list_display = ('name', 'description', 'created_at', 'test_parameter_link')
    search_fields = ('name', 'description')
    list_filter = ('created_at',)
    fieldsets = (
        (None, {
            'fields': ('name', 'description', 'python_code')
        }),
        ('示例代码', {
            'fields': (),
            'description': '''<div style="background-color:#f0f0f0; padding:10px;"><pre># 获取当前日期
datetime.datetime.now().strftime("%Y-%m-%d")</pre></div>'''
        })
    )
    
    def test_parameter_link(self, obj):
        return format_html('<a href="{}" class="button">测试执行</a>',
                          reverse('admin:test_sql_parameter', args=[obj.id]))
    test_parameter_link.short_description = '参数测试'
    test_parameter_link.allow_tags = True


class QueryInstanceForm(forms.ModelForm):
    class Meta:
        model = QueryInstance
        fields = '__all__'
        widgets = {
            'sql_template': forms.Textarea(attrs={'rows': 10}),
        }

    def clean_sql_template(self):
        sql_template = self.cleaned_data.get('sql_template')
        # 这里可以添加SQL模板验证逻辑
        return sql_template


@admin.register(QueryInstance)
class QueryInstanceAdmin(ImportExportModelAdmin):
    # 设置每页显示数量
    list_per_page = 10
    # inlines = [NotificationConfigInline]
    form = QueryInstanceForm
    list_display = ('name', 'connection', 'created_at', 'periodic_task_link', 'test_query_link')
    search_fields = ('name', 'sql_template')
    list_filter = ('connection', 'created_at')
    filter_horizontal = ('parameters',)
    fieldsets = (
        (None, {
            'fields': ('name', 'connection', 'sql_template', 'parameters')
        }),
        ('定时任务配置', {
            'fields': ('periodic_task',),
            'description': '如需设置定时任务，请先保存查询实例，然后点击右侧链接创建定时任务。'
        })
    )

    def periodic_task_link(self, obj):
        if obj.periodic_task:
            return format_html('<a href="{}">{}</a>',
                              reverse('admin:django_celery_beat_periodictask_change', args=[obj.periodic_task.id]),
                              obj.periodic_task.name)
        else:
            return format_html('<a href="{}">创建定时任务</a>',
                              reverse('admin:django_celery_beat_periodictask_add') + f'?name={obj.name}&task=dbquery.tasks.execute_query&args=%5B{obj.id}%5D')
    periodic_task_link.short_description = '定时任务'
    
    def test_query_link(self, obj):
        return format_html('<a href="{}" class="button">测试执行</a>',
                          reverse('admin:test_query_instance', args=[obj.id]))
    test_query_link.short_description = '查询测试'
    test_query_link.allow_tags = True


@admin.register(ExecutionResult)
class ExecutionResultAdmin(ImportExportModelAdmin):
    list_display = ('query_instance', 'status', 'execution_time', 'created_at', 'view_result_link', 'export_result_link')
    search_fields = ('query_instance__name', 'error_message')
    list_filter = ('status', 'created_at', 'query_instance')
    readonly_fields = ('query_instance', 'status', 'result_data', 'execution_time', 'error_message', 'created_at', 'rendered_sql')

    # 设置每页显示数量
    list_per_page = 10


    def view_result_link(self, obj):
        if obj.status == 'success' and obj.result_data:
            return format_html('<a href="/" target="_blank">查看结果</a>', json.dumps(obj.result_data)) 

        return '无结果'
    view_result_link.short_description = '查看结果'

    def export_result_link(self, obj):
        if obj.status == 'success' and obj.result_data:
            return format_html('<a href="{}">导出结果</a>', reverse('export_result', args=[obj.id]))
        return '无结果'
    export_result_link.short_description = '导出结果'

    class Media:
        js = ('dbquery/js/result_viewer.js',)


# 自定义Celery Beat的管理界面
class CustomPeriodicTaskAdmin(ImportExportModelAdmin):
    list_display = ('name', 'task', 'crontab', 'enabled', 'last_run_at')
    search_fields = ('name', 'task')
    list_filter = ('enabled', 'task')

# 尝试取消默认注册并使用自定义的，如果已经注册的话
if admin.site.is_registered(PeriodicTask):
    admin.site.unregister(PeriodicTask)
    admin.site.register(PeriodicTask, CustomPeriodicTaskAdmin)

# admin.site.register(NotificationConfig)

# 自定义视图函数 - 测试数据库连接
def test_database_connection(request, connection_id):
    connection = get_object_or_404(DatabaseConnection, id=connection_id)
    start_time = time.time()
    try:
        if connection.db_type == 'postgresql':
            conn = psycopg2.connect(
                host=connection.host,
                port=connection.port,
                user=connection.username,
                password=connection.password,
                dbname=connection.database,
                connect_timeout=connection.timeout
            )
            conn.close()
        elif connection.db_type == 'mysql':
            conn = mysql.connector.connect(
                host=connection.host,
                port=connection.port,
                user=connection.username,
                password=connection.password,
                database=connection.database,
                connection_timeout=connection.timeout
            )
            conn.close()
        elif connection.db_type == 'sqlite':
            conn = sqlite3.connect(connection.database)
            conn.close()
        # oracle
        elif connection.db_type == 'oracle':
            dsn = oracledb.makedsn(connection.host, connection.port, service_name=connection.database)
            conn = oracledb.connect(user=connection.username, password=connection.password, dsn=dsn, timeout=connection.timeout)
            conn.close()

        else:
            raise Exception(f"不支持的数据库类型: {connection.db_type}")
        execution_time = time.time() - start_time
        admin.ModelAdmin.message_user(
            DatabaseConnectionAdmin, request,
            f"数据库连接测试成功! 耗时: {execution_time:.4f}秒",
            level='success'
        )
    except Exception as e:
        admin.ModelAdmin.message_user(
            DatabaseConnectionAdmin, request,
            f"数据库连接测试失败: {str(e)}",
            level='error'
        )
    return HttpResponseRedirect(reverse('admin:dbquery_databaseconnection_changelist'))

# 自定义视图函数 - 测试SQL参数
def test_sql_parameter(request, parameter_id):
    parameter = get_object_or_404(SQLParameter, id=parameter_id)
    try:
        # 确保常用模块可用
        import datetime
        import time
        
        # 执行参数代码并获取结果
        result = eval(parameter.python_code)
        
        admin.ModelAdmin.message_user(
            SQLParameterAdmin, request,
            f"参数测试执行成功! 结果: {result}",
            level='success'
        )
    except Exception as e:
        admin.ModelAdmin.message_user(
            SQLParameterAdmin, request,
            f"参数测试执行失败: {str(e)}",
            level='error'
        )
    return HttpResponseRedirect(reverse('admin:dbquery_sqlparameter_changelist'))

# 自定义视图函数 - 测试查询实例
def test_query_instance(request, instance_id):
    instance = get_object_or_404(QueryInstance, id=instance_id)
    try:
        # 这里可以调用查询执行的任务
        from .tasks import execute_query
        result = execute_query(instance_id)
        # 解析执行结果
        if result and 'status' in result and 'result_data' in result:
            status = result['status']
            result_data = result['result_data']
            execution_time = result['execution_time']
            error_message = result.get('error_message', '')
            # 保存执行结果
            ExecutionResult.objects.create(
                query_instance=instance,
                status=status,
                result_data=result_data if status == 'success' else None,
                execution_time=execution_time,
                error_message=error_message
            )

        admin.ModelAdmin.message_user(
            QueryInstanceAdmin, request,
            f"查询测试执行成功! 结果已保存到执行结果表.",
            level='success'
        )
    except Exception as e:

        admin.ModelAdmin.message_user(
            QueryInstanceAdmin, request,
            f"查询测试执行失败: {str(e)}",
            level='error'
        )
    return HttpResponseRedirect(reverse('admin:dbquery_queryinstance_changelist'))

# 保存原始的get_urls方法
original_get_urls = admin.site.get_urls

# 添加自定义URL
def get_admin_urls():
    # 调用原始的get_urls方法
    urls = original_get_urls()
    custom_urls = [
        path('test-database-connection/<int:connection_id>/', test_database_connection, name='test_database_connection'),
        path('test-sql-parameter/<int:parameter_id>/', test_sql_parameter, name='test_sql_parameter'),
        path('test-query-instance/<int:instance_id>/', test_query_instance, name='test_query_instance'),
    ]
    return custom_urls + urls

# 替换默认的admin urls
admin.site.get_urls = get_admin_urls
