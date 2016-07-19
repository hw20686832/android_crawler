#!/usr/bin/env python
# coding:utf-8
import re
import urllib
import zipfile
import traceback

import redis
import humanize
import requests
from tornado.httpclient import AsyncHTTPClient
from tornalet import asyncify
from requests.adapters import HTTPAdapter
#from requests.packages.urllib3.poolmanager import PoolManager
from pyquery import PyQuery as _Q

from google.protobuf import descriptor, text_format
from google.protobuf.internal.containers import RepeatedCompositeFieldContainer
from google.protobuf.message import Message
from guess_language import guess_language

import googleplay_pb2
from utils.tools import remove_downloads, strCount_to_intCount
from category import GROUP_MAP, CATEGORY_MAP

# To disable warnings in requests' vendored urllib3
try:
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except:
    pass


class LoginError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class RequestError(Exception):
    def __init__(self, value):
        self.value = value

    def __str__(self):
        return repr(self.value)


class AppNotFoundError(Exception):
    def __init__(self, value=''):
        self.value = "App %s not found" % str(value)

    def __str__(self):
        return repr(self.value)

#class MyAdapter(HTTPAdapter):
#    def init_poolmanager(self, connections, maxsize, block=False):
#        self.poolmanager = PoolManager(num_pools=connections,
#                                       maxsize=maxsize,
#                                       block=block,
#                                       ssl_version=ssl.PROTOCOL_TLSv1)


class AsyncHTTPAdapter(HTTPAdapter):
    def send(self, request, stream=False, timeout=None, verify=True,
             cert=None, proxies=None):
        http_client = AsyncHTTPClient()

        resp = asyncify(http_client.fetch)(request=request.url,
                                           method=request.method,
                                           body=request.body,
                                           headers=request.headers)
        resp.reason = 'Unknown'
        resp.content = resp.body
        r = self.build_response(request, resp)

        r.status_code = resp.code
        r._content = resp.content
        return r


