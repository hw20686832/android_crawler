# coding:utf-8
from tornado.web import asynchronous
from tornado.gen import coroutine, Return
from tornado.escape import json_decode
from tornado.httpclient import AsyncHTTPClient

from .handlers import BaseHandler
from utils.commmon import db_execute


class Pull(BaseHandler):
    source = "mobvista"
    MOBVISTA_URL = "http://3s.mobvista.com/v3.php?key=b96b7ec4353f61aa6ffbc1e2084ec5b6&platform=android"

    @asynchronous
    @db_execute
    @coroutine
    def get(self):
        cli = AsyncHTTPClient()
        response = yield cli.fetch(self.MOBVISTA_URL)
        data = json_decode(response.body)

        result = []
        for offer in data['offers']:
            if not offer['link_type'] in ('gp', 'apk'):
                continue

            for cty in offer['geo'].upper().split(','):
                item = {}
                item['appid'] = offer['package_name']
                item['name'] = offer['app_name']
                item['description'] = offer['app_desc']
                item['category_id'] = offer['app_category']
                item['rating'] = offer['app_rate']
                item['size'] = offer['app_size']
                item['apk'] = offer['tracking_link']
                item['icon'] = offer['icon_link']
                item['total_count'] = "200k+"
                item['screenshot'] = []
                item['price'] = offer['price']
                item['source'] = 'mobvista'

                if offer['link_type'] == 'gp':
                    item['allowed_download'] = 2
                else:
                    item['allowed_download'] = 1

                item['country'] = cty
                result.append(item)

        raise Return(result)
