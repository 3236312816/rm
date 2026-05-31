import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
TEMPLATE_ROOT = os.path.join(BASE_DIR, 'templates')

DEBUG = os.getenv('TORNADO_DEBUG') == 'True'

PORT = os.getenv('PORT', 8080)

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'root': {
        'level': 'INFO',
        'handlers': ['console'],
        'propagate': True,
    },
    'formatters': {
        'verbose': {
            'format': '%(asctime)s %(levelname)s %(module)s %(lineno)d %(message)s'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'verbose'
        },
    },
    'loggers': {
        'tornado.general': {
            'handlers': ['console'],
            'propagate': True,
        },
    }
}
