# coding:utf-8
import json
import datetime
import zipfile
from StringIO import StringIO
try:
    import Image
except ImportError:
    from PIL import Image

import redis
import requests
from lxml.builder import E
from lxml.etree import tostring
from boto.s3.connection import S3Connection
from androguard.core.bytecodes import apk

from utils import logger


class ApkStore(object):
    def __init__(self, config):
        self.config = config
        self.log = logger.getlog("store")
        conn = S3Connection()
        self.apk_bucket = conn.get_bucket(config.APK_BUCKET)
        self.image_bucket = conn.get_bucket(config.IMAGE_BUCKET)

        self.redis = redis.Redis(
            host=self.config.REDIS_HOST,
            port=self.config.REDIS_PORT,
            db=self.config.REDIS_DB,
            password=self.config.REDIS_PASS
        )

    def convert_icon(self, data, appid):
        """convert images"""
        imageio = StringIO(data)
        src_img = Image.open(imageio)
        dest_img = src_img.resize((160, 160), Image.BILINEAR)
        img_out = StringIO()
        dest_img.save(img_out, "PNG")
        icon_path = "icon/%s" % appid
        key = self.image_bucket.new_key(icon_path)
        key.set_contents_from_string(img_out.getvalue())
        key.close()

        return icon_path

    def save(self, item, data):
        return self.download_file(item, data)

    def _generate_manifest(self, item):
        element_tree = E.mpk_info(
            E.apk_info(
                E.name("%s_%s_0.apk" % (item['appid'],
                                        str(item['version_code']))),
                E.package(item['appid']),
                E.android_versionCode(str(item['version_code'])),
                E.android_versionName(item['version_name'])
            ),
            E.apk_path("%s_%s_0.apk" % (item['appid'],
                                        str(item['version_code']))),
            E.data_path("Android"),
            E.icon_path("icon.png"),
        )

        return tostring(element_tree, pretty_print=True,
                        xml_declaration=True, encoding='utf-8')

    def download_file(self, item, data):
        # check if valid apk file
        pkg = apk.APK(data['apk']['data'], raw=True)
        if not pkg.is_valid_APK():
            raise Exception('Not a valid APK.')
        # image download
        seq = 1
        images = []
        # for s3
        for pic in item["screenshot"]:
            try:
                self.log.debug("Downloading screenshot %s" % pic)
                response = requests.get(pic)
                img_path = "screenshot/%s/%d" % (item['appid'], seq)
                key = self.image_bucket.new_key(img_path)
                key.set_contents_from_string(response.content)
                key.close()
            except:
                self.log.error("Image convert error")
                continue
            else:
                images.append(img_path)

            seq += 1
        item["screenshot"] = images

        # icon download
        self.log.debug("Downloading icon %s" % item['icon'])
        response = requests.get(item["icon"])
        item["icon"] = self.convert_icon(response.content, item['appid'])

        item['update_time'] = datetime.datetime.now()
        if not self.redis.hexists('app_record', item['appid']):
            item['create_time'] = item['update_time']
        item['language'] = self.config.LANGUAGE
        item['release_time'] = datetime.datetime.strptime(item['release_time'],
                                                          '%b %d, %Y')
        item['google_id'] = data['google_id']
        item['device_id'] = data['device_id']

        # load min_sdk_version from raw_data
        item["version_name"] = pkg.get_androidversion_name()
        item["min_sdk_version"] = int(pkg.get_min_sdk_version())
        item["version_code"] = int(pkg.get_androidversion_code())

        if not data['obb']:
            self.log.debug("Uploading apk %s" % data['apk']['filename'])
            key = self.apk_bucket.new_key(data['apk']['filename'])
            key.set_metadata('version_code', item["version_code"])
            key.set_metadata('version_name', item["version_name"])
            key.set_metadata('Content-Disposition',
                             'attachment;filename={}'.format(data['apk']['filename']))
            key.set_contents_from_string(data['apk']['data'])
            key.close()

            item['md5'] = json.loads(key.etag)
            item['obbs'] = 0
            item["apk"] = data['apk']['filename']
        else:
            pkg_path = 'v/files/%s__%d.vpk' % (item['appid'], item['version_code'])
            self.log.debug("Uploading vpk %s" % pkg_path)
            pkg_io = StringIO()
            key = self.apk_bucket.new_key(pkg_path)
            zf = zipfile.ZipFile(pkg_io, 'w')
            zip_apk_path = "%s_%s_0.apk" % (item['appid'],
                                            item['version_code'])
            zf.writestr(zip_apk_path, data['apk']['data'])

            for obb in data['obb']:
                zip_obb_path = "Android/obb/%s/%s" % (item['appid'],
                                                      obb['filename'])
                zf.writestr(zip_obb_path, obb['data'])

            zf.writestr('manifest.xml', self._generate_manifest(item))
            zf.close()

            pkg_io.seek(0)
            key.set_metadata('version_code', item["version_code"])
            key.set_metadata('version_name', item["version_name"])
            key.set_metadata('Content-Disposition',
                             'attachment;filename={}'.format(pkg_path))
            key.set_contents_from_string(pkg_io.read())
            key.close()
            item['md5'] = json.loads(key.etag)
            item['obbs'] = 1
            item["apk"] = pkg_path

        # remove old version apks.
        old_apks = self.apk_bucket.list(
            prefix="files/{}__".format(item['appid']))
        for oa in old_apks:
            if oa.key != key.key:
                oa.delete()

        return item
