from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    DatabaseConnectionViewSet,
    SQLParameterViewSet,
    QueryInstanceViewSet,
    ExecutionResultViewSet,
    ExecutionLogList)

router = DefaultRouter()
router.register(r'database-connections', DatabaseConnectionViewSet)
router.register(r'sql-parameters', SQLParameterViewSet)
router.register(r'query-instances', QueryInstanceViewSet)
router.register(r'execution-results', ExecutionResultViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('execution-results/<int:pk>/export/', ExecutionResultViewSet.as_view({'get': 'export'}), name='export_result'),
    path('execution-logs/', ExecutionLogList.as_view(), name='execution-log-list'),

]