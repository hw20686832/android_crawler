# coding:utf-8
import re
import time
import urllib

from lxml import html
from tornado.web import asynchronous
from tornado.gen import coroutine, Return
from tornado.escape import json_decode
from tornado.httpclient import AsyncHTTPClient, HTTPRequest, HTTPError

from .handlers import BaseHandler
from utils.commmon import db_execute


class API(object):
    def __init__(self):
        self.network_id = "mobisummer"
        self.api_key = "f6d8f065026ffcb7885c935aa6589530eb7c011fb15cb92d56b5f2607008c4ee"
        self.base_link = "https://api.hasoffers.com/Apiv3/json"

    def _urlencode(self, query):
        query_tuple = []
        for key, value in query.iteritems():
            if type(value) == list:
                for v in value:
                    query_tuple.append('='.join((urllib.quote(key), urllib.quote(v))))
            else:
                query_tuple.append('='.join((urllib.quote(key), urllib.quote(value))))

        query_string = "&".join(query_tuple)
        return query_string

    @coroutine
    def _get_request(self, method=None, kwargs=None, target='Affiliate_Offer'):
        params = {
            'NetworkId': self.network_id,
            'api_key': self.api_key,
            'Target': target,
            'Method': method
        }
        params.update(kwargs or {})
        request_url = '?'.join((self.base_link, self._urlencode(params)))
        cli = AsyncHTTPClient()
        response = yield cli.fetch(request_url)
        data = json_decode(response.body)
        result = data['response']['data']

        raise Return(result)

    @coroutine
    def get_list_by_type(self, type_name):
        rs = yield self._get_request('findByCreativeType',
                                     {'type': type_name})
        raise Return(rs)

    @coroutine
    def get_my_offers(self):
        rs = yield self._get_request('findMyApprovedOffers')
        raise Return(rs)

    @coroutine
    def get_offer_by_id(self, offer_id):
        rs = yield self._get_request('findById',
                                     {'id': offer_id})
        raise Return(rs)

    @coroutine
    def get_offerfiles(self):
        rs = yield self._get_request('findAll', target='Affiliate_OfferFile')
        raise Return(rs)

    @coroutine
    def get_country(self, offer_ids):
        rs = yield self._get_request('getTargetCountries',
                                     {'ids[]': offer_ids})
        raise Return(rs)

    @coroutine
    def get_tracking_link(self, offer_id):
        rs = yield self._get_request('generateTrackingLink',
                                     {'offer_id': offer_id})
        raise Return(rs)

    @coroutine
    def get_categories(self, offer_ids):
        rs = yield self._get_request('getCategories', {'ids[]': offer_ids})
        raise Return(rs)


class Pull(BaseHandler):
    source = "hasoffers"

    @asynchronous
    @db_execute
    @coroutine
    def get(self):
        cli = AsyncHTTPClient()

        api = API()
        datas = yield api.get_my_offers()
        time.sleep(10)
        countries = yield api.get_country(datas.keys())
        country_map = {cty['offer_id']: cty['countries'].keys() for cty in countries}

        result = []
        time.sleep(10)
        for offer_id, offer in datas.iteritems():
            data = offer['Offer']
            _appid = ''
            _allowed_download = 1
            _icon = ''
            if 'itunes.apple.com' in data['preview_url']:
                continue

            mch = re.match("https://play\.google\.com/store/apps/details\?id=(.*)$",
                           data['preview_url'].split('&')[0])
            if mch:
                _appid = mch.group(1)
                _allowed_download = 2

                request = HTTPRequest(data['preview_url'], validate_cert=False)
                try:
                    response = yield cli.fetch(request)
                except HTTPError as he:
                    self.log.error("Preview url request error: %s, [%s]" % (data['preview_url'], str(he)))
                    continue
                root = html.fromstring(response.body)
                src = root.xpath("//div[@class='cover-container']/img[@class='cover-image']/@src")[0]
                _icon = src if src.startswith("http") else 'https:' + src

            link_data = yield api.get_tracking_link(offer_id)
            if not link_data:
                self.log.error("Offer %s has errors. message: %s" % (offer_id, str(link_data)))
                continue

            for cty in country_map.get(offer_id, ''):
                item = {}
                item['appid'] = _appid
                item['preview_url'] = data['preview_url']
                item['name'] = data['name']
                item['icon'] = _icon
                item['description'] = data['description']
                item['allowed_download'] = _allowed_download
                item['apk'] = link_data['click_url']
                item['category_id'] = 'TOOLS'
                item['rating'] = '4'
                item['size'] = ''
                item['screenshot'] = []
                item['price'] = data['default_payout']
                item['source'] = 'hasoffers'
                item['country'] = cty
                result.append(item)
            time.sleep(10)

        raise Return(result)


class Pulls(BaseHandler):
    source = "hasoffers"

    @asynchronous
    @db_execute
    @coroutine
    def get(self):
        api = API()
        offer_ids = [
            "12523", "12547", "16947", "12441", "16953",
            "16955", "16957", "15903", "16301", "16303",
            "16949", "16951", "2316", "16337", "16339",
            "16341", "16343", "2284", "12383", "12455",
            "16051", "16053", "16055", "16057", "16059",
            "16065", "16287"
        ]

        time.sleep(10)
        countries = yield api.get_country(offer_ids)
        country_map = {cty['offer_id']: cty['countries'].keys() for cty in countries}

        result = []
        cli = AsyncHTTPClient()
        for offer_id in offer_ids:
            data = yield api.get_offer_by_id(offer_id)
            if type(data) is str:
                print data
            offer = data['Offer']
            if 'itunes.apple.com' in offer['preview_url']:
                continue
            _appid = ''
            _allowed_download = 1
            _icon = ''

            mch = re.match("https://play\.google\.com/store/apps/details\?id=(.*)$",
                           offer['preview_url'].split('&')[0])
            if mch:
                _appid = mch.group(1)
                _allowed_download = 2

                request = HTTPRequest(offer['preview_url'], validate_cert=False)
                try:
                    response = yield cli.fetch(request)
                except HTTPError as he:
                    self.log.error("Preview url request error: %s, [%s]" % (offer['preview_url'], str(he)))
                    continue
                root = html.fromstring(response.body)
                src = root.xpath("//div[@class='cover-container']/img[@class='cover-image']/@src")[0]
                _icon = src if src.startswith("http") else 'https:' + src

            """
            link_data = yield api.get_tracking_link(offer_id)
            if not link_data:
                self.log.error("Offer %s has errors. message: %s" % (offer_id, str(link_data)))
                continue
            """

            for cty in country_map.get(offer_id, ''):
                item = {}
                item['allowed_download'] = _allowed_download
                item['appid'] = _appid
                item['name'] = offer['name']
                item['description'] = offer['description']
                item['category_id'] = 'TOOLS'
                item['rating'] = '4.0'
                item['size'] = 'unknown'
                # item['apk'] = link_data['click_url']
                item['apk'] = "http://hasoffers.mobisummer.com/aff_c?offer_id=%s&aff_id=2710" % offer_id
                item['icon'] = _icon
                item['total_count'] = "100k+"
                item['screenshot'] = []
                item['price'] = offer['default_payout']
                item['source'] = 'hasoffers'
                item['preview_url'] = offer['preview_url']
                item['country'] = cty
                result.append(item)

            time.sleep(5)

        raise Return(result)
