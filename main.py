#!/usr/bin/env python
# coding:utf-8
import sys
from optparse import OptionParser

import settings


def get_class(cls):
    parts = cls.split('.')
    module = ".".join(parts[:-1])
    m = __import__(module)
    for comp in parts[1:]:
        m = getattr(m, comp)
    return m


def main():
    usage = "Usage: %prog [crawl|worker|fetch|update|remove|add|download|admin|shell] [options] arg"
    parser = OptionParser(usage)
    try:
        cmd = sys.argv[1]
    except IndexError:
        parser.error("incorrect number of arguments")

    parser.add_option("-l", "--loglevel", dest="loglevel",
                      help="log level.")

    if cmd == "crawl":
        from crawler import Detailer, Downloader

        parser.add_option("-a", "--action", dest="action",
                          help="detail or download?")
        options, args = parser.parse_args(args=sys.argv[1:])
        if options.action == "detail":
            c = Detailer(config=settings)
        elif options.action == "download":
            c = Downloader(config=settings)

        c.start()
    elif cmd == "update":
        from core.base import Base

        parser.add_option("-t", "--ptype", dest="ptype",
                          help="paid or free", default="free")
        options, args = parser.parse_args(args=sys.argv[1:])
        engine = Base(settings)
        engine.reschedule(options.ptype)
    elif cmd == 'remove':
        from core.base import Base

        parser.add_option("-a", "--appids", dest="appids",
                          help="app id string")
        options, args = parser.parse_args(args=sys.argv[1:])
        engine = Base(settings)
        [_ for _ in engine.remove(*options.appids.split(','))]
    elif cmd == 'add':
        from core.base import Base

        parser.add_option("-a", "--appid", dest="appid",
                          help="app id string", default="")
        parser.add_option("", "--force", dest="force",
                          help="schedule appid immedite")
        options, args = parser.parse_args(args=sys.argv[1:])
        engine = Base(settings)
        appids = options.appid.split(',')
        n = engine.add(appids, force=options.force)

        print "%d appids scheduled." % n
    elif cmd == 'shell':
        from core.base import Base

        parser.add_option("-u", "--uid", dest="uid",
                          help="use the specifid google user to fetch.")
        options, args = parser.parse_args(args=sys.argv[1:])
        engine = Base(settings)
        engine.shell(options.uid)
    elif cmd == 'fetch':
        """Sync fetch, get detail and download apk file, then save to s3 and mongodb."""
        from core.base import Base

        parser.add_option("-a", "--appid", dest="appid",
                          help="give the appid")
        parser.add_option("-u", "--uid", dest="uid",
                          help="use the specifid google user to fetch.")
        options, args = parser.parse_args(args=sys.argv[1:])
        engine = Base(settings)
        engine.fetch(options.appid, options.uid)

    elif cmd == 'detail':
        from core.base import Base

        parser.add_option("-a", "--appid", dest="appid",
                          help="give the appid")
        options, args = parser.parse_args(args=sys.argv[1:])
        engine = Base(settings)
        engine.detail(options.appid)
    elif cmd == 'download':
        from core.base import Base

        parser.add_option("-a", "--appid", dest="appid",
                          help="give the appid")
        parser.add_option("-d", "--dist", dest="dist",
                          help="relocate the file to distination.")
        options, args = parser.parse_args(args=sys.argv[1:])
        engine = Base(settings)
        engine.download(options.appid, dist=options.dist)
    elif cmd == 'admin':
        from admin import app

        parser.add_option("-H", "--host", dest="host",
                          help="the host for web handler",
                          default=settings.HOST)
        parser.add_option("-P", "--port", dest="port",
                          help="the port for web handler",
                          default=settings.PORT)
        options, args = parser.parse_args(args=sys.argv[1:])
        settings.HOST = options.host
        settings.PORT = options.port
        app.run(settings)
    elif cmd == 'worker':
        from importlib import import_module

        from celery.bin import worker

        parser.add_option("-a", "--app", dest="app",
                          help="specify a celery app")
        parser.add_option("-q", "--queues", dest="queues",
                          help="the queues whole worker handle")
        parser.add_option("-c", "--concurrency", dest="concurrency",
                          help="concurrency number",
                          type=int, default=4)
        options, args = parser.parse_args(args=sys.argv[1:])
        app_module = import_module('.{}'.format(options.app), package='worker')
        if options.queues:
            app_module.c.select_queues(options.queues.split(','))
        task = worker.worker(app=app_module.c)
        opt = {
            'hostname': "celery@{}_{}".format(options.app, options.queues or 'all'),
            'concurrency': options.concurrency,
            'loglevel': 'INFO',
            'traceback': True
        }
        task.run(**opt)


if __name__ == '__main__':
    main()
