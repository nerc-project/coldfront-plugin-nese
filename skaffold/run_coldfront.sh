#!/bin/bash

set -xe

if [[ ! -z "${REDIS_HOST}" ]]
then
>&2 echo "Waiting for redis..."
while ! nc -z $REDIS_HOST 6379; do sleep 5; done
fi

>&2 echo "Waiting for database..."

DATABASE_PORT=${DATABASE_PORT:-3306}

while ! echo exit | nc $DATABASE_HOST $DATABASE_PORT; do sleep 5; done

>&2 echo "Database is up - Starting"

sleep 10

DJANGO_SUPERUSER_PASSWORD=password

if [[ "$1" == "qcluster" ]]
then


  >&2 echo "Starting Cluster Worker Node..."

  watchgod django.core.management.execute_from_command_line --args qcluster

else
  >&2 echo "Starting Coldfront Instace..."

  if [[ "$INITIAL_SETUP" == "True" ]]
  then
    python -m django initial_setup
    python -m django register_openstack_attributes
    python -m django createsuperuser --username admin --email admin@admin.com --noinput || true
    python -m django register_nese_attributes
    python -m django add_nese_resources --owner HARVARD --endpoint https://s3.nese.mghpcc.org --capacity 100 --name "NESE Ceph/S3 (HU)"
  fi

  if [[ "$LOAD_TEST_DATA" == "True" ]]
  then
    python -m django load_test_data
  fi

  python -m gunicorn  coldfront.config.wsgi --timeout 120 --reload --bind=0.0.0.0:8080 
fi
