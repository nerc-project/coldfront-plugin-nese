from django.conf import settings
from django_q.tasks import AsyncTask, Chain, fetch_group, delete_group
from django_q.humanhash import uuid
from coldfront.core.allocation.models import (
    Allocation,
    AllocationAttribute,
    AllocationAttributeType,
    AllocationStatusChoice
)
from coldfront.core.utils.mail import send_email_template
from coldfront.config.email import EMAIL_TICKET_SYSTEM_ADDRESS, EMAIL_SENDER
from functools import wraps
from django.db import transaction
from django.urls import reverse
from coldfront_plugin_nese import attributes, utils

import logging

ENDPOINT_TYPE_LIST = ['rgw', 'minio']

logger = logging.getLogger(__name__)


# Decorator to prevent task races
# select_for_update is the magic
def allocation_step(func):
    @wraps(func)
    def inner_func(*args, **kwargs):
        allocations = Allocation.objects.select_for_update().filter(
            pk=kwargs['allocation_pk']
        )
        with transaction.atomic():
            allocations.get()
            return func(*args, **kwargs)

    return inner_func


def process_nese_quota(allocation_pk):
    profile = _get_profile()
    t = AsyncTask(
        'coldfront_plugin_nese.tasks.provision_nese_quota',
        profile,
        allocation_pk=allocation_pk,
        hook='coldfront_plugin_nese.tasks._provision_nese_quota_hook'
    )
    t.run()


# Run periodically to make sure allocation quota value
# matches the value set on the bucket.
def process_nese_quota_sweep():

    profile = _get_profile()
    for alloc in Allocation.objects.all():

        # Get the allocation quota attribute
        quota_attr = alloc.get_attribute(attributes.ALLOCATION_QUOTA)
        allocation_quota = quota_attr.value

        # Get the allocation bucket name
        bucket_attr = alloc.get_attribute(attributes.ALLOCATION_BUCKETNAME)
        bucket_name = bucket_attr.value

        # Get the bucket quota from object store
        bucket_quota = utils.get_bucket_quota(bucket_name, profile)

        # Compare quota set in the store with what allocation
        # expects. If different, fix.
        if bucket_quota != allocation_quota:
            logger.info(
                f"Adjusting quota for bucket {bucket_name} "
                f"from {bucket_quota} to value specified "
                f"in allocation, {allocation_quota}"
            )
            process_nese_quota(alloc.pk) 


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

    logger.debug(
        "Starting bucket allocation chain for "
        f"project: {allocation.project.title} "
        f"bucket name: {bucket_name}"
    )

    # TODO: If not set use default quantity specification
    bucket_quota = (
        allocation.get_attribute(attributes.ALLOCATION_QUOTA)
        or
        allocation.quantity
    )

    bucket_user = f"{bucket_name}_datamanager"
    profile = {
        'endpoint': settings.NESE_ENDPOINT,
        'endpoint_type': settings.NESE_ENDPOINT_TYPE,
        'access_key': settings.NESE_ENDPOINT_ACCESS_KEY,
        'secret_key': settings.NESE_ENDPOINT_SECRET_KEY,
        'scheme': settings.NESE_ENDPOINT_SCHEME,
        'uid': settings.NESE_ENDPOINT_UID
    }

    group = uuid()[0]
    alloc_chain = Chain(group=group)

    alloc_chain.append(
        'coldfront_plugin_nese.tasks.provision_nese_user',
        bucket_user,
        profile=profile,
        allocation_pk=allocation_pk
    )

    alloc_chain.append(
        'coldfront_plugin_nese.tasks.provision_nese_bucket',
        bucket_name,
        bucket_quota,
        profile=profile,
        resgroup=group,
        allocation_pk=allocation_pk
    )

    alloc_chain.append(
        'coldfront_plugin_nese.tasks.update_nese_allocation',
        resgroup=group,
        allocation_pk=allocation_pk,
        hook=cleanup
    )

    alloc_chain.run()


