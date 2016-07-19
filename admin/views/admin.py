# coding:utf-8
import re
import time
import json
import datetime
from functools import partial

import kombu.five
from bson import ObjectId
from tornado.gen import coroutine
from tornado.ioloop import IOLoop
from tornado.escape import json_encode
from tornado.web import asynchronous, authenticated
from tornalet import tornalet

from .handlers import BaseHandler
from worker import async_task, c_getapk, c_delete, c_upproxy


headers = {
    "Accept:text/html": "application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip,deflate,sdch",
    "Accept-Language": "zh-CN,zh;q=0.8,en;q=0.6,zh-TW;q=0.4",
    "Cache-Control": "max-age=0",
    "Connection": "keep-alive",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/36.0.1985.125 Chrome/36.0.1985.125 Safari/537.36"
}


class LoginHandler(BaseHandler):
    def get(self):
        self.render("login.html")

    @asynchronous
    @coroutine
    def post(self):
        email = self.get_argument("email")
        passwd = self.get_argument("passwd")
        next_url = self.get_argument("next", "/")
        remember = bool(self.get_argument("remember", False))
        auth = yield self.db.admin_user.find_one(
            {'email': email, 'passwd': passwd}
        )
        if auth:
            del auth['_id']
            self.set_current_user(auth, remember)

        self.redirect(next_url)

    def set_current_user(self, user, remember=False):
        if user:
            expire_params = {}
            if not remember:
                expire_params['expires_days'] = None
            self.set_secure_cookie("user", json_encode(user), **expire_params)
        else:
            self.clear_cookie("user")


class LogoutHandler(BaseHandler):
    @authenticated
    def get(self):
        self.clear_cookie("user")
        self.redirect('/')


class IndexHandler(BaseHandler):
    @authenticated
    def get(self):
        self.render("crawler.html")


class AppHandler(BaseHandler):
    @authenticated
    @asynchronous
    @coroutine
    def get(self):
        default_date = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
        date = self.get_argument("d", default_date)
        key = 'log:full{}:{}'

        all_appids = set()
        for x in ('new', 'update'):
            all_appids |= self.redis.smembers(key.format(x, date))

        items = self.db.AppBase.find(
            {'appid': {'$in': list(all_appids)}},
            {
                'appid': 1, 'version_name': 1,
                'group': 1, 'tag': 1, '_id': 0
            }
        )

        data = yield items.to_list(None)

        missing_key = key.format('update:missing', date)
        missing = self.redis.smembers(missing_key)
        missing_data = [
            {
                'appid': appid, 'version_name': '',
                'group': '', 'tag': 'missing'
            } for appid in missing
        ]

        data.extend(missing_data)
        result = []
        for d in data:
            d['DT_RowId'] = d['appid']
            #d['DT_RowData'] = {'dtype': d.get('tag', 'updated')}
            if 'tag' not in d:
                d['tag'] = 'missing'

            if d['tag'] == 'missing':
                d['download'] = ''
            else:
                d['download'] = '<a class="btn btn-info btn-mi" href="/download?id=%s" target="_blank" title="Download APK"><i class="glyphicon glyphicon-download"></i> Download</a>' % d['appid']
            result.append(d)

        results = {
            'data': result,
            'recordsTotal': len(data),
            'recordsFiltered': len(data)
        }
        self.render_json(results)


class DownloadHandler(BaseHandler):
    @authenticated
    @asynchronous
    @coroutine
    def get(self):
        appid = self.get_argument("id")
        item = yield self.db.AppBase.find_one({'appid': appid})
        url = 'http://ad-dl.appvv.com/' + item['apk']
        self.redirect(url)


class PurchaseHandler(BaseHandler):
    @authenticated
    def get(self):
        self.render("purchase.html")


class ProfileHandler(BaseHandler):
    @authenticated
    @asynchronous
    @coroutine
    def get(self):
        cursor = self.db.accounts.find(
            {'is_deleted': False, 'account_type': 2}
        )
        result = yield cursor.to_list(None)
        self.render_json(result)


class ScheduleHandler(BaseHandler):
    @authenticated
    @asynchronous
    @coroutine
    def post(self):
        appids = self.get_argument('ids')
        appid_list = appids.split(',')
        google_id = self.get_argument('config')
        acct = yield self.db.accounts.find_one({'uid': google_id})
        del acct['_id']

        result = {'data': []}
        for appid in appid_list:
            rs = c_getapk.download.apply_async([acct, appid], queue='new')
            self.redis.zrem('purchse_ready', appid)
            result['data'].append(rs.task_id)

        self.render_json(result)


