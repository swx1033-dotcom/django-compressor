from compressor.filters import FilterBase, register_filter

@register_filter('css', name='my_custom_css')
class MyCustomCSSFilter(FilterBase):
    def input(self, **kwargs):
        return self.content.replace('black', 'white')

@register_filter('js')
class MyCustomJSFilter(FilterBase):
    def input(self, **kwargs):
        return self.content.replace('console.log', 'alert')
