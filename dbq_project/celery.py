import os
from celery import Celery
from django.conf import settings

# 设置默认的Django设置模块
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dbq_project.settings')

app = Celery('dbq_project')

# 使用Django的设置来配置Celery
app.config_from_object('django.conf:settings', namespace='CELERY')

# 从所有已安装的应用中加载任务模块
app.autodiscover_tasks(lambda: settings.INSTALLED_APPS)