# coding:utf-8
# code: ffe591d0-65b5-402d-99c5-5efdb2fc2882
import re

from lxml import html
from tornado.web import asynchronous
from tornado.gen import coroutine, Return
from tornado.escape import json_decode
from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPError

from .handlers import BaseHandler
from utils.commmon import db_execute


class Pull(BaseHandler):
    source = "mobisummer"
    list_url = "http://console.mobisummer.com/api/v1/get?code=ffe591d0-65b5-402d-99c5-5efdb2fc2882&platform=android&status=active"

    @asynchronous
    @db_execute
    @coroutine
    def get(self):
        cli = AsyncHTTPClient()
        response = yield cli.fetch(self.list_url)
        data = json_decode(response.body)

        result = []
        for offer in data['offers']:
            _allowed_download = 1
            _icon = ''

            mch = re.match("https://play\.google\.com/store/apps/details\?id=(.*)$",
                           offer['preview_link'].split('&')[0])
            if mch:
                _allowed_download = 2

                request = HTTPRequest(offer['preview_link'], validate_cert=False)
                try:
                    response = yield cli.fetch(request)
                except HTTPError as he:
                    self.log.error("Preview url request error: %s, [%s]" % (offer['preview_link'], str(he)))
                    continue
                root = html.fromstring(response.body)
                src = root.xpath("//div[@class='cover-container']/img[@class='cover-image']/@src")[0]
                _icon = src if src.startswith("http") else 'https:' + src

            for cty in offer['country'].split(','):
                item = {}
                item['allowed_download'] = _allowed_download
                item['appid'] = offer['pkgname']
                item['name'] = offer['offer_name']
                item['description'] = offer['description']
                item['category_id'] = 'TOOLS'
                item['rating'] = offer['store_rating']
                item['size'] = 'unknown'
                item['apk'] = offer['tracking_link']
                item['icon'] = _icon
                item['total_count'] = "100k+"
                item['screenshot'] = []
                item['price'] = offer['payout']
                item['source'] = 'mobisummer'
                item['preview_url'] = offer['preview_link']
                item['country'] = cty
                result.append(item)

        raise Return(result)


class Pulls(BaseHandler):
    source = "mobisummer"

    @asynchronous
    @db_execute
    @coroutine
    def get(self):
        offer_url = "http://console.mobisummer.com/api/v1/get?code=ffe591d0-65b5-402d-99c5-5efdb2fc2882&id=%s"
        offer_ids = [
            "12523", "12547", "16947", "12441", "16953",
            "16955", "16957", "15903", "16301", "16303",
            "16949", "16951", "2316", "16337", "16339",
            "16341", "16343", "2284", "12383", "12455",
            "16051", "16053", "16055", "16057", "16059",
            "16065", "16287"
        ]

        result = []
        cli = AsyncHTTPClient()
        for offer_id in offer_ids:
            response = yield cli.fetch(offer_url % offer_id)
            offer = json_decode(response.body)['offers'][0]
            if 'itunes.apple.com' in offer['preview_link']:
                continue
            _allowed_download = 1
            _icon = ''

            mch = re.match("https://play\.google\.com/store/apps/details\?id=(.*)$",
                           offer['preview_link'].split('&')[0])
            if mch:
                _allowed_download = 2

                request = HTTPRequest(offer['preview_link'], validate_cert=False)
                try:
                    response = yield cli.fetch(request)
                except HTTPError as he:
                    self.log.error("Preview url request error: %s, [%s]" % (offer['preview_link'], str(he)))
                    continue
                root = html.fromstring(response.body)
                src = root.xpath("//div[@class='cover-container']/img[@class='cover-image']/@src")[0]
                _icon = src if src.startswith("http") else 'https:' + src

            for cty in offer['country'].split(','):
                item = {}
                item['allowed_download'] = _allowed_download
                item['appid'] = offer['pkgname']
                item['name'] = offer['offer_name']
                item['description'] = offer['description']
                item['category_id'] = 'TOOLS'
                item['rating'] = offer['store_rating']
                item['size'] = 'unknown'
                item['apk'] = offer['tracking_link']
                item['icon'] = _icon
                item['total_count'] = "100k+"
                item['screenshot'] = []
                item['price'] = offer['payout']
                item['source'] = 'mobisummer'
                item['preview_url'] = offer['preview_link']
                item['country'] = cty
                result.append(item)

        raise Return(result)
