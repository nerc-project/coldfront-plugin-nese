import os

from django.dispatch import receiver
from django.db.models.signals import post_save

from coldfront.core.allocation.models import Allocation, AllocationAttribute, AllocationAttributeType
from coldfront.core.allocation.signals import (allocation_activate,
                                               allocation_activate_user,
                                               allocation_disable,
                                               allocation_remove_user)

from .tasks import process_nese_allocation, process_nese_quota
from .attributes import ALLOCATION_QUOTA


@receiver(allocation_activate)
def activate_allocation_receiver(sender, **kwargs):
    allocation_pk = kwargs.get('allocation_pk')

    if _is_nese_allocation(allocation_pk):
        process_nese_allocation(allocation_pk)


@receiver(allocation_disable)
def allocation_disable_receiver(sender, **kwargs):
    allocation_pk = kwargs.get('allocation_pk')

    if _is_nese_allocation(allocation_pk):
        print(f"Allocation disable receiver, primary key: {allocation_pk}")


@receiver(post_save, sender=AllocationAttribute)
def UpdateAllocationQuota(sender, instance, created, **kwargs):

    quota_type = AllocationAttributeType.objects.get(
        name=ALLOCATION_QUOTA
    )

    if instance.allocation_attribute_type == quota_type and not created:
        process_nese_quota(instance.allocation.pk)


# TODO: Refactor so that nese allocation is its own type and we can
# detect based on resource type instead of relying
# on naming/descriptions.
def _is_nese_allocation(pk):
    allocation = Allocation.objects.get(pk=pk)
    desc_arry = [r.description for r in allocation.resources.all()]
    return 'NESE S3 Allocation' in desc_arry