class DownloadQueueHandler(BaseHandler):
    @authenticated
    def get(self):
        ins = c_getapk.c.control.inspect(destination=['celery@c_getapk_new', ])

        actives = ins.active()
        reserveds = ins.reserved()

        active_data = []
        for host, datas in actives.items():
            active_data.extend(datas)

        active_data.sort(key=lambda x: x['time_start'])

        for host, reserved in reserveds.items():
            active_data.extend(reserved)

        result = []
        for data in active_data:
            item = {}
            acct, appid = eval(data['args'])
            start = ''
            item['uid'] = acct['uid']
            item['appid'] = appid
            if data['time_start']:
                start = datetime.datetime.fromtimestamp(time.time() - (kombu.five.monotonic() - data['time_start'])).strftime("%m-%d %H:%M:%S")
            item['start_time'] = start
            item['status'] = u'waiting' if data['acknowledged'] else u'downloading'
            result.append(item)

        result = {
            'data': result, 'recordsFiltered': len(result),
            'recordsTotal': len(result)
        }

        self.render_json(result)


class ReadyListHandler(BaseHandler):
    @authenticated
    @tornalet
    def get(self):
        page_size = self.get_argument("length", 30)
        draw = self.get_argument('draw', 1)
        start = self.get_argument("start", 0)
        total = self.redis.zcard('purchse_ready')
        data = self.redis.zrevrange('purchse_ready', int(start),
                                    int(start)+int(page_size), withscores=True)

        items = []
        if data:
            result = self.api.bulkDetails([_id for _id, _ in data])
            for entry, (appid, create_time) in zip(result.entry, data):
                item = {'appid': appid, 'DT_RowId': appid}
                try:
                    item['price'] = entry.doc.offer[0].formattedAmount
                except:
                    item['price'] = '-'

                item['create_time'] = datetime.datetime.fromtimestamp(create_time).strftime("%m-%d %H:%M:%S")
                items.append(item)

        result = {
            'draw': draw, 'recordsFiltered': total,
            'recordsTotal': total, 'data': items
        }

        self.render_json(result)

    @authenticated
    def post(self):
        result = {'data': []}
        for k in self.request.arguments:
            if '[appid]' in k:
                item = {
                    'appid': self.get_argument(k),
                    'create_time': time.time()
                }

                self.redis.zadd('purchse_ready', item['appid'], item['create_time'])
                item['DT_RowId'] = item['appid']
                result['data'].append(item)

        self.render_json(result)

    @authenticated
    def delete(self):
        _ids = self.get_argument('id')
        for appid in _ids.split(','):
            self.redis.zrem('purchse_ready', appid)

        self.render_json({'data': []})


class PaidListHandler(BaseHandler):
    @authenticated
    @asynchronous
    @coroutine
    def get(self):
        page_size = self.get_argument("length", 30)
        draw = self.get_argument('draw', 1)
        start = self.get_argument("start", 0)
        searching = self.get_argument("search[value]", False)
        where = {'paid': 2, 'google_id': {'$exists': 1}}
        cursor = self.db.AppBase.find(where)
        total = yield cursor.count()

        filter_total = None
        if searching:
            where['appid'] = {'$regex': r'.*%s.*' % re.escape(searching)}
            cursor = self.db.AppBase.find(where)
            filter_total = yield cursor.count()

        cursor.skip(int(start)).limit(int(page_size)).sort('create_time', -1)

        data = []
        while (yield cursor.fetch_next):
            item = cursor.next_object()

            rs = {}
            rs['uid'] = item.get('google_id')
            rs['appid'] = item['appid']
            rs['name'] = item['name']
            rs['price'] = item['price']
            try:
                rs['create_time'] = item.get('update_time', item['create_time']).strftime("%Y-%m-%d %H:%M:%S")
            except:
                rs['create_time'] = '---'

            data.append(rs)

        result = {
            'draw': draw,
            'recordsFiltered': filter_total or total,
            'recordsTotal': total,
            'data': data
        }

        self.render_json(result)


class CleanHandler(BaseHandler):
    @authenticated
    @asynchronous
    @coroutine
    def post(self):
        appids = self.get_argument('appids')
        appid_list = appids.split(',')

        result = yield async_task(c_delete.delete, args=appid_list)
        self.render_json(result.result)


class UploadHandler(BaseHandler):
    @authenticated
    @asynchronous
    @coroutine
    def post(self):
        self.set_header('Access-Control-Allow-Origin', '*')
        self.set_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.set_header('Access-Control-Max-Age', 1000)
        self.set_header('Access-Control-Allow-Headers', '*')

        bucket = self.get_argument('bucket', 'andoirdpackage')
        custom_name = self.get_argument('custom_name', None)
        files = self.request.files.get('files')

        result = []
        for filedata in files:
            params = {'bucket_name': bucket, 'body': filedata['body']}
            if custom_name:
                params['filename'] = "air/%s" % filedata['filename']
                rs = yield async_task(c_upproxy.upload, kwargs=params)
            result.append(rs.result)

        self.render_json(result)


class AccountPageHandler(BaseHandler):
    @authenticated
    def get(self):
        self.render("account.html")


