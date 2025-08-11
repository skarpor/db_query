#!/bin/bash

# 确保日志目录存在
mkdir -p /app/logs

# 数据库迁移
python manage.py makemigrations
python manage.py migrate

# 启动多进程并合并日志

# 启动Django应用并将日志输出到文件
python manage.py runserver 0.0.0.0:8000 > /app/logs/django.log 2>&1 &

# 启动Celery Worker并将日志输出到文件
celery -A dbq_project worker -l info > /app/logs/celery_worker.log 2>&1 &

# 启动Celery Beat并将日志输出到文件
celery -A dbq_project beat -l info > /app/logs/celery_beat.log 2>&1 &

# 合并所有日志并输出到前台
 tail -f /app/logs/*.log | tee /app/logs/combined.log