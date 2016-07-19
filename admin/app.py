# coding:utf-8
import os

import redis
from tornado.httpserver import HTTPServer
from tornado.ioloop import IOLoop
from tornado.web import Application
from motor import MotorReplicaSetClient
from boto.s3.connection import S3Connection

from core.base import Base
from .urls import handlers


class MyApplication(Application):
    def __init__(self, settings):
        config = dict(
            template_path=os.path.join(os.path.dirname(__file__),
                                       settings.TEMPLATE_ROOT),
            static_path=os.path.join(os.path.dirname(__file__),
                                     settings.STATIC_ROOT),
            cookie_secret="__E720175A1F2957AFD8EC0E7B51275EA7__",
            login_url='/login',
            autoescape=None,
            debug=settings.DEBUG
        )
        Application.__init__(self, handlers, **config)

        conn = S3Connection()
        self.bucket = conn.get_bucket(settings.APK_BUCKET)
        self.redis = redis.Redis(
            host=settings.REDIS_HOST,
            port=settings.REDIS_PORT,
            db=settings.REDIS_DB,
            password=settings.REDIS_PASS
        )

        self.db = MotorReplicaSetClient(
            settings.MONGO_CONNECTION_STRING,
            replicaSet='android'
        )[settings.MONGO_DB]

        self.engine = Base(settings)
        self.api = self.engine.login(async=True)


def run(config):
    http_server = HTTPServer(MyApplication(config))
    http_server.listen(port=config.PORT, address=config.HOST)

    IOLoop.instance().start()


if __name__ == '__main__':
    run()
