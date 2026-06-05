import importlib
import logging
from pathlib import Path

from django.apps import AppConfig
from django.conf import settings

logger = logging.getLogger(__name__)


class CompressorConfig(AppConfig):
    name = 'compressor'
    verbose_name = 'Django Compressor'

    def ready(self):
        self._auto_discover_filters()

    def _auto_discover_filters(self):
        """
        Automatically discover and register filters from installed apps.
        
        Iterates through all installed Django apps and imports their
        filters.py module if it exists. This triggers the @register_filter
        decorator to register any filter classes defined in those modules.
        """
        for app_config in settings.INSTALLED_APPS:
            app_module_path = app_config
            filters_module = f"{app_module_path}.filters"
            
            try:
                importlib.import_module(filters_module)
                logger.debug(f"Successfully imported filters module from {app_module_path}")
            except ModuleNotFoundError:
                pass
            except ImportError as e:
                logger.warning(
                    f"Error importing filters module from {app_module_path}: {e}"
                )
            except Exception as e:
                logger.warning(
                    f"Unexpected error while importing filters from {app_module_path}: {e}"
                )
