import sys
import traceback
from io import StringIO

# User
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied
from django.db import models
from django_celery_beat.models import PeriodicTask


class DatabaseConnection(models.Model):
    DB_TYPES = (
        ('mysql', 'MySQL'),
        ('oracle', 'Oracle'),
        ('postgresql', 'PostgreSQL'),
    )
    name = models.CharField(max_length=100, unique=True, verbose_name='连接名称')
    db_type = models.CharField(max_length=20, choices=DB_TYPES, verbose_name='数据库类型')
    host = models.CharField(max_length=255, verbose_name='主机地址')
    port = models.IntegerField(verbose_name='端口')
    username = models.CharField(max_length=100, verbose_name='用户名')
    password = models.CharField(max_length=255, verbose_name='密码')
    database = models.CharField(max_length=100, verbose_name='数据库名称')
    timeout = models.IntegerField(default=30, verbose_name='查询超时时间(秒)')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    def __str__(self):
        return self.name

    class Meta:
        verbose_name = '数据库连接'
        verbose_name_plural = '数据库连接'


class SQLParameter(models.Model):
    name = models.CharField(max_length=100, verbose_name='参数名称')
    description = models.TextField(blank=True, null=True, verbose_name='参数描述')
    python_code = models.TextField(verbose_name='Python代码')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')

    def __str__(self):
        return self.name

    def evaluate(self):
        try:
            # 安全执行Python代码，导入常用模块
            import datetime
            import time
            import math
            import json
            import re
            global_vars = {
                'datetime': datetime,
                'time': time,
                'math': math,
                'json': json,
                're': re
            }
            local_vars = {}
            # 使用eval执行表达式并直接获取返回值
            result = eval(self.python_code, global_vars, local_vars)
            return result
            # 否则返回第一个变量值
            return list(local_vars.values())[0] if local_vars else None
        except Exception as e:
            error_msg = f"Error: {str(e)}"
            logger.error(f"参数计算错误: {error_msg}")
            return error_msg

    class Meta:
        verbose_name = 'SQL参数'
        verbose_name_plural = 'SQL参数'


class QueryInstance(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name='查询名称')
    connection = models.ForeignKey(DatabaseConnection, on_delete=models.CASCADE, verbose_name='数据库连接')
    sql_template = models.TextField(verbose_name='SQL模板')
    parameters = models.ManyToManyField(SQLParameter, blank=True, related_name='query_instances', verbose_name='参数')
    # result_table = models.CharField(max_length=100, verbose_name='结果表名')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='创建时间')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='更新时间')
    periodic_task = models.OneToOneField(PeriodicTask, on_delete=models.SET_NULL, null=True, blank=True, verbose_name='定时任务')

    def __str__(self):
        return self.name

    def get_rendered_sql(self):
        import logging
        logger = logging.getLogger(__name__)
        sql = self.sql_template
        for param in self.parameters.all():
            value = param.evaluate()
            logger.info(f"参数 {param.name} 解析值: {value}, 类型: {type(value)}")
            # 仅替换参数，不处理引号
            sql = sql.replace(f'{{{{ {param.name} }}}}', str(value))
            sql = sql.replace(f'{{{{{param.name}}}}}', str(value))
        logger.info(f"渲染后的SQL: {sql}")
        return sql

    class Meta:
        verbose_name = '查询实例'
        verbose_name_plural = '查询实例'


class ExecutionResult(models.Model):
    STATUS_CHOICES = (
        ('success', '成功'),
        ('failed', '失败'),
    )
    query_instance = models.ForeignKey(QueryInstance, on_delete=models.CASCADE, related_name='results', verbose_name='查询实例')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, verbose_name='执行状态')
    result_data = models.JSONField(blank=True, null=True, verbose_name='结果数据')
    rendered_sql = models.TextField(blank=True, null=True, verbose_name='解析后的SQL')
    execution_time = models.FloatField(verbose_name='执行时间(秒)')
    error_message = models.TextField(blank=True, null=True, verbose_name='错误信息')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='执行时间')

    def __str__(self):
        return f"{self.query_instance.name} - {self.status} - {self.created_at}"

    class Meta:
        verbose_name = '执行结果'
        verbose_name_plural = '执行结果'
        ordering = ['-created_at']


# class NotificationConfig(models.Model):
#     NOTIFICATION_TYPES = (
#         ('email', '电子邮件'),
#         ('sms', '短信'),
#         ('webhook', 'Webhook'),
#     )

#     query_instance = models.ForeignKey(QueryInstance, on_delete=models.CASCADE, related_name='notifications')
#     notification_type = models.CharField(max_length=20, choices=NOTIFICATION_TYPES)
#     recipient = models.CharField(max_length=255, help_text="接收人信息，如邮箱、手机号或Webhook URL")
#     trigger_on_success = models.BooleanField(default=True)
#     trigger_on_failure = models.BooleanField(default=False)
#     last_sent = models.DateTimeField(null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)

#     def __str__(self):
#         return f"{self.query_instance} - {self.get_notification_type_display()}"
#     class Meta:
#         verbose_name_plural = "通知管理"
#         verbose_name = "通知配置"
class Script(models.Model):
    STATUS_CHOICES = (
        ('draft', '草稿'),
        ('pending', '待审批'),
        ('submitted', '待审批'),
        ('approved', '已批准'),
        ('rejected', '已拒绝')
    )

    title = models.CharField(max_length=100,verbose_name="脚本名称")
    description = models.TextField(blank=True, null=True, verbose_name='描述信息')
    code = models.TextField(verbose_name='脚本内容')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    creator = models.ForeignKey(User, on_delete=models.CASCADE)
    reviewer = models.ForeignKey(User, null=True, blank=True, related_name='reviewed_scripts',on_delete=models.SET_NULL)
    review_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return f"{self.title}"

    class Meta:
        verbose_name_plural = "脚本管理"
        verbose_name = "脚本管理"

        permissions = [
            ("review_script", "可以审批脚本"),
            ("execute_script", "可以执行脚本"),
            ("change_any_script", "可以修改任何状态的脚本"),
            ("create_scheduled_task", "可以创建定时任务"),
        ]


class ExecutionLog(models.Model):
    script = models.ForeignKey(Script, on_delete=models.CASCADE)
    executed_at = models.DateTimeField(auto_now_add=True)
    output = models.TextField(null=True, blank=True,)
    success = models.BooleanField()
    error = models.TextField(blank=True,null=True)   # 错误输出
    triggered_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL)
    def __str__(self):
        return f"{self.script}"

    class Meta:
        verbose_name_plural = "脚本执行日志"
        verbose_name = "脚本执行日志"