def cleanup(task):
    delete_group(task.group)


# Individual Task Steps - Expeceted to be Idempotent
# Note: Allocation step decorator synchronizes. Uses
# allocaion_pk from function arguments
@allocation_step
def provision_nese_quota(
        profile,
        allocation_pk=None):

    alloc = Allocation.objects.get(pk=allocation_pk)
    allocation_quota = alloc.get_attribute(attributes.ALLOCATION_QUOTA)
    bucket_name = alloc.get_attribute(attributes.ALLOCATION_BUCKETNAME)

    if profile['endpoint_type'] != 'minio':
        utils.set_bucket_quota(bucket_name, allocation_quota, profile)
    else:
        tags = {
            'quota': allocation_quota,
            'rsrc': alloc.get_parent_resource.name,
            'pi': alloc.project.pi,
            'projname': alloc.project.title
        }

        utils.set_bucket_tags_minio(bucket_name, tags, profile)


def _provision_nese_quota_hook(task):

    # Task function is provision_nese_quota which has
    # args (profile, allocation_pk)

    allocation_pk = task.kwargs['allocation_pk']
    alloc = Allocation.objects.get(pk=allocation_pk)

    allocation_quota = alloc.get_attribute(attributes.ALLOCATION_QUOTA)
    bucket_name = alloc.get_attribute(attributes.ALLOCATION_BUCKETNAME)

    allocation_path = reverse('allocation-detail', args=[allocation_pk])
    allocation_url = f"{settings.CENTER_BASE_URL}/{allocation_path}"

    ctx = {
        'task': task,
        'allocation': alloc,
        'allocation_url': allocation_url,
        'quota': allocation_quota,
        'bucket_name': bucket_name
    }

    # comment
    if not task.success:
        send_email_template(
            "NESE Bucket quota adjustment failed.",
            "coldfront_plugin_nese/bucket_quota_failed.html",
            ctx,
            EMAIL_SENDER,
            [EMAIL_TICKET_SYSTEM_ADDRESS, ]
        )


@allocation_step
def provision_nese_user(
        username: str,
        profile: dict = None,
        allocation_pk: str = None) -> dict:

    logger.debug("Processing nese bucket user provisioning.")
    # Throws if bad profile
    _check_profile(profile)

    etype = profile['endpoint_type']
    if etype == 'rgw':
        uinfo = utils.create_user_rgw(username, profile)
    elif etype == 'minio':
        uinfo = utils.create_user_minio(username, profile)
    logger.debug("Processing nese bucket user provisioning - COMPLETED.")
    result = {
        'type': 'nese_user',
        'uid': uinfo['uid'],
        'access_key': uinfo['access_key'],
        'secret_key': uinfo['secret_key']
    }

    return result


@allocation_step
def provision_nese_bucket(
        bucket_name: str,
        quota: str,
        profile: dict = None,
        resgroup: str = None,
        allocation_pk: str = None) -> dict:

    logger.debug("Processing nese bucket provisioning")
    # Sanity check on endpoint type. Throws if problems.
    _check_profile(profile)

    user_tasks = fetch_group(resgroup, wait=5000)

    if user_tasks is None:
        raise RuntimeError("Create user task not found.")

    create_user_result = None
    # Should only be one result
    for t in user_tasks:
        if not t.success:
            raise RuntimeError(
                f"Cannot create bucket {bucket_name}. "
                "Depends on failed create user task."
            )

        if t.result.get('type', None) == 'nese_user':
            create_user_result = t.result
            break

    if create_user_result is None:
        raise RuntimeError(
            f"Cannot create bucket {bucket_name}. "
            "Depends on missing create user task result."
        )

    utils.create_bucket(bucket_name, profile)

    # Minio does not support CORS policy. CORS is on
    # by default for all buckets and HTTP verbs
    etype = profile['endpoint_type']
    if etype == 'rgw':
        utils.apply_policy_rgw(bucket_name, create_user_result['uid'], profile)
        utils.apply_cors(bucket_name, profile)
    elif etype == 'minio':
        utils.apply_policy_minio(
            bucket_name,
            create_user_result['uid'],
            profile
        )

    utils.set_bucket_quota(bucket_name, quota, profile)

    result = {
        'type': 'nese_bucket',
        'bucket_name': bucket_name,
        "bucket_quota": quota
    }

    return result


