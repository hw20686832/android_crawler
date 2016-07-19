# coding:utf-8
import socket

import redis
from celery import Celery

import settings


class Config(object):
    BROKER_URL = 'amqp://%s:%s@%s:%s/%s' % (
        settings.RABBITMQ_DELETE_BROKER_USER,
        settings.RABBITMQ_DELETE_BROKER_PASSWORD,
        settings.RABBITMQ_HOST,
        settings.RABBITMQ_PORT,
        settings.RABBITMQ_DELETE_BROKER_VHOST
    )

    CELERY_RESULT_BACKEND = 'redis://:%s@%s:%s/%s' % (
        settings.REDIS_PASS,
        settings.REDIS_HOST,
        settings.REDIS_PORT,
        settings.REDIS_DB
    )
    CELERY_TASK_RESULT_EXPIRES = 3600 * 24 * 30
    CELERY_ACCEPT_CONTENT = ['json', ]
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'


c = Celery()
c.config_from_object(Config)

rd = redis.Redis(
    host=settings.REDIS_HOST,
    port=settings.REDIS_PORT,
    password=settings.REDIS_PASS,
    db=settings.REDIS_DB
)


@c.task(bind=True)
def delete(self, *appids):
    from core.base import Base

    result = []
    try:
        engine = Base(settings)
        for rs in engine.remove(*appids):
            if not self.request.called_directly:
                self.update_state(
                    state='PROGRESS',
                    meta={'current': rs}
                )
            result.append(rs)
            rd.hdel('app_record', rs[0])
    except socket.error, e:
        raise self.retry(exc=e)

    return result


if __name__ == "__main__":
    from celery.bin import worker

    worker = worker.worker(app=c)
    options = {
        'concurrency': 4,
        'loglevel': 'INFO',
        'traceback': True,
    }
    worker.run(**options)
