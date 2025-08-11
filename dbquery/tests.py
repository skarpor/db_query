from django_celery_beat.models import PeriodicTask

# 获取所有 PeriodicTask
tasks = PeriodicTask.objects.all()
for task in tasks:
    print(f"ID: {task.id}, Name: {task.name}, Enabled: {task.enabled}")
    print(f"Task: {task.task}, Args: {task.args}, Schedule: {task.schedule}")
    print("------")

# 查询特定任务（如 name="ddd"）
task = PeriodicTask.objects.get(name="ddd")
print(f"Task: {task.task}, Args: {task.args}, Enabled: {task.enabled}")
print(f"Schedule: {task.schedule}")  # 检查调度方式
