from typing import Callable  # noqa


class Watcher(object):
    def start_watching(self, handler, path):
        # type: (Callable, str) -> None
        raise NotImplementedError('start_watching')
