from django.contrib import admin
from .models import DatabaseConnection, SQLParameter, QueryInstance, ExecutionResult


from django_celery_beat.models import PeriodicTask, CrontabSchedule
from django import forms
from django.urls import reverse, path
from django.utils.html import format_html
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import get_object_or_404
import json
import time
import psycopg2
import mysql.connector
import sqlite3
import subprocess
import sys
from io import StringIO
from import_export.admin import ImportExportModelAdmin
import oracledb

# class NotificationConfigInline(admin.TabularInline):
#     model = NotificationConfig
#     extra = 1
#     fields = ('notification_type', 'recipient', 'trigger_on_success', 'trigger_on_failure')

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
