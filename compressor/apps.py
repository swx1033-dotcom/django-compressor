import logging
from importlib import import_module

from django.apps import AppConfig, apps


logger = logging.getLogger("compressor")


class CompressorConfig(AppConfig):
    name = "compressor"
    verbose_name = "Django Compressor"

    def ready(self):
        self._discover_filters()

    def _discover_filters(self):
        for app_config in apps.get_app_configs():
            if app_config.name == "compressor":
                continue
            try:
                import_module("%s.filters" % app_config.name)
            except ImportError:
                pass
            except Exception:
                logger.exception(
                    "Error importing filters from %s", app_config.name
                )