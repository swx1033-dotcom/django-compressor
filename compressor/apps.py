import copy
from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules
from compressor.conf import settings
from compressor.filters import filter_registry


class CompressorConfig(AppConfig):
    name = 'compressor'
    verbose_name = 'Compressor'

    def ready(self):
        autodiscover_modules('filters')
        
        if not any(filter_registry.values()):
            return

        new_filters = copy.deepcopy(settings.COMPRESS_FILTERS)
        for filter_type, filters in filter_registry.items():
            if filter_type not in new_filters:
                new_filters[filter_type] = []
            
            existing = list(new_filters[filter_type])
            for filter_path in filters:
                if filter_path not in existing:
                    existing.append(filter_path)
            new_filters[filter_type] = existing
            
        settings.COMPRESS_FILTERS = new_filters
