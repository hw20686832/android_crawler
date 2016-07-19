# coding:utf-8
from pymongo import MongoReplicaSetClient
from celery import Celery, group
from kombu import Exchange, Queue

import settings


db_vs = MongoReplicaSetClient(
    settings.MONGO_CONNECTION_STRING,
    replicaSet='android').android_appcenter_vs
db_vs_lite = MongoReplicaSetClient(
    settings.MONGO_CONNECTION_STRING_LITE,
    replicaSet='android').android_appcenter_lite


class Config(object):
    BROKER_URL = 'amqp://%s:%s@%s:%s/%s' % (
        settings.RABBITMQ_DBSYNC_BROKER_USER,
        settings.RABBITMQ_DBSYNC_BROKER_PASSWORD,
        settings.RABBITMQ_HOST,
        settings.RABBITMQ_PORT,
        settings.RABBITMQ_DBSYNC_BROKER_VHOST
    )
    CELERY_RESULT_BACKEND = 'amqp://%s:%s@%s:%s/%s' % (
        settings.RABBITMQ_DBSYNC_BROKER_USER,
        settings.RABBITMQ_DBSYNC_BROKER_PASSWORD,
        settings.RABBITMQ_HOST,
        settings.RABBITMQ_PORT,
        settings.RABBITMQ_DBSYNC_BACKEND_VHOST
    )
    CELERY_TASK_RESULT_EXPIRES = 3600
    CELERY_ACCEPT_CONTENT = ['pickle', ]

    update_exchange = Exchange('update', type='direct')
    CELERY_QUEUES = (
        Queue('vs', update_exchange, routing_key='worker.c_dbsync.vs'),
        Queue('lite', update_exchange, routing_key='worker.c_dbsync.lite'),
    )
    CELERY_DEFAULT_QUEUE = 'vs'
    CELERY_DEFAULT_EXCHANGE_TYPE = 'direct'
    CELERY_DEFAULT_ROUTING_KEY = 'worker.c_dbsync.vs'
    CELERY_ROUTES = {
        'worker.c_dbsync.vs': {'queue': 'vs'},
        'worker.c_dbsync.lite': {'queue': 'lite'},
    }

c = Celery()
c.config_from_object(Config)

default_regions = ['vs', 'lite']


@c.task
def vs(item):
    if item['lang'] == 'zh':
        item['is_deleted'] = True

    #if item.get('obbs') == 1:
    #    coll = 'full_game'
    #else:
    #    coll = 'AppBase'
    d = db_vs.AppBase.find_one({'appid': item['appid']})
    if d:
        if d.get('ignore_crawler') == 1:
            return item['appid']
        if 'search_order' in d:
            item['search_order'] = d['search_order']
        if str(d.get('app_status', 0)) != 0:
            del item['app_status']

        item['is_deleted'] = d['is_deleted']

        if d.get('source') == 'editor':
            del item['description']
    db_vs.AppBase.update({'appid': item['appid']}, {"$set": item}, upsert=True)
    return item['appid']


@c.task
def lite(item):
    if item['lang'] == 'zh':
        item['is_deleted'] = True

    if item.get('obbs') == 1:
        coll = 'full_game'
    else:
        coll = 'AppBase'
    d = db_vs_lite[coll].find_one({'appid': item['appid']})
    if d:
        if d.get('ignore_crawler') == 1:
            return item['appid']
        if 'search_order' in d:
            item['search_order'] = d['search_order']
        if str(d.get('app_status', 0)) != 0:
            del item['app_status']

        item['is_deleted'] = d['is_deleted']

        if d.get('source') == 'editor':
            del item['description']
    db_vs_lite[coll].update({'appid': item['appid']},
                            {"$set": item}, upsert=True)
    return item['appid']


def sync(item, *regions):
    if not regions:
        regions = default_regions
    return group(*[globals()[reg].s(item) for reg in regions])()
