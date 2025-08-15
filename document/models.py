from django.contrib.auth.models import User
from django.db import models
from django.conf import settings
import os


class Document(models.Model):
    title = models.CharField(max_length=200, verbose_name="标题")
    file_name = models.CharField(max_length=100, unique=True, verbose_name="文件名")
    content = models.TextField(blank=True, verbose_name="内容")
    is_visible = models.BooleanField(default=True, verbose_name="是否可见")
    is_editable = models.BooleanField(default=True, verbose_name="是否可编辑")
    version = models.IntegerField(default=1, verbose_name="版本号")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="创建时间")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="更新时间")
    created_by = models.GenericIPAddressField(null=True, blank=True, verbose_name="创建IP")
    updated_by = models.GenericIPAddressField(null=True, blank=True, verbose_name="最后修改IP")

    class Meta:
        verbose_name = "文档管理"
        verbose_name_plural = "文档管理"
        ordering = ['-updated_at']

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        # 保存到文件系统
        if settings.DOCUMENTS_DIR:
            file_path = os.path.join(settings.DOCUMENTS_DIR, self.file_name)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(self.content)
