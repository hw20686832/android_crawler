# coding:utf-8
import re
from urlparse import urljoin

import requests
from lxml import html


headers = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, sdch",
    "Accept-Language": "zh-CN,zh;q=0.8,en-US;q=0.6,en;q=0.4",
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "Host": "www.appannie.com",
    "Pragma": "no-cache",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Ubuntu Chromium/36.0.1985.125 Chrome/36.0.1985.125 Safari/537.36"
}

country_list = ['united-states', 'saudi-arabia', 'indonesia', 'india']


def login_appannie():
    login_url = 'https://www.appannie.com/account/login/'
    session = requests.Session()
    session.headers = headers
    loginRep = session.get(login_url, verify=False)
    csrfmiddlewaretoken = ""
    try:
        csrfmiddlewaretoken = loginRep.cookies._cookies['www.appannie.com']['/']['csrftoken'].value
    except:
        pass
    data = {
        "csrfmiddlewaretoken": csrfmiddlewaretoken,
        "next": "/dashboard/home/",
        "username": "zhuzhuwang1234@sina.com",
        "password": "wangzhu1234",
        "remember_user": "on"
    }
    session.post(login_url, data=data, verify=False)
    session.headers['X-Requested-With'] = 'XMLHttpRequest'
    return session


def touch_appannie():
    for country_name in country_list:
        touch_appannie_for_one_country(country_name)
        for item in touch_appannie_for_one_country(country_name):
            yield item


def touch_appannie_for_one_country(country_name):
    urls = [
        'https://www.appannie.com/apps/google-play/top-chart/{}/application/'.format(country_name),
        'https://www.appannie.com/apps/google-play/top-chart/{}/game/'.format(country_name),
    ]

    session = login_appannie()

    appids = set()
    for url, cate in urls:
        session.headers['Referer'] = url

        response = session.get(url)
        more_page = re.search("pageVal\.data_url = '(.*)';", response.content).group(1)
        ch = re.search("pageVal\.chart_hour = '(.*)';", response.content).group(1)

        more_url = urljoin(url, more_page) + '?p=2-&h=%s&iap=undefined' % ch

        response = session.get(more_url)
        root = html.fromstring(response.text)
        free = root.xpath("//tr[@class='odd' or @class='even']/td[1][contains(@class, 'app free')]//div[@class='main-info']//span[@class='product-code']/text()")
        grossing = root.xpath("//tr[@class='odd' or @class='even']/td[3][contains(@class, 'app free')]//div[@class='main-info']//span[@class='product-code']/text()")
        new_free = root.xpath("//tr[@class='odd' or @class='even']/td[4][contains(@class, 'app free')]//div[@class='main-info']//span[@class='product-code']/text()")

        appids |= set(free + grossing + new_free)
        print 'Url %s fetched free: %d, grossing: %d, new free: %d; all %d' % (url, len(set(free)), len(set(grossing)), len(set(new_free)), len(set(free) | set(grossing) | set(new_free)))

        for appid in appids:
            yield appid
