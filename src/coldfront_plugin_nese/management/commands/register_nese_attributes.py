from django.core.management.base import BaseCommand

from coldfront.core.allocation import models as allocation_models
from coldfront.core.resource import models as resource_models

from coldfront_plugin_nese import attributes

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Add default NESE related choices'

    def register_allocation_attributes(self):

        logger.debug('Registering NESE attributes')

        attrinfo = [
            (attributes.ALLOCATION_TEXT_ATTRIBUTES, "Text"),
            (attributes.ALLOCATION_INT_ATTRIBUTES, "Int")
        ]

        for alloc_attr_type_names, attr_type_name in attrinfo:

            attr_type = allocation_models.AttributeType.objects.get(
                name=attr_type_name
            )

            for attr_name in alloc_attr_type_names:
                allocation_models.AllocationAttributeType.objects.get_or_create(
                    name=attr_name,
                    attribute_type=attr_type,
                    has_usage=False,
                    is_private=False
                )

    def register_resource_attributes(self):

        attrinfo = [
            (attributes.RESOURCE_TEXT_ATTRIBUTES, "Text"),
            (attributes.RESOURCE_INT_ATTRIBUTES, "Int")
        ]

        for rsrc_attr_type_names, attr_type_name in attrinfo:
            attr_type = resource_models.AttributeType.objects.get(
                name=attr_type_name
            )

            for attr_name in rsrc_attr_type_names:
                resource_models.ResourceAttributeType.objects.get_or_create(
                    name=attr_name,
                    attribute_type=attr_type
                )

    def add_allocation_status_choices(self):
        
        for choice in attributes.ALLOCATION_STATUS_CHOICES:
            allocation_models.AllocationStatusChoice.objects.get_or_create(
                name=choice
            )

    # def register_resource_type(self):
    #     resource_models.ResourceType.objects.get_or_create(
    #         name='NESE ', description='Open Storage Network')

    def handle(self, *args, **options):
        # self.register_resource_type()
        self.register_resource_attributes()
        self.register_allocation_attributes()
        self.add_allocation_status()
