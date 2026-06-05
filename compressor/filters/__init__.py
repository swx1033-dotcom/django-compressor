# flake8: noqa
from compressor.filters.base import (
    FilterBase,
    CallbackOutputFilter,
    CompilerFilter,
    CachedCompilerFilter,
    FilterError,
)

_registered_filters = {
    "css": [],
    "js": [],
}


def get_registered_filters():
    return _registered_filters


def register_filter(filter_type, name=None):
    """
    Class decorator for registering compressor filters.

    Usage::

        from compressor.filters import FilterBase, register_filter

        @register_filter('css')
        class MyCSSFilter(FilterBase):
            def output(self, **kwargs):
                return self.content.replace('foo', 'bar')

    The decorated class is automatically discovered and made available
    as a compressor filter, without needing to add it to COMPRESS_FILTERS.

    :param filter_type: 'css' or 'js'
    :param name: Optional name for the filter (not currently used for lookup)
    """
    if filter_type not in ("css", "js"):
        raise ValueError(
            'filter_type must be "css" or "js", got %r' % filter_type
        )

    def decorator(cls):
        if cls not in _registered_filters[filter_type]:
            _registered_filters[filter_type].append(cls)
        cls._compressor_filter_type = filter_type
        cls._compressor_filter_name = name or cls.__name__
        return cls

    return decorator