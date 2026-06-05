import os
import django
from django.conf import settings

settings.configure(
    INSTALLED_APPS=[
        'compressor',
    ],
    COMPRESS_FILTERS={
        'css': ['custom.css.Filter'],
        'js': []
    }
)
django.setup()

from compressor.conf import settings as comp_settings
print("COMPRESS_FILTERS after setup:", comp_settings.COMPRESS_FILTERS)
