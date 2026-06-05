import os
import sys
import django
from django.conf import settings
from compressor.base import Compressor

def run_test():
    settings.configure(
        DEBUG=True,
        INSTALLED_APPS=[
            'compressor',
            'test_app',
        ],
        COMPRESS_FILTERS={
            'css': ['compressor.filters.css_default.CssAbsoluteFilter'],
            'js': []
        },
        COMPRESS_ENABLED=True,
        COMPRESS_ROOT='/tmp',
        COMPRESS_URL='/static/',
        TEMPLATES=[
            {
                'BACKEND': 'django.template.backends.django.DjangoTemplates',
                'DIRS': [],
                'APP_DIRS': True,
                'OPTIONS': {
                    'context_processors': [
                        'django.template.context_processors.debug',
                        'django.template.context_processors.request',
                    ],
                },
            },
        ],
    )

    django.setup()

    from compressor.conf import settings as comp_settings

    print("Registered CSS filters:", comp_settings.COMPRESS_FILTERS['css'])
    print("Registered JS filters:", comp_settings.COMPRESS_FILTERS['js'])

    assert 'test_app.filters.MyCustomCSSFilter' in comp_settings.COMPRESS_FILTERS['css']
    assert 'test_app.filters.MyCustomJSFilter' in comp_settings.COMPRESS_FILTERS['js']

    # Test CSS Filter
    css_compressor = Compressor('css', content='body { color: black; }')
    # Use output() to trigger filter
    css_output = "\n".join(css_compressor.filter_input(forced=True))
    css_filtered = css_compressor.filter_output(css_output)
    
    print("CSS Output:", css_filtered)
    assert 'white' in css_filtered, "MyCustomCSSFilter was not executed!"

    # Test JS Filter
    js_compressor = Compressor('js', content='console.log("hello");')
    js_output = "\n".join(js_compressor.filter_input(forced=True))
    js_filtered = js_compressor.filter_output(js_output)
    
    print("JS Output:", js_filtered)
    assert 'alert' in js_filtered, "MyCustomJSFilter was not executed!"

    print("All tests passed successfully.")

if __name__ == '__main__':
    run_test()
