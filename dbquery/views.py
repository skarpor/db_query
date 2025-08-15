import json

from rest_framework import viewsets, filters, status, generics
from rest_framework.decorators import action, authentication_classes, permission_classes
from rest_framework.response import Response
from rest_framework.pagination import PageNumberPagination
from django_filters.rest_framework import DjangoFilterBackend
from .models import DatabaseConnection, SQLParameter, QueryInstance, ExecutionResult, ExecutionLog
from .serializers import (
    DatabaseConnectionSerializer,
    SQLParameterSerializer,
    QueryInstanceSerializer,
    ExecutionResultSerializer,
    PaginatedExecutionResultSerializer,
    ExecutionLogSerializer)
import csv
from django.http import HttpResponse
from django.utils import timezone
from rest_framework.permissions import AllowAny

class StandardResultsSetPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class DatabaseConnectionViewSet(viewsets.ModelViewSet):
    queryset = DatabaseConnection.objects.all()
    serializer_class = DatabaseConnectionSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['db_type']
    search_fields = ['name', 'host', 'database']
    ordering_fields = ['name', 'created_at']


class SQLParameterViewSet(viewsets.ModelViewSet):
    queryset = SQLParameter.objects.all()
    serializer_class = SQLParameterSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ['name', 'description']
    ordering_fields = ['name', 'created_at']


@authentication_classes([])
@permission_classes([AllowAny])
class QueryInstanceViewSet(viewsets.ModelViewSet):
    queryset = QueryInstance.objects.all()
    serializer_class = QueryInstanceSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['connection']
    search_fields = ['name', 'sql_template']
    ordering_fields = ['name', 'created_at']

    @action(detail=True, methods=['post'])
    def execute(self, request, pk=None):
        query_instance = self.get_object()
        from .tasks import execute_query
        task = execute_query.delay(query_instance.id)
        return Response({
            'status': '任务已提交',
            'task_id': task.id
        }, status=status.HTTP_202_ACCEPTED)

@authentication_classes([])
@permission_classes([AllowAny])
class ExecutionResultViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = ExecutionResult.objects.all()
    serializer_class = ExecutionResultSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['query_instance', 'status']
    search_fields = ['query_instance__name', 'error_message']
    ordering_fields = ['created_at', 'execution_time']
    pagination_class = StandardResultsSetPagination

    @action(detail=True, methods=['get'])
    def detail(self, request, pk=None):
        execution_result = self.get_object()
        serializer = self.get_serializer(execution_result)
        return Response(serializer.data)

    @action(detail=True, methods=['get'])
    def export(self, request, pk=None):
        execution_result = self.get_object()

        if execution_result.status != 'success' or not execution_result.result_data:
            return Response({
                'error': '没有可导出的成功结果'
            }, status=status.HTTP_400_BAD_REQUEST)

        # 创建CSV响应
        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="result_{execution_result.id}_{timezone.now().strftime("%Y%m%d%H%M%S")}.csv"'

        # 写入CSV数据
        writer = csv.writer(response)
        data = execution_result.result_data

        # 统一处理字符串类型数据
        if isinstance(data, str):
            try:
                # 参考前端逻辑，先尝试解析JSON字符串
                parsed_data = json.loads(data)
                data = parsed_data
            except Exception as e:
                print(f"JSON解析失败: {str(e)}")
                data = [{'原始数据': data}]

        # 确保数据结构统一
        if not isinstance(data, list):
            data = [data]

        # 自动收集所有字段
        field_set = set()
        for item in data:
            if isinstance(item, dict):
                field_set.update(item.keys())
        headers = sorted(field_set)

        # 写入表头
        writer.writerow(headers)

        # 写入数据行
        for item in data:
            if isinstance(item, dict):
                row = [item.get(field, '') for field in headers]
            else:
                row = [str(item)]
            writer.writerow(row)

        return response

    @action(detail=False, methods=['get'])
    def latest(self, request):
        # 获取每个查询实例的最新执行结果
        latest_results = []
        query_instances = QueryInstance.objects.all()
        for q in query_instances:
            latest_result = q.results.order_by('-created_at').first()
            if latest_result:
                latest_results.append(latest_result)

        # 分页处理
        page = self.paginate_queryset(latest_results)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(latest_results, many=True)
        return Response(serializer.data)


@authentication_classes([])
@permission_classes([AllowAny])
class ExecutionLogList(generics.ListAPIView):
    serializer_class = ExecutionLogSerializer

    def get_queryset(self):
        queryset = ExecutionLog.objects.all().order_by('-executed_at')

        # 过滤条件
        status = self.request.query_params.get('status', None)
        search = self.request.query_params.get('search', None)

        if status:
            if status == 'success':
                queryset = queryset.filter(success=True)
            elif status == 'failed':
                queryset = queryset.filter(success=False)

        if search:
            queryset = queryset.filter(script__title__icontains=search)

        return queryset
