# coding:utf-8
import socket
from hashlib import md5

from celery import Celery
from celery.task import current
from boto.s3.connection import S3Connection
from androguard.core.bytecodes import apk

import settings


class Config(object):
    BROKER_URL = 'amqp://%s:%s@%s:%s/%s' % (
        settings.RABBITMQ_DBSYNC_BROKER_USER,
        settings.RABBITMQ_DBSYNC_BROKER_PASSWORD,
        settings.RABBITMQ_HOST,
        settings.RABBITMQ_PORT,
        settings.RABBITMQ_UPLOAD_BROKER_VHOST
    )
    CELERY_RESULT_BACKEND = 'amqp://%s:%s@%s:%s/%s' % (
        settings.RABBITMQ_DBSYNC_BROKER_USER,
        settings.RABBITMQ_DBSYNC_BROKER_PASSWORD,
        settings.RABBITMQ_HOST,
        settings.RABBITMQ_PORT,
        settings.RABBITMQ_UPLOAD_BROKER_VHOST
    )
    CELERY_TASK_RESULT_EXPIRES = 3600
    CELERY_ACCEPT_CONTENT = ['pickle', ]
    CELERY_TASK_SERIALIZER = 'pickle'


c = Celery()
c.config_from_object(Config)


@c.task
def upload(bucket_name='androidpackage', filename=None, body=None):
    try:
        meta = {
            "version_name": None,
            "version_code": None,
            "min_sdk_version": None,
            "package": None,
            "md5": md5(body).hexdigest()
        }
        try:
            pkg = apk.APK(body, raw=True)
            meta["version_name"] = pkg.get_androidversion_name()
            meta["min_sdk_version"] = int(pkg.get_min_sdk_version())
            meta["version_code"] = int(pkg.get_androidversion_code())
            meta["package"] = pkg.get_package()
            meta["valid"] = 1
        except:
            meta["valid"] = 0

        conn = S3Connection()
        bucket = conn.get_bucket(bucket_name)
        if filename:
            app_key = filename
        else:
            if meta['valid']:
                app_key = "upload/%(package)s__%(version_code)d.apk" % meta
            else:
                app_key = "upload/novalid/%s.apk" % meta['md5']

        key = bucket.new_key(app_key)
        for k, v in meta.iteritems():
            if v:
                key.set_metadata(k, v)
        key.set_contents_from_string(body)
        key.close()
    except socket.error, e:
        current.retry(exc=e)

    return meta
