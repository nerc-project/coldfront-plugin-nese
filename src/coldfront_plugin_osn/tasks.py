from django.conf import settings
from django_q.tasks import Chain, result_group, delete_group
from django_q.humanhash import uuid
from coldfront.core.allocation.models import (
    Allocation, AllocationAttribute, AllocationAttributeType
)
from coldfront_plugin_osn import attributes, utils


# Find all allocation ids with attributes of
# a given type
def _get_alloc_pks(attr_name):
    attr_type = AllocationAttributeType.objects.get(
        name=attr_name
    )
    attrs = AllocationAttribute.objects.filter(
        allocation_attribute_type=attr_type
    )

    return [a.allocation.pk for a in attrs]


def process_nese_allocation(allocation_pk=None):

    alloc_pk_iter = None
    # Short circuit - if pk is passed, just process that
    if allocation_pk is not None:
        alloc_pk_iter = [allocation_pk]
    else:
        # Find allocations with buckets spec'd but no keys
        #
        # Create "bucket set" of allocations with bucketnames
        # Create "key set" of allocations with secret keys
        # Subtract key set from bucket set == pks of allocs with
        # buckets defined but no keys
        attr_pk_list_buckets = _get_alloc_pks(attributes.ALLOCATION_BUCKETNAME)
        attr_pk_list_secrets = _get_alloc_pks(attributes.ALLOCATION_SECRET_KEY)
        alloc_pk_iter = set(attr_pk_list_buckets) - set(attr_pk_list_secrets)

    for pk in alloc_pk_iter:
        start_allocation_task(pk)


def start_allocation_task(allocation_pk):

    allocation = Allocation.objects.get(pk=allocation_pk)

    bucket_name = allocation.get_attribute(attributes.ALLOCATION_BUCKETNAME)
    bucket_sz = allocation.quantity
    bucket_user = f"{bucket_name}_datamanager"
    profile = {
        'endpoint': settings.NESE_ENDPOINT,
        'endpoint_type': settings.NESE_ENDPOINT_TYPE,
        'access_key': settings.NESE_ENDPOINT_ACCESS_KEY,
        'secret_key': settings.NESE_ENDPOINT_SECRET_KEY,
        'scheme': settings.NESE_ENDPOINT_SCHEME
    }

    group = uuid()[0]
    alloc_chain = Chain(group=group)

    alloc_chain.append(
        'coldfront_plugin_osn.tasks.provision_nese_user',
        bucket_user,
        profile
    )

    alloc_chain.append(
        'coldfront_plugin_osn.tasks.provision_nese_bucket',
        bucket_name,
        bucket_sz,
        profile,
        resgroup=group
    )

    alloc_chain.append(
        'coldfront_plugin_osn.tasks.update_nese_allocation',
        allocation_pk,
        resgroup=group
    )

    alloc_chain.run()


def provision_nese_user(
        username: str,
        profile: dict) -> dict:

    if profile.get('endpoint_type', None) == 'rgw':
        result = utils.create_user_rgw(username, profile)
    else:
        result = utils.create_user_minio(username, profile)

    result['type'] = 'nese_user'

    return result


def provision_nese_bucket(
        bucket_name: str,
        bucket_sz: int,
        profile: dict,
        resgroup: str = None) -> dict:

    results = result_group(resgroup, wait=5000)

    create_user_result = None
    # Should only be one result
    for res in results:
        if res.get('type', None) == 'nese_user':
            create_user_result = res
            break

    if create_user_result is not None:
        utils.create_bucket(bucket_name, profile)
        utils.apply_policy(bucket_name, res['uid'], profile)
        # Minio does not support CORS policy. It's on
        # by default for all buckets and HTTP verbs
        if profile['endpoint_type'] != 'mino':
            utils.apply_cors(bucket_name, profile)

    result = {
        'type': 'nese_bucket',
        'bucket_name': bucket_name
    }
    return result


def update_nese_allocation(
        allocation_pk,
        resgroup: str = None) -> dict:

    results = result_group(resgroup, count=2, wait=5000)
    all_result_values = {}
    for r in results:
        all_result_values.update(r)

    allocation_attributes = {
        attributes.ALLOCATION_BUCKETNAME: all_result_values['bucket_name'],
        attributes.ALLOCATION_ACCESS_KEY: all_result_values['access_key'],
        attributes.ALLOCATION_SECRET_KEY: all_result_values['secret_key'],
    }

    allocation = Allocation.objects.get(pk=allocation_pk)

    for attr_type_name, attr_val in allocation_attributes.items():
        attr_type = AllocationAttributeType.objects.get(name=attr_type_name)
        AllocationAttribute.objects.get_or_create(
            allocation_attribute_type=attr_type,
            allocation=allocation,
            value=attr_val
        )

    allocation_attributes['type'] = 'osn_allocation'

    delete_group(resgroup)
    return allocation_attributes
