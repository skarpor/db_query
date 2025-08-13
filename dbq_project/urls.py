"""
URL configuration for dbq_project project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.http import HttpResponse
from django.views.static import serve
from django.conf import settings
import os
def serve_vue(request):
    with open(os.path.join(settings.STATICFILES_DIRS[0], 'index.html'), 'rb') as f:
        content = f.read().decode('utf-8')
        return HttpResponse(content, content_type='text/html')

urlpatterns = [
    path('', serve_vue),
    path('admin/', admin.site.urls),
    path('api/', include('dbquery.urls')),
]
