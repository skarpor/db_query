# middleware.py
from django.http import HttpResponseForbidden
import redis
from django.conf import settings

class IPRestrictionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        ALLOWED_IPS = ['127.0.0.1','192.168.1.8']
        client_ip = self.get_client_ip(request)

        if client_ip not in ALLOWED_IPS:
            return HttpResponseForbidden("IP 禁止访问")

        return self.get_response(request)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
class IPControlMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.redis = redis.StrictRedis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            decode_responses=True
        )

    def __call__(self, request):
        client_ip = self.get_client_ip(request)
        
        # 检查黑名单（优先拦截）
        if self.redis.sismember("ip:blacklist", client_ip):
            return HttpResponseForbidden("您的IP已被封禁", status=403)
        
        # 如果启用白名单模式，则检查白名单
        if settings.IP_WHITELIST_ENABLED and not self.redis.sismember("ip:whitelist", client_ip):
            return HttpResponseForbidden("IP未授权访问", status=403)
        
        return self.get_response(request)

    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        return x_forwarded_for.split(',')[0] if x_forwarded_for else request.META.get('REMOTE_ADDR')
