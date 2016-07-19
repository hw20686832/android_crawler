# coding:utf-8
from .views import admin, mobvista, hasoffers, mobisummer

handlers = [
    (r"/", admin.IndexHandler),
    (r"/login", admin.LoginHandler),
    (r"/logout", admin.LogoutHandler),
    (r"/crawler", admin.AppHandler),
    (r"/download", admin.DownloadHandler),
    (r"/profile", admin.ProfileHandler),
    (r"/schd", admin.ScheduleHandler),
    (r"/dqueue", admin.DownloadQueueHandler),
    (r"/rlist", admin.ReadyListHandler),
    (r"/purchase", admin.PurchaseHandler),
    (r"/paidlist", admin.PaidListHandler),
    (r"/upload", admin.UploadHandler),
    (r"/clean", admin.CleanHandler),
    (r"/acct", admin.AccountPageHandler),
    (r"/account", admin.AccountHandler),
    (r"/black", admin.BlackListPageHandler),
    (r"/blacklist", admin.BlackListHandler),
    (r"/fetch", admin.FetchHandler),
    # ad pool #
    (r"/mobvista", mobvista.Pull),
    (r"/hasoffers", hasoffers.Pull),
    (r"/has", hasoffers.Pulls),
    (r"/mobisummer", mobisummer.Pull),
    (r"/mobi", mobisummer.Pulls)
]