class GooglePlayAPI(object):
    """Google Play Unofficial API Class

    Usual APIs methods are login(), search(), details(), bulkDetails(),
    download(), browse(), reviews() and list().

    toStr() can be used to pretty print the result (protobuf object) of the
    previous methods.

    toDict() converts the result into a dict, for easier introspection."""

    SERVICE = "androidmarket"
    URL_LOGIN = "https://android.clients.google.com/auth"
    # "https://www.google.com/accounts/ClientLogin"
    DETAIL_URL = "https://play.google.com/store/apps/details?id=%s"
    ACCOUNT_TYPE_GOOGLE = "GOOGLE"
    ACCOUNT_TYPE_HOSTED = "HOSTED"
    ACCOUNT_TYPE_HOSTED_OR_GOOGLE = "HOSTED_OR_GOOGLE"
    authSubToken = None

    def __init__(self, androidId=None, lang=None, settings=None, debug=False, async=False, log=None):
        # you must use a device-associated androidId value
        self.preFetch = {}
        if lang is None:
            lang = "en_US"
        self.lang = lang
        self.settings = settings
        self.androidId = androidId
        self.email = None
        self.debug = debug
        self.log = log

        self.redis = redis.Redis(host=self.settings.REDIS_HOST,
                                 port=self.settings.REDIS_PORT,
                                 db=self.settings.REDIS_DB,
                                 password=self.settings.REDIS_PASS)

        self.requests = requests
        if async:
            requests.adapters.extract_cookies_to_jar = lambda a, b, c: None
            self.requests = requests.Session()
            self.requests.mount('http://', AsyncHTTPAdapter())
            self.requests.mount('https://', AsyncHTTPAdapter())

    def toDict(self, protoObj):
        """Converts the (protobuf) result from an API call into a dict, for
        easier introspection."""
        iterable = False
        if isinstance(protoObj, RepeatedCompositeFieldContainer):
            iterable = True
        else:
            protoObj = [protoObj]
        retlist = []

        for po in protoObj:
            msg = dict()
            for fielddesc, value in po.ListFields():
                # print value, type(value), getattr(value, "__iter__", False)
                if fielddesc.type == descriptor.FieldDescriptor.TYPE_GROUP or \
                   isinstance(value, RepeatedCompositeFieldContainer) or \
                   isinstance(value, Message):
                    msg[fielddesc.name] = self.toDict(value)
                else:
                    msg[fielddesc.name] = value
            retlist.append(msg)
        if not iterable:
            if len(retlist) > 0:
                return retlist[0]
            else:
                return None
        return retlist

    def toStr(self, protoObj):
        """Used for pretty printing a result from the API."""
        return text_format.MessageToString(protoObj)

    def _try_register_preFetch(self, protoObj):
        fields = [i.name for (i, _) in protoObj.ListFields()]
        if ("preFetch" in fields):
            for p in protoObj.preFetch:
                self.preFetch[p.url] = p.response

    def setAuthSubToken(self, authSubToken):
        self.authSubToken = authSubToken

        # put your auth token in settings.py to avoid multiple login requests
        if self.debug:
            print "authSubToken: " + authSubToken

    def login(self, email=None, password=None, authSubToken=None):
        """Login to your Google Account. You must provide either:
        - an email and password
        - a valid Google authSubToken"""
        if (authSubToken is not None):
            self.setAuthSubToken(authSubToken)
        else:
            if (email is None or password is None):
                raise Exception(
                    "You should provide at least authSubToken or (email and password)")

            params = {"Email": email,
                      "Passwd": password,
                      "service": self.SERVICE,
                      "accountType": self.ACCOUNT_TYPE_HOSTED_OR_GOOGLE,
                      "has_permission": "1",
                      "source": "android",
                      "androidId": self.androidId,
                      "app": "com.android.vending",
                      # "client_sig": self.client_sig,
                      "device_country": "us",
                      "operatorCountry": "us",
                      "lang": "us",
                      "sdk_version": "19"}
            headers = {
                "Accept-Encoding": "",
            }
            response = requests.post(self.URL_LOGIN, data=params,
                                     headers=headers, verify=False)
            data = response.text.split()
            params = {}
            for d in data:
                if "=" not in d:
                    continue
                k, v = d.split("=")
                params[k.strip().lower()] = v.strip()
            if "auth" in params:
                self.setAuthSubToken(params["auth"])
                self.email = email
            elif "error" in params:
                # self.log.error(response.text)
                raise LoginError("server says: " + params["error"])
            else:
                raise LoginError("Auth token not found.")

    def executeRequestApi2(self, path, datapost=None, post_content_type="application/x-www-form-urlencoded; charset=UTF-8"):
        #if (datapost is None and path in self.preFetch):
        #    data = self.preFetch[path]
        #else:
        headers = {
            "Accept-Language": self.lang,
            "Authorization": "GoogleLogin auth=%s" % self.authSubToken,
            # "X-DFE-Enabled-Experiments": "cl:billing.select_add_instrument_by_default",
            "X-DFE-Enabled-Experiments": "cl:billing.cleanup_auth_settings,cl:details.album_all_access_enabled,cl:billing.prompt_for_fop,cl:details.hide_download_count_in_title,cl:details.double_fetch_social_data,cl:billing.purchase_button_show_wallet_3d_icon,cl:search.cap_local_suggestions_2,cl:billing.prompt_for_fop_ui_mode_radio_button,cl:billing.prompt_for_auth_choice_once",
            # "X-DFE-Unsupported-Experiments": "nocache:billing.use_charging_poller,market_emails,buyer_currency,prod_baseline,checkin.set_asset_paid_app_field,shekel_test,content_ratings,buyer_currency_in_app,nocache:encrypted_apk,recent_changes",
            "X-DFE-Unsupported-Experiments": "nocache:dfe:dc:1,nocache:dfe:uc:US,nocache:dfe:ci:1788,cl:details.details_page_v2_enabled,cl:disable_web_p_compression,cl:search.dora_searchbox_enabled,cl:search.hide_ordinals_from_search_results,targets:CBIIEwgUCBUIGAgjCFcI8QEI_QEIrQII8AII2QMI-wMIwgQIxAQI0gQI4wUI5AUI5QUI6AUIsgYIzQYI1wYIhQcIjgcIqgcItAcIwAcI7wcI8AcIrggI5w8I7A8IkxAIqhAIkJWBBgiRlYEGCJKVgQYIk5WBBgiVlYEGCJeVgQYImJWBBgialYEGCJuVgQYIpJWBBgillYEGCKiVgQYIqpWBBgirlYEGCKyVgQYIrZWBBgizlYEGCLSVgQYItpWBBgi3lYEGCLiVgQYIuZWBBgi6lYEGCLuVgQYIvJWBBgjBlYEGCMKVgQYIxJWBBgjFlYEGCMiVgQYIyZWBBgjOlYEGCM-VgQYI0JWBBgjUlYEGCNiVgQYI3JWBBgjxlYEGCPiVgQYI-5WBBgiGloEGCIeWgQYIjJaBBgiNloEGCJCWgQYIlpaBBgiZloEGCO6XgQYItpiBBgi-mIEGCOyZgQYI3JqBBhKFAgA84ABml1aOIwByERlbKxpG7buyghM9Klm_aUwSS0CzhOXJ6N7E9fv0B1YgF-gjnDwsoXbTWeP4fenDfR8BUimff2kbdromJCZtJQpVKojFyC4Qc0ZCuX0_BYOmY1gQAJUumAt9dNvw1bClIKhOL-nqrUnBTFttG5W8-kmhVr8V8z5gXynzvR_BQDTK1iyVcVlT6vKhTYQQC_KdfK09B1COG1GzLqM1UGAGE9N0vkAOrZtOqjH-yfuZ_h5eKY0soHMcKvPXOEgq3VTRO8e16_eqIy3FTmPfUk_IRJpu_sItcBc4x2PQm-7RMctj0CzDPCrIMOtVGntNPgcXHwIL5Avw40eE4A==",
            "X-DFE-Device-Id": self.androidId,
            "X-DFE-Client-Id": "am-android-google",
            "X-DFE-Request-Params": "timeoutMs=5000; retryAttempt=1",
            "X-DFE-Logging-Id": "-2541767d77652ea6", # Deprecated?
            # "X-DFE-MCCMNC": "310120",
            "X-DFE-MCCMNC": "310004",
            # "User-Agent": "Android-Finsky/3.7.13 (api=3,versionCode=8013013,sdk=16,device=crespo,hardware=herring,product=soju)",
            # "User-Agent": "Android-Finsky/3.10.14 (api=3,versionCode=8016014,sdk=15,device=GT-I9300,hardware=aries,product=GT-I9300)",
            "User-Agent": "Android-Finsky/5.0.31 (api=3,versionCode=80300031,sdk=19,device=hammerhead,hardware=hammerhead,product=hammerhead)",
            # "X-DFE-SmallestScreenWidthDp": "320",
            "X-DFE-Filter-Level": "3",
            # "Accept-Encoding": "",
            "Host": "android.clients.google.com"
        }

        if datapost is not None:
            headers["Content-Type"] = post_content_type

        url = "https://android.clients.google.com/fdfe/%s" % path
        if datapost is not None:
            response = self.requests.post(url, data=str(datapost), headers=headers, verify=False)
        else:
            response = self.requests.get(url, headers=headers, verify=False)

            """// For debug
            if datapost is not None:
                response = session.post(url, data=str(datapost), headers=headers, verify=False)
            else:
                response = session.get(url, headers=headers, verify=False)

            print response.content

            root = html.fromstring(response.content)
            vcode_url = root.xpath("//img[1]/@src")[0]

            vurl = urljoin(response.url, vcode_url)
            action_url = urljoin(response.url, 'CaptchaRedirect')

            resp = session.get(vurl)
            with open("x.jpg", 'w') as f:
                f.write(resp.content)

            vcode = raw_input()
            param = {'continue': url, 'id': root.xpath("//input[@name='id']/@value")[0],
                     'captcha': vcode, 'submit': 'Submit'}

            action_url = action_url + '?' + urllib.urlencode(param)
            print action_url
            r = session.get(action_url.replace('https', 'http'), headers=headers)
            print r.status_code
            print r.content
            """

        data = response.content

        '''
        data = StringIO.StringIO(data)
        gzipper = gzip.GzipFile(fileobj=data)
        data = gzipper.read()
        '''
        message = googleplay_pb2.ResponseWrapper.FromString(data)
        #self._try_register_preFetch(message)

        # Debug
        #print text_format.MessageToString(message)
        return message

    #####################################
    # Google Play API Methods
    #####################################

    def search(self, query, nb_results=None, offset=None):
        """Search for apps."""
        path = "search?c=3&q=%s" % requests.utils.quote(query)
        # TODO handle categories
        if (nb_results is not None):
            path += "&n=%d" % int(nb_results)
        if (offset is not None):
            path += "&o=%d" % int(offset)

        message = self.executeRequestApi2(path)
        return message.payload.searchResponse

    def details(self, packageName):
        """Get app details from a package name.
        packageName is the app unique ID (usually starting with 'com.')."""
        path = "details?doc=%s" % requests.utils.quote(packageName)
        message = self.executeRequestApi2(path)
        return message.payload.detailsResponse

    def bulkDetails(self, packageNames):
        """Get several apps details from a list of package names.

        This is much more efficient than calling N times details() since it
        requires only one request.

        packageNames is a list of app ID (usually starting with 'com.')."""
        path = "bulkDetails"
        req = googleplay_pb2.BulkDetailsRequest()
        req.docid.extend(packageNames)
        data = req.SerializeToString()
        message = self.executeRequestApi2(path, data, "application/x-protobuf")
        return message.payload.bulkDetailsResponse

    def browse(self, cat=None, ctr=None):
        """Browse categories.
        cat (category ID) and ctr (subcategory ID) are used as filters."""
        path = "browse?c=3"
        if (cat is not None):
            path += "&cat=%s" % requests.utils.quote(cat)
        if (ctr is not None):
            path += "&ctr=%s" % requests.utils.quote(ctr)
        message = self.executeRequestApi2(path)
        return message.payload.browseResponse

    def list(self, cat, ctr=None, nb_results=None, offset=None):
        """List apps.
        If ctr (subcategory ID) is None, returns a list of valid subcategories.
        If ctr is provided, list apps within this subcategory."""
        path = "list?c=3&cat=%s" % requests.utils.quote(cat)
        if (ctr is not None):
            path += "&ctr=%s" % requests.utils.quote(ctr)
        if (nb_results is not None):
            path += "&n=%s" % requests.utils.quote(nb_results)
        if (offset is not None):
            path += "&o=%s" % requests.utils.quote(offset)
        message = self.executeRequestApi2(path)
        return message.payload.listResponse

    def similar(self, packageName):
        """Similar apps.
        """
        path = "rec?c=3&doc=%s&rt=1"
        message = self.executeRequestApi2(path)
        return message.payload.listResponse

    def cross(self, packageName):
        """Users Also Installed
        """
        path = "rec?c=3&doc=%s&rt=2"
        message = self.executeRequestApi2(path)
        return message.payload.listResponse

    def reviews(self, packageName, filterByDevice=False, sort=2, nb_results=None, offset=None):
        """Browse reviews.
        packageName is the app unique ID.
        If filterByDevice is True, return only reviews for your device."""
        path = "rev?doc=%s&sort=%d" % (requests.utils.quote(packageName), sort)
        if (nb_results is not None):
            path += "&n=%d" % int(nb_results)
        if (offset is not None):
            path += "&o=%d" % int(offset)
        if(filterByDevice):
            path += "&dfil=1"
        message = self.executeRequestApi2(path)
        return message.payload.reviewResponse

    def get_apk_url(self, packageName, versionCode, offerType=1):
        result = {"apkurl": "", "cookie": "", "obbs": []}
        path = "purchase"
        data = "ot=%d&doc=%s&vc=%d" % (offerType, packageName, versionCode)
        message = self.executeRequestApi2(path, data)
        url = message.payload.buyResponse.purchaseStatusResponse.appDeliveryData.downloadUrl
        additions = message.payload.buyResponse.purchaseStatusResponse.appDeliveryData.additionalFile
        for addit in additions:
            obb = {'file_type': addit.fileType,
                   'version_code': addit.versionCode,
                   'download_url': addit.downloadUrl}
            result["obbs"].append(obb)

        try:
            cookie = message.payload.buyResponse.purchaseStatusResponse.appDeliveryData.downloadAuthCookie[0]
        except Exception, e:
            self.log.error("Error with message @@@ %s" % str(message))
            raise e

        cookies = {
            str(cookie.name): str(cookie.value)
            # python-requests #459 fixes this
        }

        result["apkurl"] = url
        result["cookie"] = cookies

        return result

    def get_purchased_url(self, packageName, versionCode, offerType=1):
        """Get paid app download url which is purchased.
        """
        result = {"apkurl": "", "cookie": "", "obbs": []}
        path = "delivery?ot=%d&doc=%s&vc=%d" % (offerType, packageName, versionCode)
        message = self.executeRequestApi2(path)
        url = message.payload.deliveryResponse.appDeliveryData.downloadUrl
        additions = message.payload.deliveryResponse.appDeliveryData.additionalFile
        for addit in additions:
            obb = {'file_type': addit.fileType,
                   'version_code': addit.versionCode,
                   'download_url': addit.downloadUrl}
            result["obbs"].append(obb)

        try:
            cookie = message.payload.deliveryResponse.appDeliveryData.downloadAuthCookie[0]
        except Exception, e:
            self.log.error("Error with message @@@ %s" % str(message))
            raise e
        cookies = {
            str(cookie.name): str(cookie.value)
            # python-requests #459 fixes this
        }

        result["apkurl"] = url
        result["cookie"] = cookies

        return result

    def download(self, packageName, versionCode, offerType=1, is_purchased=False):
        """Download an app and return its raw data (APK file), and OBB file if include.
        packageName is the app unique ID (usually starting with 'com.').
        versionCode can be grabbed by using the details() method on the givenapp.
        is_purchased can identify whether app is paid.
        return an object like as {'apk': {'filename': 'xxxx', 'data': 'xxxxx'},
                                  'obb': [{'filename': 'xxxx', 'data': 'xxxx'}, ...]}"""
        if is_purchased:
            purchased = self.get_purchased_url(packageName, versionCode, offerType)
        else:
            purchased = self.get_apk_url(packageName, versionCode, offerType)
        headers = {"User-Agent": "AndroidDownloadManager/4.1.1 (Linux; U; Android 4.1.1; Nexus S Build/JRO03E)"}

        result = {
            'apk': '', 'obb': [],
            'google_id': self.email,
            'device_id': self.androidId
        }
        self.log.debug("Downloading apk by package %s" % packageName)
        response = self.requests.get(purchased['apkurl'], headers=headers,
                                     cookies=purchased['cookie'], verify=False)
        #filename = "files/{}.apk".format(sha1("{}/{}".format(packageName, md5(response.content))))
        filename = "files/{}__{}.apk".format(packageName, versionCode)
        result["apk"] = {
            'filename': filename,
            'data': response.content,
        }
        for n, obb in enumerate(purchased['obbs']):
            self.log.debug("Downloading obb#%d by package %s" % (n, packageName))
            response = self.requests.get(obb['download_url'], headers=headers,
                                         cookies=purchased['cookie'], verify=False)

            obb_obj = {'filename': "{}.{}.{}.obb".format('main' if obb['file_type'] == 0 else 'patch',
                                                         obb['version_code'], packageName),
                       'data': response.content}
            result['obb'].append(obb_obj)

        return result

    def download_file(self, packageName):
        """Download an APK file(PKG file if OBB file include), and save to local path.
        packageName is the app unique ID (usually starting with 'com.').
        return apk(pkg) filename
        """
        detail = self.details(packageName)
        price = detail.docV2.offer[0].formattedAmount.lower()
        is_purchased = False
        if price != 'free':
            is_purchased = True
        version_code = detail.docV2.details.appDetails.versionCode
        offer_type = detail.docV2.offer[0].offerType
        data = self.download(packageName, version_code, offer_type,
                             is_purchased=is_purchased)

        pkg_filename = "{}.pkg".format(packageName)
        zf = zipfile.ZipFile(pkg_filename, "w")
        zf.writestr(data['apk']['filename'], data['apk']['data'])

        for obb in data['obb']:
            zf.writestr(obb['filename'], obb['data'])

        zf.close()
        return pkg_filename
        print "pkg file {} downloaded.".format(pkg_filename)

    def get_detail(self, appid):
        """Get app detail as a dict.
        """
        item = {}
        detail = self.details(appid)
        if not detail.docV2.docid:
            raise AppNotFoundError(appid)
        item["appid"] = appid
        item["version_code"] = detail.docV2.details.appDetails.versionCode
        item["offer_type"] = detail.docV2.offer[0].offerType
        category = detail.docV2.details.appDetails.appCategory[0]
        item["category_id"] = CATEGORY_MAP[category]
        item["description"] = detail.docV2.descriptionHtml
        # detect the string language from description, return ISO 639-1 language code.
        item["lang"] = unicode(guess_language(item["description"] or 'en'))
        item["developer"] = detail.docV2.details.appDetails.developerName
        item["group"] = GROUP_MAP.get(detail.docV2.details.appDetails.appType) or 'app'
        item["icon"] = [img.imageUrl for img in detail.docV2.image if img.imageType == 4][0]
        item["is_deleted"] = False
        item["name"] = detail.docV2.title
        # for url seo
        name = re.sub(ur"""\$|\%|\(|\)|\[|\[|\]|\*|\ |\®|\#|\~|\`|\@|\^|\&|\{|\}|\<|\>|\?|\"|\'|\’|\–|\:|\;|\||\/|\+|\!|\•|\,|\™|\_|\.""", '-', item['name'])
        name_url = urllib.quote(name.encode('utf-8'))
        if "%" not in name_url:
            item['name_url'] = name_url
        item["operating_systems"] = ""
        item["order"] = 0
        item["rating"] = detail.docV2.aggregateRating.starRating
        item['rating_user'] = humanize.intcomma(detail.docV2.aggregateRating.ratingsCount)

        total_count = detail.docV2.details.appDetails.numDownloads
        item["total_count"] = remove_downloads(total_count)
        item["download_count"] = strCount_to_intCount(total_count)

        item["release_time"] = detail.docV2.details.appDetails.uploadDate
        item["screenshot"] = [img.imageUrl for img in detail.docV2.image if img.imageType == 1]
        item["update_info"] = detail.docV2.details.appDetails.recentChangesHtml
        item["version"] = detail.docV2.details.appDetails.versionString
        item["offer_type"] = detail.docV2.offer[0].offerType
        item["size"] = humanize.naturalsize(detail.docV2.details.appDetails.installationSize, gnu=True)
        item["source"] = 'crawler'
        item["channel"] = 'googleplay'
        item["price"] = detail.docV2.offer[0].formattedAmount.lower()
        item["paid"] = 1
        item["search_order"] = 0
        item["search_reindex"] = 1
        item['app_status'] = 0

        return item

    def bulk_detail(self, *appids):
        """Get several apps details from a list of package names.
        return as a dict generator.
        """
        bulk_message = self.bulkDetails(appids)
        for appid, message in zip(appids, bulk_message.entry):
            try:
                if message.ByteSize() > 0:
                    item = {}
                    item["appid"] = message.doc.docid
                    item["version_code"] = message.doc.details.appDetails.versionCode
                    item["price"] = message.doc.offer[0].formattedAmount.lower()
                    seen = self.redis.hget("app_record", item['appid'])
                    if item['price'] != 'free':
                        self.redis.sadd("paid_appids", item['appid'])
                        continue
                    if str(item["version_code"]) != seen:
                        if not seen:
                            item['tag'] = 'new'
                        else:
                            item['tag'] = 'updated'
                    else:
                        #self.log.warning("Ignore app %s vc %s local vc %s" % (item['appid'], item['version_code'], seen))
                        continue

                    share_url = message.doc.shareUrl
                    response = self.requests.get(share_url)
                    if response.status_code == 404:
                        continue

                    q = _Q(response.content.decode('utf-8'))
                    item["offer_type"] = message.doc.offer[0].offerType
                    category_url = q(".document-subtitle.category").attr('href')

                    category = ''
                    if category_url:
                        category = re.search('.*/(.*?)$', category_url).group(1)
                    item["category_id"] = CATEGORY_MAP.get(category, 'TOOLS')
                    item["category_play"] = category
                    item["description"] = q('div[itemprop=description]').html()
                    item["lang"] = unicode(guess_language(q('.id-app-orig-desc').text() or 'en'))
                    item["developer"] = q("a.document-subtitle.primary span").text()
                    item["group"] = GROUP_MAP.get(message.doc.details.appDetails.appType) or 'app'
                    item["icon"] = [img.imageUrl for img in message.doc.image if img.imageType == 4][0]
                    item["is_deleted"] = False
                    item["name"] = message.doc.title
                    name = re.sub(ur"""\$|\%|\(|\)|\[|\[|\]|\*|\ |\®|\#|\~|\`|\@|\^|\&|\{|\}|\<|\>|\?|\"|\'|\’|\–|\:|\;|\||\/|\+|\!|\•|\,|\™|\_""", '-', item['name'])
                    name_url = urllib.quote(name.encode('utf-8'))
                    if "%" not in name_url:
                        item['name_url'] = name_url

                    item["operating_systems"] = q("div[itemprop=operatingSystems]").text().strip()
                    item["order"] = 0
                    item["rating"] = message.doc.aggregateRating.starRating
                    item['rating_user'] = humanize.intcomma(message.doc.aggregateRating.ratingsCount)

                    total_count = message.doc.details.appDetails.numDownloads
                    total_count = remove_downloads(total_count)
                    item["total_count"] = total_count
                    item["download_count"] = strCount_to_intCount(total_count)

                    item["release_time"] = message.doc.details.appDetails.uploadDate
                    item["screenshot"] = [img.get('src') if img.get('src').startswith('http') else 'http:' + img.get('src') for img in q("div.thumbnails img[itemprop=screenshot]")]
                    item["update_info"] = q(".recent-change").text().strip()
                    item["version_name"] = q("div[itemprop=softwareVersion]").text()
                    item["size"] = humanize.naturalsize(message.doc.details.appDetails.installationSize, gnu=True)
                    item["source"] = 'crawler'
                    item["channel"] = 'googleplay'
                    item["paid"] = 1  # 1 for free, 2 for paid
                    item["search_order"] = 0
                    item["search_reindex"] = 1
                    item['app_status'] = 0

                    yield item
                else:
                    yield {"appid": appid, 'notfound': True}
            except Exception as e:
                traceback.print_exc()
