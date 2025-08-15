from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action, authentication_classes,permission_classes
from .models import Document
from .serializers import DocumentSerializer, DocumentUpdateSerializer
from rest_framework.permissions import IsAuthenticated
from rest_framework.permissions import AllowAny


@authentication_classes([])
@permission_classes([AllowAny])
class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.filter(is_visible=True)
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'update':
            return DocumentUpdateSerializer
        return super().get_serializer_class()
    def get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip

    def perform_create(self, serializer):
        ip = self.get_client_ip(self.request)
        serializer.save(created_by_ip=ip)

    def perform_update(self, serializer):
        # 版本号递增
        instance = self.get_object()
        ip = self.get_client_ip(self.request)
        serializer.save(
            version=instance.version + 1,
            updated_by_ip=ip
        )


    @action(detail=True, methods=['get'])
    def content(self, request, pk=None):
        document = self.get_object()
        return Response({
            'content': document.content,
            'version': document.version
        })

    @action(detail=True, methods=['put'])
    def save_content(self, request, pk=None):
        document = self.get_object()
        if not document.is_editable:
            return Response(
                {'error': '此文档不可编辑'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = DocumentUpdateSerializer(
            document,
            data=request.data
        )
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({
            'status': '保存成功',
            'version': document.version + 1
        })