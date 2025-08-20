from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import JsonResponse

from .models import AccessControlRule
from django.conf import settings


class AccessControlMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.settings = getattr(settings, 'ACCESS_CONTROL_SETTINGS', {})

    def __call__(self, request):
        # 排除管理员界面（如果配置允许）
        if self.settings.get('EXCLUDE_ADMIN', False) and request.path.startswith('/admin/'):
            return self.get_response(request)
        # 排除静态文件
        # if request.path.startswith('/static/'):
        #     return self.get_response(request)
        # 确保request.user存在，如果不存在则使用匿名用户
        if not hasattr(request, 'user'):
            request.user = AnonymousUser()

        # 获取当前请求的路径和方法
        path = request.path
        method = request.method

        # 使用缓存获取规则
        # cache_key = 'access_control_rules'
        # rules = cache.get(cache_key)
        #
        # if rules is None:
        #     rules = list(AccessControlRule.objects.filter(is_active=True).order_by('priority'))
        #     cache.set(cache_key, rules, timeout=300)  # 缓存5分钟
        rules = AccessControlRule.objects.filter(is_active=True).order_by('priority')

        matched_rule = None

        for rule in rules:
            # 检查URL是否匹配
            if not rule.match_url(path):
                continue

            # 检查HTTP方法是否匹配
            if rule.methods != 'ALL' and method != rule.methods:
                continue

            # 检查规则是否在有效期内
            if not rule.is_valid_now():
                continue

            # 找到匹配的规则
            matched_rule = rule
            break

        # 如果没有匹配的规则，拒绝访问
        if not matched_rule:
            return JsonResponse({
                'error': 'Access denied',
                'message': 'No access rule matches this request',
                'code': 403
            }, status=403)

        # 检查用户权限
        if not matched_rule.has_permission(request.user):
            if matched_rule.custom_response:
                # 返回自定义响应
                response_data = matched_rule.custom_response
                status_code = response_data.get('code', 403)
                return JsonResponse(response_data, status=status_code)
            else:
                # 默认拒绝访问响应
                return JsonResponse({
                    'error': 'Access denied',
                    'message': 'You do not have permission to access this resource',
                    'code': 403
                }, status=403)

        # 规则匹配且用户有权限，继续处理请求
        response = self.get_response(request)
        return response


# from django.http import JsonResponse
# from django.utils import timezone
# from .models import AccessControlRule
# import json
#
#
# class AccessControlMiddleware:
#     def __init__(self, get_response):
#         self.get_response = get_response
#
#     def __call__(self, request):
#         # 获取当前请求的路径和方法
#         path = request.path
#         method = request.method
#         # 使用缓存获取规则
#         cache_key = 'access_control_rules'
#         rules = cache.get(cache_key)
#
#         if rules is None:
#             rules = list(AccessControlRule.objects.filter(is_active=True).order_by('priority'))
#             cache.set(cache_key, rules, timeout=300)  # 缓存5分钟
#
#         # 获取所有活跃的规则并按优先级排序
#         # rules = AccessControlRule.objects.filter(is_active=True).order_by('priority')
#
#         for rule in rules:
#             # 检查URL是否匹配
#             if not rule.match_url(path):
#                 continue
#
#             # 检查HTTP方法是否匹配
#             if rule.methods != 'ALL' and method != rule.methods:
#                 continue
#
#             # 检查规则是否在有效期内
#             if not rule.is_valid_now():
#                 continue
#
#             # 检查用户权限
#             if not rule.has_permission(request.user):
#                 if rule.custom_response:
#                     # 返回自定义响应
#                     response_data = rule.custom_response
#                     status_code = response_data.get('code', 403)
#                     return JsonResponse(response_data, status=status_code)
#                 else:
#                     # 默认拒绝访问响应
#                     return JsonResponse({
#                         'error': 'Access denied',
#                         'message': 'You do not have permission to access this resource',
#                         'code': 403
#                     }, status=403)
#
#             # 如果规则匹配且用户有权限，继续处理请求
#             break
#
#         # 没有匹配的规则或用户有权限，继续处理请求
#         response = self.get_response(request)
#         return response