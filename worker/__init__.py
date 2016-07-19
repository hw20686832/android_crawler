# coding:utf-8
import inspect
from pkgutil import iter_modules

from celery import Task
from tornado.concurrent import TracebackFuture
from tornado.ioloop import IOLoop


def async_task(task, *args, **kwargs):
    future = TracebackFuture()
    callback = kwargs.pop("callback", None)
    if callback:
        IOLoop.instance().add_future(future,
                                     lambda future: callback(future.result()))
    result = task.apply_async(*args, **kwargs)
    IOLoop.instance().add_callback(_on_result, result, future)
    return future


def _on_result(result, future):
    # if result is not ready, add callback function to next loop,
    if result.ready():
        future.set_result(result)
    else:
        IOLoop.instance().add_callback(_on_result, result, future)


class TaskManager(object):
    def __init__(self):
        self.task_module = 'worker.tasks'
        self._tasks = {}
        for module in self.walk_modules(self.task_module):
            self._filter_tasks(module)

    def __new__(cls, *args, **kwargs):
        if not hasattr(cls, '_obj'):
            cls._obj = super(TaskManager, cls).__new__(cls, *args, **kwargs)

        return cls._obj

    def _filter_tasks(self, module):
        for cls in self.iter_task_classes(module):
            self._tasks[cls.name] = cls

    def iter_task_classes(self, module):
        for obj in vars(module).itervalues():
            if inspect.isclass(obj) and \
                    issubclass(obj, Task) and \
                    obj.__module__ == module.__name__ and \
                    getattr(obj, 'name', None) and \
                    not obj.__name__ == 'WashTask':
                yield obj

    def walk_modules(self, path, load=False):
        mods = []
        mod = __import__(path, {}, {}, [''])
        mods.append(mod)
        if hasattr(mod, '__path__'):
            for _, subpath, ispkg in iter_modules(mod.__path__):
                fullpath = path + '.' + subpath
                if ispkg:
                    mods += self.walk_modules(fullpath)
                else:
                    submod = __import__(fullpath, {}, {}, [''])
                    mods.append(submod)
        return mods

    def get_list(self):
        return sorted(self._tasks.keys())

    def next(self, task_name):
        ls = self.get_list()
        next_index = ls.index(task_name) + 1
        if next_index < len(ls):
            return self[next_index]

    def first(self):
        task_name = self.get_list()[0]
        return self[task_name]

    def __len__(self):
        return len(self._tasks)

    def __getitem__(self, task_name):
        try:
            cls = self._tasks[task_name]
        except KeyError:
            raise KeyError("Task not found: %s" % task_name)

        return cls

    def __iter__(self):
        return self._tasks.itervalues()
