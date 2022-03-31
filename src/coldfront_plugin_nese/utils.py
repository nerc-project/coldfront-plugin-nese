# from email import policy
from subprocess import run as runsub, CalledProcessError
import os
import secrets
import string
import boto3
import json
import tempfile
import time
from rgwadmin import RGWAdmin
from rgwadmin.exceptions import RGWAdminException
from botocore.exceptions import ClientError

from .exceptions import NESEProvisioningError

NESE_MC_ALIAS = "NESE"


def get_client(profile):
    client = boto3.client(
            's3',
            aws_access_key_id=profile['access_key'],
            aws_secret_access_key=profile['secret_key'],
            endpoint_url=f"{profile['scheme']}://{profile['endpoint']}"
        )
    return client


def apply_policy_minio(bucket_name, user_name, profile):
    policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "bucket read write policy",
                "Effect": "Allow",
                "Action": [
                    "s3:DeleteObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:PutObject"
                ],
                "Resource":[
                    f"arn:aws:s3:::{bucket_name}/*",
                    f"arn:aws:s3:::{bucket_name}"
                ]
            }
            ]
    }
    policy_str = json.dumps(policy)
    policy_name = f"{bucket_name}_policy"

    # Create the canned policy
    with tempfile.NamedTemporaryFile() as policy_file:
        policy_file.write(policy_str.encode())
        policy_file.flush()
        _execute_mc(
            "admin",
            "policy",
            "add",
            NESE_MC_ALIAS,
            policy_name,
            policy_file.name,
            profile=profile
        )

    # Apply the canned policy to the user
    _execute_mc(
        "admin",
        "policy",
        "set",
        NESE_MC_ALIAS,
        policy_name,
        f"user={user_name}",
        profile=profile
    )


def apply_policy_rgw(bucket_name, user_name, profile):

    bucket_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Sid": "bucket read write policy",
                "Effect": "Allow",
                "Principal": {"AWS": [f"arn:aws:iam:::user/{user_name}"]},
                "Action":[
                    "s3:DeleteObject",
                    "s3:GetObject",
                    "s3:ListBucket",
                    "s3:PutObject"
                ],
                "Resource":[
                    f"arn:aws:s3:::{bucket_name}/*",
                    f"arn:aws:s3:::{bucket_name}"
                ]
            },
            {
               "Sid": "bucket read policy",
               "Effect": "Allow",
               "Principal": {'AWS': ['*']},
               "Action":[
                   "s3:GetObject",
                   "s3:ListBucket"
                ],
               "Resource":[
                   f"arn:aws:s3:::{bucket_name}/*",
                   f"arn:aws:s3:::{bucket_name}"
               ]
            }
         ]
    }

    # Convert the policy from JSON dict to string
    bucket_policy = json.dumps(bucket_policy)

    # Set the new policy
    s3_client = get_client(profile)
    s3_client.put_bucket_policy(Bucket=bucket_name, Policy=bucket_policy)


def create_bucket(bucket_name, profile):
    """Create an S3 bucket

    :param bucket_name: Bucket to create
    :return: True if bucket created, else False
    """

    # Create bucket
    try:
        s3_client = get_client(profile)
        s3_client.create_bucket(Bucket=bucket_name)
    except ClientError as e:
        raise NESEProvisioningError(e)

    return True


def apply_cors(bucket_name, profile):

    cors_configuration = {
        'CORSRules': [{
            'AllowedHeaders': [
                '*'
            ],
            'AllowedMethods': [
                "HEAD",
                "GET",
                "PUT",
                "POST",
                "DELETE"
            ],
            'AllowedOrigins': [
                "https://*.mghpcc.org",
                "https://*.osn.mghpcc.org",
                "https://*.osn.xsede.org"
            ],
            'ExposeHeaders': [
                "ETag",
                "date",
                "x-amz-meta-custom-header",
                "x-amz-server-side-encryption",
                "x-amz-request-id",
                "x-amz-id-2"
            ],
            'MaxAgeSeconds': 3000
        }]
    }

    s3_client = get_client(profile)

    try:
        s3_client.put_bucket_cors(
            Bucket=bucket_name,
            CORSConfiguration=cors_configuration
        )
    except ClientError as e:
        raise NESEProvisioningError(e)

    return True


