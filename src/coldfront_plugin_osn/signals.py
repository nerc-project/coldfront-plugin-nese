import os

from django.dispatch import receiver

from coldfront.core.allocation.signals import (allocation_activate,
                                               allocation_activate_user,
                                               allocation_disable,
                                               allocation_remove_user)

from .tasks import process_nese_allocation

@receiver(allocation_activate)
def activate_allocation_receiver(sender, **kwargs):
    allocation_pk = kwargs.get('allocation_pk')
    process_nese_allocation()


@receiver(allocation_disable)
def allocation_disable_receiver(sender, **kwargs):
    allocation_pk = kwargs.get('allocation_pk')
    print(f"Allocation disable receiver, primary key: {allocation_pk}")


@receiver(allocation_activate_user)
def activate_allocation_user_receiver(sender, **kwargs):
    allocation_user_pk = kwargs.get('allocation_user_pk')
    print(f"Allocation add user receiver, primary key: {allocation_user_pk}")


@receiver(allocation_remove_user)
def allocation_remove_user_receiver(sender, **kwargs):
    allocation_user_pk = kwargs.get('allocation_user_pk')
    print(f"Allocation remove user receiver, primary key: {allocation_user_pk}")
