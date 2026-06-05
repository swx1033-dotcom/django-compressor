# flake8: noqa
from compressor.filters.base import (
    FilterBase,
    CallbackOutputFilter,
    CompilerFilter,
    CachedCompilerFilter,
    FilterError,
)

filter_registry = {
    'js': [],
    'css': [],
}

def register_filter(filter_type, name=None):
    """
    Register a custom filter for django-compressor.
    """
    def decorator(cls):
        dotted_path = f"{cls.__module__}.{cls.__name__}"
        if filter_type not in filter_registry:
            filter_registry[filter_type] = []
        if dotted_path not in filter_registry[filter_type]:
            filter_registry[filter_type].append(dotted_path)
        return cls
    return decorator
