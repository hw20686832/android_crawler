# coding:utf-8
import socket

from celery import Celery
from celery.utils.log import get_task_logger
from kombu import Exchange, Queue, serialization
serialization.registry._decoders.pop("application/x-python-serialize")

from core.googleplay import GooglePlayAPI
from core.apk_store import ApkStore
from worker.c_dbsync import sync
import settings


store = ApkStore(settings)


class Config(object):
    BROKER_URL = 'amqp://%s:%s@%s:%s/%s' % (
        settings.RABBITMQ_GETAPK_BROKER_USER,
        settings.RABBITMQ_GETAPK_BROKER_PASSWORD,
        settings.RABBITMQ_HOST,
        settings.RABBITMQ_PORT,
        settings.RABBITMQ_GETAPK_BROKER_VHOST
    )
    CELERY_RESULT_BACKEND = 'amqp://%s:%s@%s:%s/%s' % (
        settings.RABBITMQ_GETAPK_BROKER_USER,
        settings.RABBITMQ_GETAPK_BROKER_PASSWORD,
        settings.RABBITMQ_HOST,
        settings.RABBITMQ_PORT,
        settings.RABBITMQ_GETAPK_BROKER_VHOST
    )
    CELERY_TASK_RESULT_EXPIRES = 3600
    CELERY_ACCEPT_CONTENT = ['json', 'pickle']
    CELERY_TASK_SERIALIZER = 'json'
    CELERY_RESULT_SERIALIZER = 'json'

    update_exchange = Exchange('paid', type='direct')
    CELERY_QUEUES = (
        Queue('new', update_exchange),
        Queue('update', update_exchange)
    )

    CELERY_DEFAULT_QUEUE = 'new'
    CELERY_DEFAULT_EXCHANGE_TYPE = 'direct'


c = Celery()
c.config_from_object(Config)
logger = get_task_logger(__name__)


@c.task(bind=True)
def download(self, acct, appid):
    try:
        self.update_state(state='PROGRESS',
                          meta={'msg': 'Loging into GooglePlay...'})
        api = GooglePlayAPI(acct['device_id'], lang=acct.get('lang', 'en_US'),
                            settings=settings, log=logger)
        api.login(acct['uid'], acct['passwd'])
        self.update_state(state='PROGRESS',
                          meta={'msg': 'Fetching app detail...'})
        item = api.get_detail(appid)
        is_purchased = not item['price'].lower() == 'free'
        if store.redis.hget('app_record', appid) != str(item['version_code']):
            self.update_state(state='PROGRESS',
                              meta={'msg': 'Downloading apk file...'})
            data = api.download(
                appid,
                item['version_code'], item['offer_type'],
                is_purchased=is_purchased
            )

            self.update_state(state='PROGRESS',
                              meta={'msg': 'Uploading all files to aws...'})
            item = store.save(item, data)
            item['paid'] = 2
            self.update_state(state='PROGRESS',
                              meta={'msg': 'Saving into database...'})
            g = sync(item)
            if g:
                g.join()
                store.redis.hset('app_record', appid, item['version_code'])
        else:
            self.update_state(state='PROGRESS',
                              meta={'msg': 'This app has been up to date...'})
    except socket.error, e:
        self.update_state(state='PROGRESS',
                          meta={'msg': 'Have some error happened...'})
        self.retry(exc=e)

    return item['appid']


if __name__ == "__main__":
    from celery.bin import worker

    worker = worker.worker(app=c)
    options = {
        'concurrency': 4,
        'loglevel': 'INFO',
        'traceback': True,
    }
    worker.run(**options)
