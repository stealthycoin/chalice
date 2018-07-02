import os
import sys
import threading
import time

from typing import Dict, List, Set, Callable  # noqa

from chalice.watcher.shared import Watcher
from chalice.utils import OSUtils


class StatFileObserver(object):
    def __init__(self, path):
        # type: (str) -> None
        self._path = path
        self._osutils = OSUtils()
        self._mtimes = {}  # type: Dict[str, int]

    def check(self):
        # type: () -> Set[str]
        # TODO: this is currently broken and refreshes every cycle
        updated = set([])
        for filepath in self._iter_module_files():
            if self._check_file(filepath):
                needs_update = True
        return needs_update


    def _iter_module_files(self):
        """This iterates over all relevant Python files.  It goes through all
        loaded files from modules, all files in folders of already loaded modules
        as well as all files reachable through a package.
        """
        # COPIED FROM: https://github.com/pallets/werkzeug/blob/master/werkzeug/_reloader.py#L12
        # The list call is necessary on Python 3 in case the module
        # dictionary modifies during iteration.
        for module in list(sys.modules.values()):
            if module is None:
                continue
            filename = getattr(module, '__file__', None)
            if filename:
                if os.path.isdir(filename) and \
                   os.path.exists(os.path.join(filename, "__init__.py")):
                    filename = os.path.join(filename, "__init__.py")
                old = None
                while not os.path.isfile(filename):
                    old = filename
                    filename = os.path.dirname(filename)
                    if filename == old:
                        break
                else:
                    if filename[-4:] in ('.pyc', '.pyo'):
                        filename = filename[:-1]
                    yield filename

    def _check_file(self, path):
        # type: (str) -> Set[str]
        new_mtime = self._osutils.mtime(path)
        old_mtime = self._mtimes.get(path, 0)
        if new_mtime > old_mtime:
            self._mtimes[path] = new_mtime
            return True
        return False


class StatFileWatcher(Watcher):
    def start_watching(self, handler, path):
        # type: (Callable, str) -> None
        observer = StatFileObserver(path)
        t = threading.Thread(target=self._run, args=(handler, observer,))
        t.daemon = True
        t.start()

    def _run(self, handler, observer):
        # type: (Callable, StatFileObserver) -> None
        observer.check()
        while True:
            time.sleep(1)
            if observer.check():
                handler()
