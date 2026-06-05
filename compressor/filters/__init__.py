# flake8: noqa
from compressor.filters.base import (
    FilterBase,
    CallbackOutputFilter,
    CompilerFilter,
    CachedCompilerFilter,
    FilterError,
)


_filter_registry = {
    'css': {},
    'js': {},
}


def register_filter(filter_type, name=None):
    """
    Class decorator to register a filter class.
    
    Args:
        filter_type: The type of filter, either 'js' or 'css'.
        name: Optional name for the filter. If not provided, 
              the class name will be used.
    
    Example:
        @register_filter('css', name='my_custom_filter')
        class MyCustomFilter(FilterBase):
            def input(self, **kwargs):
                return self.content.upper()
    """
    def decorator(cls):
        if filter_type not in _filter_registry:
            raise ValueError(
                f"Invalid filter_type '{filter_type}'. Must be one of: {', '.join(_filter_registry.keys())}"
            )
        if not issubclass(cls, FilterBase):
            raise TypeError(
                f"Filter class must be a subclass of FilterBase, got {cls.__name__}"
            )
        filter_name = name or f"{cls.__module__}.{cls.__name__}"
        _filter_registry[filter_type][filter_name] = cls
        return cls
    return decorator


def get_registered_filters(filter_type):
    """
    Get all registered filters for a given filter type.
    
    Args:
        filter_type: The type of filter, either 'js' or 'css'.
    
    Returns:
        A dictionary of registered filters for the given type.
    """
    return _filter_registry.get(filter_type, {})
