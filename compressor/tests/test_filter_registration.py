from django.test import TestCase, override_settings
from django.test.utils import setup_test_environment

from compressor.filters import register_filter, FilterBase, get_registered_filters
from compressor.base import Compressor


class FilterRegistrationTestCase(TestCase):
    """Test cases for the filter registration decorator mechanism."""

    def test_register_filter_decorator(self):
        """Test that the decorator properly registers filter classes."""
        from compressor.tests.test_app.filters import (
            TestUppercaseCssFilter,
            TestUppercaseJsFilter,
            TestAutoNameFilter,
        )
        
        css_filters = get_registered_filters('css')
        js_filters = get_registered_filters('js')
        
        self.assertIn('test_uppercase', css_filters)
        self.assertIs(css_filters['test_uppercase'], TestUppercaseCssFilter)
        
        self.assertIn('test_uppercase', js_filters)
        self.assertIs(js_filters['test_uppercase'], TestUppercaseJsFilter)
        
        auto_name = 'compressor.tests.test_app.filters.TestAutoNameFilter'
        self.assertIn(auto_name, css_filters)
        self.assertIs(css_filters[auto_name], TestAutoNameFilter)

    def test_register_filter_invalid_type(self):
        """Test that registering with invalid filter_type raises ValueError."""
        with self.assertRaises(ValueError) as context:
            @register_filter('invalid_type')
            class InvalidFilter(FilterBase):
                def input(self, **kwargs):
                    return self.content
        
        self.assertIn("Invalid filter_type", str(context.exception))

    def test_register_filter_non_subclass(self):
        """Test that registering a non-FilterBase subclass raises TypeError."""
        with self.assertRaises(TypeError) as context:
            @register_filter('css')
            class NotAFilter:
                pass
        
        self.assertIn("must be a subclass of FilterBase", str(context.exception))

    @override_settings(INSTALLED_APPS=[
        'django.contrib.staticfiles',
        'compressor',
        'compressor.tests.test_app',
    ])
    def test_auto_discovery(self):
        """Test that filters are auto-discovered from installed apps."""
        from compressor.apps import CompressorConfig
        from compressor.conf import settings
        
        config = CompressorConfig('compressor', 'compressor')
        config._auto_discover_filters()
        
        css_filters = get_registered_filters('css')
        self.assertIn('test_uppercase', css_filters)

    def test_filter_execution(self):
        """Test that registered filters can be executed correctly."""
        from compressor.tests.test_app.filters import TestUppercaseCssFilter
        
        content = "body { color: red; }"
        filter_instance = TestUppercaseCssFilter(content, filter_type='css')
        
        result = filter_instance.input()
        self.assertEqual(result, "BODY { COLOR: RED; }")
        
        result = filter_instance.output()
        self.assertEqual(result, "BODY { COLOR: RED; }")

    @override_settings(COMPRESS_FILTERS={
        'css': ['compressor.filters.css_default.CssAbsoluteFilter'],
        'js': ['compressor.filters.jsmin.rJSMinFilter'],
    })
    def test_compress_filters_merges_registered_filters(self):
        """Test that Compressor merges registered filters with configured filters."""
        from compressor.tests.test_app.filters import TestUppercaseCssFilter
        
        compressor = Compressor('css', content='body { color: red; }')
        
        filter_paths = compressor.filters
        
        configured_filter = 'compressor.filters.css_default.CssAbsoluteFilter'
        self.assertIn(configured_filter, filter_paths)
        
        registered_filter = 'compressor.tests.test_app.filters.TestAutoNameFilter'
        self.assertIn(registered_filter, filter_paths)

    @override_settings(COMPRESS_FILTERS={
        'css': [
            'compressor.filters.css_default.CssAbsoluteFilter',
            'compressor.tests.test_app.filters.TestAutoNameFilter',
        ],
        'js': ['compressor.filters.jsmin.rJSMinFilter'],
    })
    def test_configured_filters_have_priority(self):
        """Test that configured filters have priority and registered filters are not duplicated."""
        compressor = Compressor('css', content='body { color: red; }')
        
        filter_paths = compressor.filters
        
        count = filter_paths.count('compressor.tests.test_app.filters.TestAutoNameFilter')
        self.assertEqual(count, 1, "Filter should not be duplicated")
        
        self.assertEqual(
            filter_paths.index('compressor.filters.css_default.CssAbsoluteFilter'),
            0,
            "Configured filters should come first"
        )
