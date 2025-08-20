from django.db import migrations


def create_initial_rules(apps, schema_editor):
    AccessControlRule = apps.get_model('access_control', 'AccessControlRule')

    # 管理员界面规则
    admin_rule = AccessControlRule(
        name='Admin Access',
        url_pattern=r'^/admin/.*',
        methods='ALL',
        require_login=True,
        is_active=True,
        priority=1
    )
    admin_rule.save()

    # 静态文件规则（如果需要限制）
    static_rule = AccessControlRule(
        name='Static Files',
        url_pattern=r'^/static/.*',
        methods='ALL',
        require_login=False,  # 根据需求调整
        is_active=True,
        priority=5
    )
    static_rule.save()

    # 媒体文件规则（如果需要限制）
    media_rule = AccessControlRule(
        name='Media Files',
        url_pattern=r'^/media/.*',
        methods='ALL',
        require_login=False,  # 根据需求调整
        is_active=True,
        priority=5
    )
    media_rule.save()


class Migration(migrations.Migration):
    dependencies = [
        ('access_control', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(create_initial_rules),
    ]