@allocation_step
def update_nese_allocation(
        allocation_pk: str = None,
        resgroup: str = None) -> dict:

    allocation = Allocation.objects.get(pk=allocation_pk)
    alloc_tasks = fetch_group(resgroup, count=2, wait=5000)
    failed = [f for f in alloc_tasks if not f.success]
    retval = ""

    # If any of the provisioning tasks failed, set the allocation status
    # to Provisioning Error and send email to ticket system
    # to have them fix the issue
    if len(failed) > 0:

        for f in failed:
            print(f"FAILINFO (task={f.func}): {f.result}")

        allocation_path = reverse('allocation-detail', args=[allocation_pk])
        allocation_url = f"{settings.CENTER_BASE_URL}/{allocation_path}"

        ctx = {
            'allocation': allocation,
            'allocation_url': allocation_url,
            'failed_tasks': failed
        }

        provisioning_error_status = AllocationStatusChoice.objects.get(
            name=attributes.ALLOCATION_STATUS_PROVISIONING_ERROR
        )
        allocation.status = provisioning_error_status
        allocation.save()
        send_email_template(
            "NESE Bucket provisioning failed.",
            "coldfront_plugin_nese/bucket_provision_failed.html",
            ctx,
            EMAIL_SENDER,
            [EMAIL_TICKET_SYSTEM_ADDRESS, ]
        )
        retval = f"NESE Bucket allocation for {allocation.description} failed."
    else:
        all_result_values = {}
        for t in alloc_tasks:
            all_result_values.update(t.result)

        allocation_attributes = {
            attributes.ALLOCATION_BUCKETNAME: all_result_values['bucket_name'],
            attributes.ALLOCATION_ACCESS_KEY: all_result_values['access_key'],
            attributes.ALLOCATION_SECRET_KEY: all_result_values['secret_key'],
            attributes.ALLOCATION_QUOTA: all_result_values['bucket_quota'],
        }

        for attr_type_name, attr_val in allocation_attributes.items():
            attr_type = AllocationAttributeType.objects.get(
                name=attr_type_name
            )
            AllocationAttribute.objects.get_or_create(
                allocation_attribute_type=attr_type,
                allocation=allocation,
                value=attr_val
            )

        retval = (
            "NESE Bucket allocation for "
            f"{allocation.description} succeeded."
        )

    return retval


# ######## Internal #############


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


def _get_profile():
    profile = {
        'endpoint': settings.NESE_ENDPOINT,
        'endpoint_type': settings.NESE_ENDPOINT_TYPE,
        'access_key': settings.NESE_ENDPOINT_ACCESS_KEY,
        'secret_key': settings.NESE_ENDPOINT_SECRET_KEY,
        'scheme': settings.NESE_ENDPOINT_SCHEME,
        'uid': settings.NESE_ENDPOINT_UID
    }

    return profile


def _check_profile(profile: str):

    # Check valid endpoint type
    etype = profile.get('endpoint_type', None)
    if etype not in ENDPOINT_TYPE_LIST:
        raise ValueError(f"Unrecognized endpoint type: {etype}")

    # Valid http scheme
    scheme = profile.get('scheme', None)
    if scheme not in ['http', 'https']:
        raise ValueError(f"Unrecognized endpoint scheme {scheme}")

    # Missing values
    required = ['endpoint', 'access_key', 'secret_key', 'uid']
    missing = [r for r in required if profile.get(r, None) is None]
    if len(missing) > 0:
        raise ValueError(
            f'Required profile values are missing: {",".join(missing)}'
        )