class AccountHandler(BaseHandler):
    @authenticated
    @asynchronous
    @coroutine
    def get(self):
        page_size = self.get_argument("length", 20)
        draw = self.get_argument('draw', 1)
        start = self.get_argument("start", 0)

        cursor = self.db.accounts.find()
        total = yield cursor.count()
        cursor.skip(int(start)).limit(int(page_size)).sort('uid')

        items = []
        while (yield cursor.fetch_next):
            item = cursor.next_object()
            item['DT_RowId'] = item['_id']
            items.append(item)

        result = {
            'draw': draw,
            'recordsFiltered': total,
            'recordsTotal': total,
            'data': items
        }

        self.render_json(result)

    @authenticated
    @asynchronous
    @coroutine
    def post(self):
        acct = {
            'uid': self.get_argument('data[0][uid]'),
            'passwd': self.get_argument('data[0][passwd]'),
            'device_id': self.get_argument('data[0][device_id]'),
            'account_type': int(self.get_argument('data[0][account_type]', 1)),
            'lang': self.get_argument('data[0][lang]', 'en_US'),
            'system_version': self.get_argument('data[0][system_version]', '4.0'),
            'is_deleted': bool(int(self.get_argument('data[0][is_deleted]', 0)))
        }
        _id = yield self.db.accounts.insert(acct)
        acct['DT_RowId'] = _id
        result = {'data': [acct, ]}
        self.render_json(result)

    @authenticated
    @asynchronous
    @coroutine
    def put(self):
        _id = self.get_argument('id')
        acct = {
            'uid': self.get_argument('data[%s][uid]' % _id),
            'passwd': self.get_argument('data[%s][passwd]' % _id),
            'device_id': self.get_argument('data[%s][device_id]' % _id),
            'account_type': int(self.get_argument('data[%s][account_type]' % _id, 1)),
            'lang': self.get_argument('data[%s][lang]' % _id, 'en_US'),
            'system_version': self.get_argument('data[%s][system_version]' % _id, '4.0'),
            'is_deleted': bool(int(self.get_argument('data[%s][is_deleted]' % _id, 0)))
        }
        yield self.db.accounts.update(
            {"_id": ObjectId(_id)},
            {"$set": acct}
        )

        acct['DT_RowId'] = _id
        result = {'data': [acct, ]}
        self.render_json(result)

    @authenticated
    @asynchronous
    @coroutine
    def delete(self):
        _ids = self.get_argument('id')
        ids_obj = [ObjectId(_id) for _id in _ids.split(',')]

        yield self.db.accounts.remove({'_id': {'$in': ids_obj}})
        self.render_json({'data': []})


class BlackListPageHandler(BaseHandler):
    @authenticated
    def get(self):
        self.render("blacklist.html")


class BlackListHandler(BaseHandler):
    @authenticated
    @asynchronous
    @coroutine
    def get(self):
        page_size = self.get_argument("length", 20)
        draw = self.get_argument('draw', 1)
        start = self.get_argument("start", 0)

        cursor = self.db.forbidden_app.find()
        total = yield cursor.count()
        cursor.skip(int(start)).limit(int(page_size)).sort('create_time', -1)

        items = []
        while (yield cursor.fetch_next):
            item = cursor.next_object()
            item['DT_RowId'] = item['_id']
            items.append(item)

        result = {
            'draw': draw,
            'recordsFiltered': total,
            'recordsTotal': total,
            'data': items
        }

        self.render_json(result)

    @authenticated
    @asynchronous
    @coroutine
    def post(self):
        result = {'data': []}
        for k in self.request.arguments:
            if '[appid]' in k:
                item = {
                    'appid': self.get_argument(k),
                    'create_time': datetime.datetime.now()
                }

                _id = yield self.db.forbidden_app.insert(item)
                item['DT_RowId'] = _id
                result['data'].append(item)

        self.render_json(result)

    @authenticated
    @asynchronous
    @coroutine
    def put(self):
        _id = self.get_argument('id')
        item = {
            'appid': self.get_argument('data[%s][appid]' % _id),
        }
        yield self.db.forbidden_app.update(
            {"_id": ObjectId(_id)},
            {"$set": item}
        )

        item['DT_RowId'] = _id
        result = {'data': [item, ]}
        self.render_json(result)

    @authenticated
    @asynchronous
    @coroutine
    def delete(self):
        _ids = self.get_argument('id')
        yield self.db.forbidden_app.remove(
            {'_id': {
                '$in': [ObjectId(_id) for _id in _ids.split(',')]
            }}
        )
        self.render_json({'data': []})


class FetchHandler(BaseHandler):
    @asynchronous
    def post(self):
        appid = self.get_argument('id')
        google_id = self.get_argument('gid')
        self.db.accounts.find_one({'uid': google_id}, {'_id': 0},
                                  callback=partial(self.on_find, appid))

    @asynchronous
    def on_find(self, appid, result, error):
        wtask = c_getapk.download.apply_async([result, appid], queue='new')
        self.on_progress(wtask)

    @asynchronous
    def on_progress(self, task, status=None):
        current_status = task.result
        if current_status != status:
            if type(current_status) is dict:
                self.write("%s\n" % current_status['msg'])
                self.flush()

        if not task.successful():
            IOLoop.current().add_callback(self.on_progress,
                                          task, current_status)
        else:
            self.finish()
