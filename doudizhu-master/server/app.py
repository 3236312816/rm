import asyncio
import logging.config

import tornado.web
import tornado.websocket

from api.game.views import SocketHandler
from config import DEBUG, LOGGING, PORT, TEMPLATE_ROOT, STATIC_ROOT, STATIC_URL

logging.config.dictConfig(LOGGING)


class MainHandler(tornado.web.RequestHandler):
    def get(self):
        self.render('poker.html')


class Application(tornado.web.Application):
    def __init__(self):
        settings = {
            'debug': DEBUG,
            'gzip': False,
            'autoescape': 'xhtml_escape',
            'template_path': TEMPLATE_ROOT,
            'static_path': STATIC_ROOT,
            'static_url_prefix': STATIC_URL,
        }

        url_patterns = [
            ('/', MainHandler),
            ('/ws', SocketHandler),
        ]
        super().__init__(url_patterns, **settings)


async def main():
    app = Application()
    app.listen(PORT, '0.0.0.0')
    logging.info(f'Server started at http://0.0.0.0:{PORT}')
    await asyncio.Event().wait()


if __name__ == '__main__':
    asyncio.run(main())
