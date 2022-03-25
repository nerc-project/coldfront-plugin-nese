import os
import pkgutil
import secrets
from sys import path as sys_path

from coldfront.config.settings import *


plugin_openstack = pkgutil.get_loader('coldfront_plugin_openstack.config')
plugin_keycloak_usersearch = pkgutil.get_loader('coldfront_plugin_keycloak_usersearch')

include(plugin_openstack.get_filename())
include(plugin_keycloak_usersearch.get_filename())

ADDITIONAL_USER_SEARCH_CLASSES = ["coldfront_plugin_keycloak_usersearch.search.KeycloakUserSearch"]

# ColdFront upstream ignores the env var even though it exposes the setting.
# https://github.com/ubccr/coldfront/blob/c490acddd2853a39201ebc58d3ba0d2c1eb8f623/coldfront/config/core.py#L80
ACCOUNT_CREATION_TEXT = os.getenv('ACCOUNT_CREATION_TEXT')

if os.getenv('DEBUG', 'False') == 'True':
    SESSION_COOKIE_SECURE = False

SESSION_COOKIE_SAMESITE = 'Lax'

DATABASES = {
    'default': {
        'ENGINE': ENV.get_value(
            'DATABASE_ENGINE',
            default='django.db.backends.mysql'
        ),
        'NAME': ENV.get_value('DATABASE_NAME', default='coldfront'),
        'USER': ENV.get_value('DATABASE_USER'),
        'PASSWORD': ENV.get_value('DATABASE_PASSWORD'),
        'HOST': ENV.get_value('DATABASE_HOST'),
        'PORT': ENV.get_value('DATABASE_PORT', default=3306),
    },
}

ALLOWED_HOSTS = ['.mss.mghpcc.org', '.mghpcc.org']

# LOGGING['loggers']['mozilla_django_oidc'] = {
#     'handlers': ['console'],
#     'level': 'DEBUG'
#     }

#LOGGING['django']['level'] = 'DEBUG'

plugin_nese = pkgutil.get_loader('coldfront_plugin_nese.config')
include(plugin_nese.get_filename())

# SECRET_KEY = secrets.token_urlsafe()

Q_CLUSTER = {
    'name': 'coldfront',
    'workers': 4,
    'recycle': 500,
    'timeout': 60,
    'compress': True,
    'save_limit': 250,
    'queue_limit': 500,
    'cpu_affinity': 1,
    'label': 'Django Q',
    'redis': {
        'host': 'coldfront-redis',
        'port': 6379,
        'db': 0, 
    }
}
