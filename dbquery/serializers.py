from rest_framework import serializers
from .models import DatabaseConnection, SQLParameter, QueryInstance, ExecutionResult, ExecutionLog


class DatabaseConnectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = DatabaseConnection
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class SQLParameterSerializer(serializers.ModelSerializer):
    class Meta:
        model = SQLParameter
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')


class QueryInstanceSerializer(serializers.ModelSerializer):
    connection_name = serializers.ReadOnlyField(source='connection.name')
    parameter_names = serializers.ReadOnlyField(source='get_parameter_names')

    class Meta:
        model = QueryInstance
        fields = '__all__'
        read_only_fields = ('created_at', 'updated_at')

    def get_parameter_names(self, obj):
        return [param.name for param in obj.parameters.all()]


class ExecutionResultSerializer(serializers.ModelSerializer):
    query_instance_name = serializers.ReadOnlyField(source='query_instance.name')
    formatted_result_data = serializers.SerializerMethodField()

    class Meta:
        model = ExecutionResult
        fields = '__all__'
        read_only_fields = ('created_at',)

    def get_formatted_result_data(self, obj):
        # 确保返回的数据是列表格式
        if obj.result_data and not isinstance(obj.result_data, list):
            return [obj.result_data]
        return obj.result_data or []


class PaginatedExecutionResultSerializer(serializers.Serializer):
    count = serializers.IntegerField()
    next = serializers.URLField(allow_null=True)
    previous = serializers.URLField(allow_null=True)
    results = ExecutionResultSerializer(many=True)

class ExecutionLogSerializer(serializers.ModelSerializer):
    script_title = serializers.CharField(source='script.title', read_only=True)
    triggered_by_name = serializers.CharField(source='triggered_by.username', read_only=True)
    status = serializers.SerializerMethodField()

    class Meta:
        model = ExecutionLog
        fields = '__all__'

    def get_status(self, obj):
        return 'success' if obj.success else 'failed'
