from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import ScriptApproval, ScriptDraft, ApprovedScript


@receiver(post_save, sender=ScriptDraft)
def handle_draft_submission(sender, instance, **kwargs):
    if instance.status == 'submitted' and not hasattr(instance, 'scriptapproval'):
        ScriptApproval.objects.create(draft=instance)

@receiver(post_save, sender=ScriptApproval)
def handle_approval(sender, instance, **kwargs):
    if instance.status == 'approved' and not hasattr(instance, 'approvedscript'):
        ApprovedScript.objects.create(
            title=instance.draft.title,
            code=instance.draft.code,
            approval_record=instance
        )
