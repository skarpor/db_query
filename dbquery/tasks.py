from celery import shared_task
from .models import QueryInstance, ExecutionResult
import time
import json
import logging
import pymysql
import cx_Oracle
from datetime import datetime
from django.core.mail import send_mail
from django.conf import settings
# from .notification import NotificationService
# 自定义JSON编码器，处理datetime对象
class DateTimeEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.strftime('%Y-%m-%d %H:%M:%S')
        return super().default(obj)

# 配置日志
logger = logging.getLogger(__name__)


@shared_task(bind=True, max_retries=3)  # 允许重试3次
def execute_query(self, query_instance_id):
    try:
        start_time = time.time()
        query_instance = QueryInstance.objects.get(id=query_instance_id)
        connection = query_instance.connection

        logger.info(f"开始执行查询: {query_instance.name} (ID: {query_instance_id})")

        # 渲染SQL
        sql = query_instance.get_rendered_sql()
        logger.info(f"渲染后的SQL: {sql}")

        # 连接数据库并执行查询
        result_data = None
        error_message = None
        status = 'success'

        try:
            if connection.db_type == 'mysql':
                conn = pymysql.connect(
                    host=connection.host,
                    port=connection.port,
                    user=connection.username,
                    password=connection.password,
                    database=connection.database,
                    connect_timeout=connection.timeout
                )
                with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                    cursor.execute(sql)
                    result_data = cursor.fetchall()
                conn.close()
            elif connection.db_type == 'oracle':
                dsn = cx_Oracle.makedsn(connection.host, connection.port, service_name=connection.database)
                conn = cx_Oracle.connect(user=connection.username, password=connection.password, dsn=dsn, timeout=connection.timeout)
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    columns = [col[0] for col in cursor.description]
                    result_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
                conn.close()
            # postgresql 数据库,使用 psycopg2 库
            elif connection.db_type == 'postgresql':
                import psycopg2
                from psycopg2.extras import RealDictCursor
            
                conn = psycopg2.connect(
                    host=connection.host,
                    port=connection.port,
                    user=connection.username,
                    password=connection.password,
                    dbname=connection.database,
                    connect_timeout=connection.timeout
                )
                with conn.cursor(cursor_factory=RealDictCursor) as cursor:  # 使用RealDictCursor直接返回字典
                    cursor.execute(sql)
                    result_data = cursor.fetchall()
                conn.close()
            elif connection.db_type == 'sqlserver':
                import pyodbc
                conn = pyodbc.connect(
                    f"DRIVER={{ODBC Driver 17 for SQL Server}};"
                    f"SERVER={connection.host},{connection.port};"
                    f"DATABASE={connection.database};"
                    f"UID={connection.username};"
                    f"PWD={connection.password};"
                    f"Connect Timeout={connection.timeout};"
                )
                with conn.cursor() as cursor:
                    cursor.execute(sql)
                    columns = [col[0] for col in cursor.description]
                    result_data = [dict(zip(columns, row)) for row in cursor.fetchall()]
                conn.close()

            else:
                raise ValueError(f"不支持的数据库类型: {connection.db_type}")

        except Exception as e:
            status = 'failed'
            error_message = str(e)
            logger.error(f"查询执行失败: {error_message}")
            
            # 计算执行时间
            execution_time = time.time() - start_time
            
            # 先保存失败结果
            ExecutionResult.objects.create(
                query_instance=query_instance,
                status=status,
                result_data=None,
                rendered_sql=sql,
                execution_time=execution_time,
                error_message=error_message
            )
            
            logger.info(f"查询执行完成: {query_instance.name}, 状态: {status}, 耗时: {execution_time:.2f}秒")
            
            # 再进行重试
            self.retry(exc=e, countdown=60 * (self.request.retries + 1))  # 指数退避重试

        # 计算执行时间
        execution_time = time.time() - start_time

        # 保存执行结果
        # 序列化结果数据，处理datetime对象
        serialized_data = json.dumps(result_data, cls=DateTimeEncoder) if status == 'success' else None
        
        ExecutionResult.objects.create(
            query_instance=query_instance,
            status=status,
            result_data=serialized_data,
            rendered_sql=sql,
            execution_time=execution_time,
            error_message=error_message
        )

        logger.info(f"查询执行完成: {query_instance.name}, 状态: {status}, 耗时: {execution_time:.2f}秒")

        # 发送邮件通知
        if settings.EMAIL_HOST_USER:
            subject = f"查询任务{query_instance.name}执行{status}"
            message = f"查询名称: {query_instance.name}\n状态: {status}\n耗时: {execution_time:.2f}秒\n"
            if status == 'failed':
                message += f"错误信息: {error_message}"
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [settings.DEFAULT_FROM_EMAIL],  # 发送给自己，实际应用中可以修改为目标邮箱
                fail_silently=True,
            )

        return {
            'status': status,
            'execution_time': execution_time,
            'result_count': len(result_data) if result_data else 0
        }

    except QueryInstance.DoesNotExist:
        logger.error(f"查询实例不存在: {query_instance_id}")
        return {'status': 'failed', 'error': '查询实例不存在'}
    except Exception as e:
        logger.error(f"任务执行异常: {str(e)}")
        return {'status': 'failed', 'error': str(e)}


@shared_task
def test_task():
    """测试任务"""
    logger.info("测试任务执行成功")
    return "测试任务执行成功"