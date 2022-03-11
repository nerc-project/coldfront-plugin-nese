"""
Author: Jim Culbert
Copyright (c) 2022 MGHPCC
All rights reserved. No warranty, explicit or implicit, provided.
"""

from django.apps import AppConfig


class NesePluginConfig(AppConfig):
    name = 'coldfront_plugin_nese'

    def ready(self):
        import coldfront_plugin_nese.signals
