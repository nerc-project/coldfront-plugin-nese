"""
Author: Jim Culbert
Copyright (c) 2022 MGHPCC
All rights reserved. No warranty, explicit or implicit, provided.
"""

from django.apps import AppConfig


class OsnPluginConfig(AppConfig):
    name = 'coldfront_plugin_osn'

    def ready(self):
        import coldfront_plugin_osn.signals