def create_user_rgw(username, profile, display_name=None, email=None):

    ret_user = None
    isSecure = profile['scheme'] == 'https'
    rgw = RGWAdmin(
        access_key=profile['access_key'],
        secret_key=profile['secret_key'],
        server=profile['endpoint'],
        secure=isSecure
    )

    try:
        ret_user = rgw.create_user(
            uid=username,
            display_name=display_name or username,
            email=email or "unknown@unknown.org",
            max_buckets=-1,
        )

    except RGWAdminException as e:
        if e.code == "UserAlreadyExists":
            print("INFO: User already exists")
            ret_user = rgw.get_user(uid=username)
        else:
            raise NESEProvisioningError(e)

    result = {
        'uid': username,
        'access_key': ret_user['keys'][0]['access_key'],
        'secret_key': ret_user['keys'][0]['secret_key']
    }

    return result


def set_bucket_quota_rgw(
        bucketname: str,
        quota: int,
        profile: dict) -> bool:

    isSecure = profile['scheme'] == 'https'
    rgw = RGWAdmin(
        access_key=profile['access_key'],
        secret_key=profile['secret_key'],
        server=profile['endpoint'],
        secure=isSecure
    )

    # Quota in TB to value in KB
    quota_kb = quota * (1024*1024*1024)
    try:
        rgw.set_bucket_quota(
            uid=profile['uid'],
            bucket=bucketname,
            max_size_kb=quota_kb,
            enabled=True)
    except Exception as e:
        raise NESEProvisioningError(e)


def create_user_minio(
        username: str,
        profile: dict) -> dict:

    ALPHABET = string.ascii_letters + string.digits + "+/"
    user_secret = ''.join(
        secrets.choice(ALPHABET) for i in range(30)
    )

    subres = _execute_mc(
        "admin",
        "user",
        "add",
        "--json",
        NESE_MC_ALIAS,
        username,
        user_secret,
        profile=profile
    )

    result = {
        'uid': username,
        'access_key': username,
        'secret_key': user_secret,
        'subres': subres
    }

    return result


def set_bucket_quota_minio(
        bucketname: str,
        quota: int,
        profile: dict):

    # Note: Quota in TB
    # Throws if command is not successful
    _execute_mc(
        "admin",
        "bucket",
        "quota",
        f"{NESE_MC_ALIAS}/{bucketname}",
        "--hard",
        f"{quota}t",
        profile=profile
    )


def set_bucket_tags_minio(
        bucketname: str,
        tags: dict,
        profile: dict):

    tags['timestamp'] = str(time.time())
    tagstr = "&".join([f"{k}={v}" for k, v in tags.items()])
    _execute_mc(
        "tag",
        "set",
        f"{NESE_MC_ALIAS}/{bucketname}",
        tagstr,
        profile=profile
    )


def get_bucket_tags_minio(
        bucketname: str,
        profile: dict) -> dict:

    tags_json_str = _execute_mc(
        "tag",
        "list",
        "--json"
        f"{NESE_MC_ALIAS}/{bucketname}",
        profile=profile
    )

    tags = json.loads(tags_json_str)

    return tags


def set_bucket_quota(bucket_name, quota, profile):

    etype = profile['endpoint_type']
    if etype == 'rgw':
        set_bucket_quota_rgw(bucket_name, quota, profile)

    elif etype == 'minio':
        tags = {
            'quota': quota,
            # 'rsrc': allocation.get_parent_resource.name,
            # 'pi': allocation.project.pi,
            # 'projname': allocation.project.title
        }

        # utils.set_bucket_quota_minio(bucket_name, quota, profile)
        set_bucket_tags_minio(bucket_name, tags, profile)


def get_bucket_quota(bucket_name, profile):
    etype = profile['endpoint_type']
    if etype == 'rgw':
        # TODO: Implement rgw bucket quota retrieval
        raise NotImplementedError()
        #get_bucket_quota_rgw(bucket_name, quota, profile)

    elif etype == 'minio':
        # utils.get_bucket_quota_minio(bucket_name, quota, profile)
        tags = get_bucket_tags_minio(bucket_name, profile)
        quota = tags['quota']

    return quota


def _execute_mc(*args, profile, timeout=60, input=None):
    subenv = os.environ.copy()
    mcailias_env = f"MC_HOST_{NESE_MC_ALIAS}"
    subenv[mcailias_env] = (
        f"{profile['scheme']}://"
        f"{profile['access_key']}:{profile['secret_key']}@"
        f"{profile['endpoint']}"
    )

    command = ("mc",) + args

    try:
        subres = runsub(
            command,
            capture_output=True,
            check=True,
            env=subenv,
            timeout=timeout,
            input=input
        )
    except CalledProcessError as e:
        msg = (
            f"MINIO CMD: {e.cmd}{os.linesep}"
            f"STDOUT: {e.stdout}{os.linesep}",
            f"STDERR: {e.stderr}{os.linesep}"
            f"RETCODE: {e.returncode}{os.linesep}"
        )
        raise NESEProvisioningError(msg)

    return subres
