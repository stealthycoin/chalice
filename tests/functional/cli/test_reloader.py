import sys
import mock
import threading

import pytest

from chalice.cli import reloader
from chalice.watcher.stat import StatFileWatcher
from tests.conftest import watchdog_only


DEFAULT_DELAY = 0.1
MAX_TIMEOUT = 5.0


@pytest.fixture
def watchdog_factory():
    from chalice.watcher.eventbased import WatchdogFileWatcher
    return WatchdogFileWatcher


def modify_file_after_n_seconds(filename, contents, delay=DEFAULT_DELAY):
    t = threading.Timer(delay, function=modify_file, args=(filename, contents))
    t.daemon = True
    t.start()


def modify_file(filename, contents):
    if filename is None:
        return
    with open(filename, 'w') as f:
        f.write(contents)


def assert_reload_happens(root_dir, when_modified_file, watcher):
    http_thread = mock.Mock(spec=reloader.HTTPServerThread)
    p = reloader.WorkerProcess(http_thread, watcher)
    modify_file_after_n_seconds(when_modified_file, 'contents')
    rc = p.main(root_dir, MAX_TIMEOUT)
    assert rc == reloader.RESTART_REQUEST_RC


@watchdog_only
class TestWatchdogFileWatcher(object):
    def test_can_reload_when_file_created(self, tmpdir, watchdog_factory, monkeypatch):
        top_level_file = str(tmpdir.join('foo.py'))
        assert_reload_happens(str(tmpdir), when_modified_file=top_level_file,
                              watcher=watchdog_factory())

    def test_can_reload_when_subdir_file_created(self, tmpdir,
                                                 watchdog_factory):
        subdir_file = str(tmpdir.join('subdir').mkdir().join('foo.py'))
        assert_reload_happens(str(tmpdir), when_modified_file=subdir_file,
                              watcher=watchdog_factory())

    def test_rc_0_when_no_file_modified(self, tmpdir, watchdog_factory):
        http_thread = mock.Mock(spec=reloader.HTTPServerThread)
        p = reloader.WorkerProcess(http_thread, watchdog_factory())
        rc = p.main(str(tmpdir), timeout=0.2)
        assert rc == 0


class TestStatFileWatcher(object):
    def test_can_reload_when_file_created(self, tmpdir, monkeypatch):
        monkeypatch.delitem(sys.modules, 'testsuite_app', raising=False)
        app_pkg = tmpdir.mkdir('testsuite_app')

        appfile = app_pkg.join('__init__.py')
        appfile.write('')

        monkeypatch.syspath_prepend(str(tmpdir))
        import testsuite_app

        assert_reload_happens(str(app_pkg), when_modified_file=str(appfile),
                              watcher=StatFileWatcher())

    def test_can_reload_when_subdir_file_created(self, tmpdir):
        subdir_file = str(tmpdir.join('subdir').mkdir().join('foo.py'))
        assert_reload_happens(str(tmpdir), when_modified_file=subdir_file,
                              watcher=StatFileWatcher())

    def test_rc_0_when_no_file_modified(self, tmpdir):
        http_thread = mock.Mock(spec=reloader.HTTPServerThread)
        p = reloader.WorkerProcess(http_thread, StatFileWatcher())
        rc = p.main(str(tmpdir), timeout=0.2)
        assert rc == 0
