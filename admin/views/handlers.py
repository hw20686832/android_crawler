# coding:utf-8
import json
import traceback

from tornado.web import RequestHandler
from tornado.escape import json_encode, json_decode

from utils.commmon import MongoItemEncoder


class BaseHandler(RequestHandler):
    @property
    def db(self):
        return self.application.db

    @property
    def bucket(self):
        return self.application.bucket

    @property
    def redis(self):
        return self.application.redis

    @property
    def log(self):
        return self.application.log

    @property
    def api(self):
        return self.application.api

    def get_current_user(self):
        user_json = self.get_secure_cookie("user")
        if user_json:
            return json_decode(user_json)

    def render_json(self, obj):
        """Auto render python object to json string."""
        self.set_header("Content-Type", "application/json; charset=UFT-8")
        self.write(json.dumps(obj, indent=4,
                              sort_keys=True, cls=MongoItemEncoder))

    def __finish(self, chunk=None):
        """Only for restful api.
        Set global content type to json.
        """
        self.set_header("Content-Type", "application/json; charset=UFT-8")
        super(BaseHandler, self).finish(chunk)

    def write_error(self, status_code, **kwargs):
        """Override to implement custom error pages.
        Only support restful api.
        """
        try:
            result = {'result': {'success': False, 'error': ''}}
            exc_info = kwargs.pop('exc_info')
            e = exc_info[1]

            self.clear()
            self.set_status(status_code)
            result['result']['error'] = str(e)
            self.finish(json_encode(result))
        except Exception:
            self.log.error(traceback.format_exc())
            return super(RequestHandler, self).write_error(status_code, **kwargs)
