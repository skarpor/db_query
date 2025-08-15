from rest_framework import serializers
from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    created_by = serializers.StringRelatedField()
    updated_by = serializers.StringRelatedField()

    class Meta:
        model = Document
        fields = [
            'id', 'title', 'file_name', 'content',
            'is_visible', 'is_editable', 'version',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]
        read_only_fields = [
            'id', 'file_name', 'version',
            'created_at', 'updated_at', 'created_by', 'updated_by'
        ]


class DocumentUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['content', 'version']

    def validate(self, data):
        instance = self.instance
        if instance.version > data['version']:
            raise serializers.ValidationError(
                "文档已被更新，请刷新后重试"
            )
        return data