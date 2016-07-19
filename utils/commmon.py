# coding:utf-8
import json
import datetime

from bson import ObjectId
from tornado.gen import coroutine


def db_execute(func):
    @coroutine
    def _wrapper(self):
        rs = []
        data = yield func(self)
        if len(data) > 0:
            yield self.db.ad_pool.remove({'source': self.source})
            rs = yield self.db.ad_pool.insert(data)
            self.log.debug("%s: %d offers saved." % (self.source, len(data)))
        self.render_json(str(rs))

    return _wrapper


class MongoItemEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.datetime):
            return obj.strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(obj, ObjectId):
            return str(obj)
        # Let the base class default method raise the TypeError
        return json.JSONEncoder.default(self, obj)
