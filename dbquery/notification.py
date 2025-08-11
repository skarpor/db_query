import logging
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
import requests

logger = logging.getLogger(__name__)


class NotificationService:
    @staticmethod
    def send_notification(result):
        """根据查询结果发送通知"""
        try:
            query = result.query_instance
            notifications = query.notifications.all()

            if not notifications:
                return

            context = {
                'query_name': query.name,
                'execution_time': result.execution_time,
                'success': result.success,
                'duration': result.duration,
                'error_message': result.error_message,
                'result_count': result.row_count
            }

            for notification in notifications:
                should_send = (
                        (notification.trigger_on_success and result.success) or
                        (notification.trigger_on_failure and not result.success)
                )

                if should_send:
                    if notification.notification_type == 'email':
                        NotificationService.send_email(notification, context)
                    # elif notification.notification_type == 'sms':
                    #     NotificationService.send_sms(notification, context)
                    elif notification.notification_type == 'webhook':
                        NotificationService.send_webhook(notification, context, result)

                    notification.last_sent = result.execution_time
                    notification.save()

                    # 记录通知日志
                    # SystemLog.objects.create(
                    #     level='INFO',
                    #     category='NOTIFICATION',
                    #     message=f"发送通知: {query.name}",
                    #     object_id=query.id,
                    #     details={
                    #         'type': notification.notification_type,
                    #         'recipient': notification.recipient,
                    #         'status': 'success' if result.success else 'failure'
                    #     }
                    # )

        except Exception as e:
            logger.error(f"发送通知失败: {str(e)}", exc_info=True)
            # 记录错误日志
            # SystemLog.objects.create(
            #     level='ERROR',
            #     category='NOTIFICATION',
            #     message=f"发送通知失败: {query.name if 'query' in locals() else '未知'}",
            #     details={
            #         'error': str(e)
            #     }
            # )

    @staticmethod
    def send_email(notification, context):
        """发送电子邮件通知"""
        subject = f"查询执行通知: {context['query_name']} - {'成功' if context['success'] else '失败'}"

        # 使用模板渲染邮件内容
        html_message = render_to_string('emails/query_notification.html', context)
        text_message = render_to_string('emails/query_notification.txt', context)

        send_mail(
            subject=subject,
            message=text_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[notification.recipient],
            html_message=html_message,
            fail_silently=False
        )

    @staticmethod
    def send_sms(notification, context):
        """发送短信通知（示例使用Twilio）"""
        if not all([hasattr(settings, 'TWILIO_ACCOUNT_SID'),
                    hasattr(settings, 'TWILIO_AUTH_TOKEN'),
                    hasattr(settings, 'TWILIO_PHONE_NUMBER')]):
            logger.warning("未配置短信服务")
            return

        # from twilio.rest import Client

        # client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)

        status = "成功" if context['success'] else f"失败: {context['error_message'][:30]}" if context[
            'error_message'] else "失败"
        message_body = (
            f"查询[{context['query_name']}]执行{status} "
            f"时间:{context['execution_time'].strftime('%Y-%m-%d %H:%M')} "
            f"耗时:{context['duration']:.2f}秒"
        )

        # client.messages.create(
        #     body=message_body,
        #     from_=settings.TWILIO_PHONE_NUMBER,
        #     to=notification.recipient
        # )

    @staticmethod
    def send_webhook(notification, context, result):
        """发送Webhook通知"""
        payload = {
            'event': 'query_execution',
            'query_id': result.query_instance_id,
            'query_name': context['query_name'],
            'status': 'success' if context['success'] else 'failure',
            'execution_time': context['execution_time'].isoformat(),
            'duration': context['duration'],
            'result_count': context['result_count']
        }

        if not context['success']:
            payload['error'] = context['error_message']

        try:
            response = requests.post(
                notification.recipient,
                json=payload,
                timeout=10
            )
            response.raise_for_status()
        except requests.RequestException as e:
            logger.error(f"Webhook发送失败: {str(e)}")