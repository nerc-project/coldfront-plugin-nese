#! /bin/bash
export MC_USER=AKIAIOSFODNN7EXAMPLE
export MC_PASS=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
export MC_HOST=192.168.39.199:30900
export MC_HOST_NESE=http://$MC_USER:$MC_PASS@$MC_HOST

# Use "user" namespace for testing with vanilla FS
# Use "ceph" namespace for use with cephfs FS
NAMESPACE=user

# Script depends on the following being installed:
# Minio mc client
# attr package (for getfattr, setfattr)
# jq for parsing

BASE_DIR=/home/jculbert/development/nerc/coldfront-plugin-nese/datatest/

# List the buckets and parse the directories out
BUCKET_DIRS=$(mc ls --json NESE | jq -r .key)

for b in $BUCKET_DIRS; do
    # Get the quota tag for each bucket
    COLDFRONT_QUOTA=$(mc tag list --json NESE/$b | jq -r .tagset.quota)

    # Get the quota extended attribute for cephfs
    DISK_QUOTA=$(getfattr -n $NAMESPACE.quota.max_bytes --only-values -m "^$NAMESPACE\\.quota\\.max_bytes" $BASE_DIR/$b)

    echo Bucket: $b CF: $COLDFRONT_QUOTA, D: $DISK_QUOTA

    if [ "$COLDFRONT_QUOTA" -ne "$DISK_QUOTA" ]; then
        setfattr -n $NAMESPACE.quota.max_bytes -v $COLDFRONT_QUOTA $BASE_DIR/$b
    fi
done
