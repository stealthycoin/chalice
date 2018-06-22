import time

from chalice.watcher.stat import StatFileObserver


def remove_prefix(prefix, targets):
    return {target[len(prefix.strpath) + 1:] for target in targets}


def touch(path):
    path.setmtime(time.time() + 1)


def test_does_return_new_file(tmpdir):
    stater = StatFileObserver(tmpdir.strpath)
    stater.check()
    tmpdir.join('foo.txt').write('foobarbaz')

    changes = stater.check()
    changes = remove_prefix(tmpdir, changes)

    assert len(changes) == 1
    assert 'foo.txt' in changes


def test_does_find_subdirectory_files(tmpdir):
    tmpdir.join('foo.txt').write('foo')
    tmpdir.mkdir('sub').join('bar.txt').write('bar')
    stater = StatFileObserver(tmpdir.strpath)

    changes = stater.check()
    changes = remove_prefix(tmpdir, changes)

    assert len(changes) == 2
    assert 'foo.txt' in changes
    assert 'sub/bar.txt' in changes


def test_does_return_updated_file(tmpdir):
    foo = tmpdir.join('foo.txt')
    foo.write('foo')
    stater = StatFileObserver(tmpdir.strpath)

    stater.check()
    touch(foo)
    changes = stater.check()
    changes = remove_prefix(tmpdir, changes)

    assert len(changes) == 1
    assert 'foo.txt' in changes


def test_does_return_updated_nested_file(tmpdir):
    foo = tmpdir.join('foo.txt')
    foo.write('foo')
    bar = tmpdir.mkdir('sub').join('bar.txt')
    bar.write('bar')
    stater = StatFileObserver(tmpdir.strpath)

    stater.check()
    touch(foo)
    touch(bar)
    changes = stater.check()
    changes = remove_prefix(tmpdir, changes)

    assert len(changes) == 2
    assert 'foo.txt' in changes
    assert 'sub/bar.txt' in changes


def test_does_return_empty_set_when_no_updates(tmpdir):
    foo = tmpdir.join('foo.txt')
    foo.write('foo')
    bar = tmpdir.mkdir('sub').join('bar.txt')
    bar.write('bar')
    stater = StatFileObserver(tmpdir.strpath)

    stater.check()
    changes = stater.check()
    changes = remove_prefix(tmpdir, changes)

    assert changes == set()
