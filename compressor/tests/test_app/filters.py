from compressor.filters import FilterBase, register_filter


@register_filter("css")
class UpperCaseCSSFilter(FilterBase):
    def output(self, **kwargs):
        return self.content.upper()


@register_filter("js", name="upper_js")
class UpperCaseJSFilter(FilterBase):
    def output(self, **kwargs):
        return self.content.upper()