from compressor.filters import register_filter, FilterBase


@register_filter('css', name='test_uppercase')
class TestUppercaseCssFilter(FilterBase):
    """Test CSS filter that converts content to uppercase."""
    
    def input(self, **kwargs):
        return self.content.upper()
    
    def output(self, **kwargs):
        return self.content.upper()


@register_filter('js', name='test_uppercase')
class TestUppercaseJsFilter(FilterBase):
    """Test JS filter that converts content to uppercase."""
    
    def input(self, **kwargs):
        return self.content.upper()
    
    def output(self, **kwargs):
        return self.content.upper()


@register_filter('css')
class TestAutoNameFilter(FilterBase):
    """Test CSS filter with auto-generated name."""
    
    def input(self, **kwargs):
        return self.content.replace('test', 'TEST')
