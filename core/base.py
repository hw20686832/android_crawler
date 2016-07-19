#!/usr/bin/env python
# coding: utf-8
import random
from IPython.terminal.embed import InteractiveShellEmbed
from IPython.terminal.ipapp import load_default_config

import gevent
from gevent import monkey
monkey.patch_all()

import socket
from pprint import pprint

import netifaces
from gevent import greenlet
from gevent.pool import Pool
import redis
from pymongo import MongoReplicaSetClient

from utils import logger
from utils.topapp import touch_appannie
from core.googleplay import GooglePlayAPI
from core.apk_store import ApkStore


BANNER = """[Google] Google Play Unofficial API Interactive Shell
[Google] Successfully logged in using your Google account.
[Google] The variable 'api' holds the API object.
[Google] Feel free to use api?.
"""

real_create_conn = socket.create_connection


def list_ips():
    ifaces = netifaces.interfaces()
    ips = []
    for iface in ifaces:
        addr = netifaces.ifaddresses(iface)
        a = addr.get(netifaces.AF_INET)
        if a:
            if a[0]['netmask'] == '255.255.255.248' \
               and a[0]['addr'] != '66.90.93.62':
                ips.append(a[0]['addr'])

    return ips


def set_src_addr(*args, **kwargs):
    if len(args) > 0:
        address, timeout = args[0], args[1]
    elif len(kwargs) > 0:
        address = kwargs['address']
        timeout = kwargs['timeout']
    source_address = (random.choice(list_ips()), 0)
    return real_create_conn(address, timeout, source_address)

socket.create_connection = set_src_addr


class Adapter(greenlet.Greenlet):
    def __init__(self, engine):
        self.engine = engine
        self.log = engine.log
        self.db = engine.db

        super(Adapter, self).__init__()


class MaintainAdapter(Adapter):
    def _run(self):
        while True:
            for g in list(self.engine.detail_pool):
                if g.dead:
                    self.engine.detail_pool.discard(g)
                    self.log.warning(
                        "Restart a dead greenlet %s." % str(g))
            for i in xrange(self.engine.detail_pool.free_count()):
                self.engine.detail_pool.spawn(self.engine.run)

            gevent.sleep(3)


class Base(object):
    def __init__(self, config=None):
        self.config = config
        self.log = logger.getlog()
        self.redis = redis.Redis(
            host=self.config.REDIS_HOST,
            port=self.config.REDIS_PORT,
            db=self.config.REDIS_DB,
            password=self.config.REDIS_PASS
        )

        self.db = MongoReplicaSetClient(
            self.config.MONGO_CONNECTION_STRING,
            replicaSet='android'
        )[self.config.MONGO_DB]

        self.store = ApkStore(config)
        self.image_bucket = self.store.image_bucket
        self.apk_bucket = self.store.apk_bucket
        self.detail_pool = Pool(config.CONCURRENT_NUM)

        self.accounts = list(self.db.accounts.find(
            {'is_deleted': False}
        ))
        self.adapters = []
        self.registry(MaintainAdapter)

    def registry(self, adapter_cls):
        assert issubclass(adapter_cls, Adapter)
        self.adapters.append(adapter_cls)

    def _select_user(self, **kwargs):
        """Random choice an account object according to designated params.
        """
        def where(item):
            for k, v in kwargs.items():
                if item[k] != v:
                    return False

            return True

        return random.choice(filter(where, self.accounts))

    def login(self, uid=None, async=False):
        where = {}
        if uid:
            where = {'uid': uid}
        acct = self._select_user(**where)
        api = GooglePlayAPI(
            acct['device_id'],
            lang=self.config.LANG,
            settings=self.config,
            async=async,
            log=self.log
        )
        api.login(acct['uid'], acct['passwd'])
        self.log.info("Login user '%s' with android id %s" %
                      (acct['uid'], acct['device_id']))
        return api

    def shell(self, uid=None):
        api = self.login(uid)
        namespace = {"api": api, "settings": self.config,
                     "db": self.db, "redis": self.redis,
                     "apk_bucket": self.apk_bucket,
                     "image_bucket": self.image_bucket}
        shell = InteractiveShellEmbed(
            banner1=BANNER, user_ns=namespace,
            config=load_default_config())
        shell()
        print("bye.")

    def fetch(self, appid, uid=None):
        """
        Sync fetch, get detail and download apk file, then save to s3 and mongodb.
        """
        from worker.c_dbsync import sync

        self.log.debug("Loging into GooglePlay...")
        api = self.login(uid)
        self.log.debug("Fetching app detail...")
        detail = api.get_detail(appid)
        self.log.debug("Downloading apk file...")
        is_purchased = not detail['price'].lower() == 'free'
        data = api.download(appid, detail['version_code'],
                            detail['offer_type'], is_purchased)
        item = self.store.save(detail, data)
        self.log.debug("App info [appid: %s, version: %s, release time: %s]" %
                       (appid, item['version_name'],
                        item['release_time'].strftime("%Y-%m-%d")))
        del item["offer_type"]
        self.log.debug("Saving into database...")
        g = sync(item)
        if g:
            g.join()
            self.log.debug("OK.")
        else:
            self.log.debug("App ignored!")

    def detail(self, appid):
        api = self.login()
        detail = api.get_detail(appid)
        pprint(detail)

    def download(self, appid, dist=None):
        api = self.login()
        detail = api.details(appid)
        data = api.download(appid,
                            detail.docV2.details.appDetails.versionCode,
                            detail.docV2.offer[0].offerType)

        with open(dist or '%s.apk' % appid, 'w') as f:
            f.write(data['apk']['data'])

    def remove(self, *appids):
        for aid in appids:
            item = self.db.AppBase.find_one({"appid": aid})
            if item:
                self.db.AppBase.remove(item)
                self.image_bucket.delete_key(item['icon'])
                self.image_bucket.delete_keys(item['screenshot'])
                self.apk_bucket.delete_key(item['apk'])
                self.redis.hdel('app_record', aid)
                msg = "app {} delete complete.".format(aid)
            else:
                msg = "app {} not found.".format(aid)

            self.log.debug(msg)
            yield (aid, msg)

    def add(self, appids, force=False):
        n = 0
        for appid in appids:
            if force:
                self.redis.lpush("appids", appid)
            else:
                self.redis.rpush("appids", appid)
            n += 1

        return n

    def reschedule(self, ptype="free"):
        if ptype == 'free':
            if self.redis.llen('appids') == 0:
                for appid in self.redis.hkeys("app_record"):
                    self.redis.rpush('appids', appid)
        elif ptype == 'paid':
            from worker import c_getapk

            host = 'celery@c_getapk_update'
            ins = c_getapk.c.control.inspect(destination=[host, ])

            if not ins.active():
                for item in self.db.AppBase.find(
                        {'paid': 2, 'google_id': {'$exists': 1}}):
                    acct = self._select_user(item['google_id'])
                    c_getapk.download.apply_async(
                        [acct, item['appid']],
                        queue='update'
                    )
        elif ptype == 'hot':
            self.add(touch_appannie(), True)

    def prepare(self):
        """You can do something before crawler start.
        """
        pass

    def run(self):
        """need implement"""
        raise NotImplementedError()

    def start(self):
        self.prepare()
        for i in range(self.detail_pool.size):
            self.detail_pool.spawn(self.run)

        for adapter_cls in self.adapters:
            adapter = adapter_cls(self)
            adapter.start()

        self.detail_pool.join()
