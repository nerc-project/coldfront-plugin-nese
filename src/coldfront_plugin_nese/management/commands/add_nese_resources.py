from django.core.management.base import BaseCommand

from coldfront.core.resource.models import (Resource,
                                            ResourceAttribute,
                                            ResourceAttributeType,
                                            ResourceType)

from coldfront_plugin_nese import attributes


class Command(BaseCommand):
    help = 'Create NESE resource'

    def add_arguments(self, parser):
        parser.add_argument('--name', type=str, required=True,
                            help='Name of NESE S3 resource')
        parser.add_argument('--owner', type=str, required=True,
                            help='Owner of NESE S3 resource')
        parser.add_argument('--endpoint', type=str, required=True,
                            help='Endpoint of NESE S3 resource')
        parser.add_argument('--allocsz', type=int, required=False,
                            help='Default size of allocation', default=10)
        parser.add_argument('--capacity', type=int, required=True,
                            help='Capacity of S3 resource allocation')

    def handle(self, *args, **options):
        nese, _ = Resource.objects.get_or_create(
            resource_type=ResourceType.objects.get(name='Storage'),
            parent_resource=None,
            name=options['name'],
            description='NESE S3 Allocation',
            is_available=True,
            is_public=True,
            is_allocatable=True
        )

        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_ENDPOINT),
            resource=nese,
            value=options['endpoint']
        )

        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_OWNER),
            resource=nese,
            value=options['owner']
        )

        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name=attributes.RESOURCE_QUOTA),
            resource=nese,
            value=options['capacity']
        )

        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name="quantity_default_value"),
            resource=nese,
            value=options['allocsz']
        )

        ResourceAttribute.objects.get_or_create(
            resource_attribute_type=ResourceAttributeType.objects.get(
                name="quantity_label"),
            resource=nese,
            value='Bucket Quota (TB)'
        )
