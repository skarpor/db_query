from django.db import models
from django.contrib.auth.models import User, Group
from django.core.validators import RegexValidator
import re


class AccessControlRule(models.Model):
    # 规则基本信息
    name = models.CharField(max_length=100, unique=True, verbose_name="规则名称")
    description = models.TextField(blank=True, verbose_name="规则描述")

    # URL 模式匹配
    url_pattern = models.CharField(
        max_length=200,
        verbose_name="URL模式",
        help_text="支持正则表达式，如 ^/api/.* 或精确路径 /api/users/"
    )
    # 添加匹配类型字段
    MATCH_TYPES = [
        ('regex', '正则表达式'),
        ('exact', '精确匹配'),
        ('startswith', '开头匹配'),
        ('endswith', '结尾匹配'),
        ('contains', '包含'),
    ]
    match_type = models.CharField(
        max_length=10,
        choices=MATCH_TYPES,
        default='regex',
        verbose_name="匹配类型"
    )

    def match_url(self, path):
        """根据匹配类型检查URL是否匹配规则"""
        if self.match_type == 'regex':
            pattern = re.compile(self.url_pattern)
            return pattern.match(path) is not None
        elif self.match_type == 'exact':
            return path == self.url_pattern
        elif self.match_type == 'startswith':
            return path.startswith(self.url_pattern)
        elif self.match_type == 'endswith':
            return path.endswith(self.url_pattern)
        elif self.match_type == 'contains':
            return self.url_pattern in path
        return False

    # HTTP 方法控制
    HTTP_METHODS = [
        ('GET', 'GET'),
        ('POST', 'POST'),
        ('PUT', 'PUT'),
        ('DELETE', 'DELETE'),
        ('PATCH', 'PATCH'),
        ('HEAD', 'HEAD'),
        ('OPTIONS', 'OPTIONS'),
        ('ALL', 'ALL'),
    ]
    methods = models.CharField(
        max_length=10,
        choices=HTTP_METHODS,
        default='ALL',
        verbose_name="HTTP方法"
    )

    # 访问控制
    is_active = models.BooleanField(default=True, verbose_name="是否启用")
    require_login = models.BooleanField(default=True, verbose_name="需要登录")
    require_permission = models.BooleanField(default=False, verbose_name="需要特定权限")

    # 用户/组权限
    allowed_users = models.ManyToManyField(
        User,
        blank=True,
        verbose_name="允许的用户"
    )
    allowed_groups = models.ManyToManyField(
        Group,
        blank=True,
        verbose_name="允许的用户组"
    )

    # 时间控制
    valid_from = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="生效时间"
    )
    valid_until = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="过期时间"
    )

    # 自定义响应
    custom_response = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="自定义响应",
        help_text='JSON格式，如 {"message": "自定义错误消息", "code": 403}'
    )

    # 优先级（数字越小优先级越高）
    priority = models.IntegerField(
        default=0,
        verbose_name="优先级",
        help_text="数字越小优先级越高，0为默认优先级"
    )

    class Meta:
        verbose_name = "访问控制规则"
        verbose_name_plural = "访问控制规则"
        ordering = ['priority', 'name']

    def __str__(self):
        return self.name

    def match_url(self, path):
        """检查URL是否匹配规则"""
        pattern = re.compile(self.url_pattern)
        return pattern.match(path) is not None

    def is_valid_now(self):
        """检查规则是否在有效期内"""
        from django.utils import timezone
        now = timezone.now()

        if self.valid_from and now < self.valid_from:
            return False
        if self.valid_until and now > self.valid_until:
            return False
        return True

    def has_permission(self, user, permission_required=None):
        """检查用户是否有权限"""
        # 如果不需要登录，任何用户都有权限
        if not self.require_login:
            return True

        # 如果用户未认证
        if not user.is_authenticated:
            return False

        # 检查特定用户权限
        if self.require_permission and permission_required:
            if not user.has_perm(permission_required):
                return False

        # 检查允许的用户
        if self.allowed_users.exists() and user not in self.allowed_users.all():
            return False

        # 检查允许的用户组
        if self.allowed_groups.exists():
            user_groups = user.groups.all()
            if not any(group in user_groups for group in self.allowed_groups.all()):
                return False

        return True

