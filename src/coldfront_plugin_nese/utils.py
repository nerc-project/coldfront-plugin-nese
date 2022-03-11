from subprocess import PIPE, run as runsub
import os
import secrets
import string
import boto3
import json
from rgwadmin import RGWAdmin
from rgwadmin.exceptions import RGWAdminException
from botocore.exceptions import ClientError

NESE_MC_ALIAS = "NESE"


def get_client(profile):
    client = boto3.client(
            's3',
            aws_access_key_id=profile['access_key'],
            aws_secret_access_key=profile['secret_key'],
            endpoint_url=f"{profile['scheme']}://{profile['endpoint']}"
        )
    return client


def apply_policy(bucket_name, user_name, profile):

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
        print(e)
        return False
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
        print(e)
        return False

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
            raise(e)

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
    rgw.set_bucket_quota(
        uid=profile['uid'],
        bucket=bucketname,
        max_size_kb=quota_kb,
        enabled=True)


def create_user_minio(
        username: str,
        profile: dict) -> dict:

    ALPHABET = string.ascii_letters + string.digits + "+/"
    user_secret = ''.join(
        secrets.choice(ALPHABET) for i in range(30)
    )

    subres = _execute_mcadmin(
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
        profile: dict) -> bool:

    # Note: Quota in TB
    # Throws if command is not successful
    _execute_mcadmin(
        "bucket",
        "quota",
        f"{NESE_MC_ALIAS}/{bucketname}",
        "--hard",
        f"{quota}t",
        profile=profile
    )


def _execute_mcadmin(*args, profile):
    subenv = os.environ.copy()
    mcailias_env = f"MC_HOST_{NESE_MC_ALIAS}"
    subenv[mcailias_env] = (
        f"{profile['scheme']}://"
        f"{profile['access_key']}:{profile['secret_key']}@"
        f"{profile['endpoint']}"
    )

    command = ("mc", "admin") + args
    subres = runsub(command, capture_output=True, check=True, env=subenv)

    # Throws with useful info if retcode is non-zero
    subres.check_returncode()
    return subres
