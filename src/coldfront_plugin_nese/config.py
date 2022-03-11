from coldfront.config.base import INSTALLED_APPS
from coldfront.config.logging import LOGGING
from coldfront.config.env import ENV

if 'coldfront_plugin_nese' not in INSTALLED_APPS:
    INSTALLED_APPS += [
        'coldfront_plugin_nese',
    ]

NESE_ENDPOINT = ENV.str('NESE_ENDPOINT')
NESE_ENDPOINT_TYPE = ENV.str('NESE_ENDPOINT_TYPE', default='rgw')
NESE_ENDPOINT_SCHEME = ENV.str('NESE_ENDPOINT_SCHEME', default='https')
NESE_ENDPOINT_ACCESS_KEY = ENV.str('NESE_ENDPOINT_ACCESS_KEY')
NESE_ENDPOINT_SECRET_KEY = ENV.str('NESE_ENDPOINT_SECRET_KEY')
NESE_ENDPOINT_UID = ENV.str('NESE_ENDPOINT_UID')

LOGGING['loggers']['coldfront_plugin_nese'] = {
    'handlers': ['console'],
    'level': 'DEBUG'
}
