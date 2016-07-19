# coding:utf-8
import json
import random
import socket
import datetime
import traceback

import gevent

from core.base import Base, Adapter
from worker.c_dbsync import sync


class AccountAdapter(Adapter):
    def _run(self):
        while True:
            accounts = list(self.db.accounts.find(
                {'is_deleted': False, 'account_type': 1}
            ))
            self.engine.accounts = accounts
            self.log.debug("All google account refreshed.")
            gevent.sleep(60)


class ForbiddenAdapter(Adapter):
    def _run(self):
        while True:
            items = self.db.forbidden_app.find()
            self.engine.ignore_package = set(item['appid'] for item in items)
            self.log.debug("All forbidden app list refreshed.")
            gevent.sleep(60 * 10)


class Detailer(Base):
    def prepare(self):
        self.registry(AccountAdapter)
        self.registry(ForbiddenAdapter)

    def run(self):
        api = self.login()
        num = 0
        while True:
            if num >= 50:
                api = self.login()
                self.prepare()
                num = 0
            if self.redis.llen("download_free") > 100000:
                gevent.sleep(30)
                continue

            appids = set()
            while len(appids) <= 300:
                appid = self.redis.lpop("appids")
                if appid:
                    # Ignore forbidden package
                    if appid not in self.ignore_package:
                        appids.add(appid)
                else:
                    break

            if not appids:
                gevent.sleep(random.randint(0, 9))
            else:
                for item in api.bulk_detail(*appids):
                    if 'notfound' in item:
                        continue
                    self.redis.rpush('download_free', json.dumps(item))
                    self.log.debug("APK fetched into download %s" % item['appid'])

                num += 1
            gevent.sleep(random.random() * self.config.DOWNLOAD_DELAY)


class Downloader(Base):
    def prepare(self):
        self.registry(AccountAdapter)

    def run(self):
        api = self.login()
        num = 0
        while True:
            if num >= 50:
                api = self.login()
                num = 0
            app = self.redis.lpop("download_free")
            if not app:
                gevent.sleep(3)
                continue

            item = json.loads(app)
            # apk download
            try:
                result = api.download(item["appid"],
                                      int(item["version_code"]),
                                      int(item["offer_type"]))
            except:
                self.log.error(traceback.format_exc())
                self.log.error(
                    "app download error with id %s, ignore!" % item['appid'])

                num += 2
                continue

            try:
                item = self.store.save(item, result)
            except socket.error:
                self.redis.rpush('download_free', app)
                continue
            except Exception:
                self.log.error("App %s error on save." % item['appid'])
                raise
            if item['tag'] == 'new':
                #item['app_status'] = -3
                item['create_time'] = datetime.datetime.now()
                _key = 'log:fullnew:%s' % datetime.datetime.now().strftime('%Y-%m-%d')
                self.redis.sadd(_key, item['appid'])
                self.redis.expire(_key, 3600 * 24 * 30)
            else:
                item['update_time'] = datetime.datetime.now()
                _key = 'log:fullupdate:%s' % datetime.datetime.now().strftime('%Y-%m-%d')
                self.redis.sadd(_key, item['appid'])
                self.redis.expire(_key, 3600 * 24 * 30)

            #item['release_time'] = datetime.datetime.strptime(item['release_time'], '%b %d, %Y')
            del item["offer_type"]
            # save item to mongo
            #self.db.AppBase.update({'appid': item["appid"]}, item, upsert=True)
            sync(item)
            # save fingerprint to redis for dupefilter
            self.redis.hset("app_record", item['appid'], str(item['version_code']))
            self.log.debug("apk %s version: %s downloaded" %
                           (item['appid'], item['version_name']))
            num += 1

            gevent.sleep(random.random() * self.config.DOWNLOAD_DELAY)
