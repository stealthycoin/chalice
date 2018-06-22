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
        return self._check_dir(self._path)

    def _check_dir(self, directory):
        # type: (str) -> Set[str]
        updated = set()  # type: Set[str]
        subdirectories_to_check = []  # type: List[str]

        directory_entries = self._osutils.get_directory_contents(directory)
        for entry in directory_entries:
            full_path = self._osutils.joinpath(directory, entry)

            if self._osutils.file_exists(full_path):
                updated.update(self._check_file(full_path))

            if self._osutils.directory_exists(full_path):
                subdirectories_to_check.append(full_path)

        for dir_path in subdirectories_to_check:
            updated.update(self._check_dir(dir_path))

        return updated

    def _check_file(self, path):
        # type: (str) -> Set[str]
        new_mtime = self._osutils.mtime(path)
        old_mtime = self._mtimes.get(path, 0)
        if new_mtime > old_mtime:
            self._mtimes[path] = new_mtime
            return set([path])
        return set()


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
            changes = observer.check()
            if changes:
                handler()
