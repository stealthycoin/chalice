import sys
import os
import pytest
import zipfile
import tarfile
import io

from chalice.utils import OSUtils
from chalice.compat import pip_no_compile_c_env_vars
from chalice.compat import pip_no_compile_c_shim
from chalice.deploy.packager import Package
from chalice.deploy.packager import PipRunner
from chalice.deploy.packager import SDistMetadataFetcher
from chalice.deploy.packager import InvalidSourceDistributionNameError
from chalice.deploy.packager import SubprocessPip
from chalice.deploy.packager import NoSuchPackageError
from chalice.deploy.packager import PackageDownloadError
from chalice.deploy.packager import ChaliceIgnore
from tests.conftest import FakePipCall
from tests.conftest import InMemoryOSUtils


class FakePip(object):
    def __init__(self):
        self._calls = []
        self._returns = []

    def main(self, args, env_vars=None, shim=None):
        self._calls.append(FakePipCall(args, env_vars, shim))
        if self._returns:
            return self._returns.pop(0)
        # Return an rc of 0 and an empty stderr
        return 0, b''

    def add_return(self, return_pair):
        self._returns.append(return_pair)

    @property
    def calls(self):
        return self._calls


@pytest.fixture
def pip_runner():
    pip = FakePip()
    pip_runner = PipRunner(pip)
    return pip, pip_runner


@pytest.fixture
def osutils():
    return OSUtils()


@pytest.fixture
def mem_osutils():
    return InMemoryOSUtils()


@pytest.fixture
def sdist_reader():
    return SDistMetadataFetcher()


class TestPackage(object):
    def test_can_create_package_with_custom_osutils(self, osutils):
        pkg = Package('', 'foobar-1.0-py3-none-any.whl', osutils)
        assert pkg._osutils == osutils

    def test_wheel_package(self):
        filename = 'foobar-1.0-py3-none-any.whl'
        pkg = Package('', filename)
        assert pkg.dist_type == 'wheel'
        assert pkg.filename == filename
        assert pkg.identifier == 'foobar==1.0'
        assert str(pkg) == 'foobar==1.0(wheel)'

    def test_invalid_package(self):
        with pytest.raises(InvalidSourceDistributionNameError):
            Package('', 'foobar.jpg')

    def test_same_pkg_sdist_and_wheel_collide(self, osutils, sdist_builder):
        with osutils.tempdir() as tempdir:
            sdist_builder.write_fake_sdist(tempdir, 'foobar', '1.0')
            pkgs = set()
            pkgs.add(Package('', 'foobar-1.0-py3-none-any.whl'))
            pkgs.add(Package(tempdir, 'foobar-1.0.zip'))
            assert len(pkgs) == 1

    def test_diff_pkg_sdist_and_whl_do_not_collide(self):
        pkgs = set()
        pkgs.add(Package('', 'foobar-1.0-py3-none-any.whl'))
        pkgs.add(Package('', 'badbaz-1.0-py3-none-any.whl'))
        assert len(pkgs) == 2

    def test_same_pkg_is_eq(self):
        pkg = Package('', 'foobar-1.0-py3-none-any.whl')
        assert pkg == pkg

    def test_pkg_is_eq_to_similar_pkg(self):
        pure_pkg = Package('', 'foobar-1.0-py3-none-any.whl')
        plat_pkg = Package('', 'foobar-1.0-py3-py36m-manylinux1_x86_64.whl')
        assert pure_pkg == plat_pkg

    def test_pkg_is_not_equal_to_different_type(self):
        pkg = Package('', 'foobar-1.0-py3-none-any.whl')
        non_package_type = 1
        assert not (pkg == non_package_type)

    def test_pkg_repr(self):
        pkg = Package('', 'foobar-1.0-py3-none-any.whl')
        assert repr(pkg) == 'foobar==1.0(wheel)'

    def test_wheel_data_dir(self):
        pkg = Package('', 'foobar-2.0-py3-none-any.whl')
        assert pkg.data_dir == 'foobar-2.0.data'


class TestSubprocessPip(object):
    def test_can_invoke_pip(self):
        pip = SubprocessPip()
        rc, err = pip.main(['--version'])
        # Simple assertion that we can execute pip and it gives us some output
        # and nothing on stderr.
        assert rc == 0
        assert err == b''


class TestPipRunner(object):
    def test_build_wheel(self, pip_runner):
        # Test that `pip wheel` is called with the correct params
        pip, runner = pip_runner
        wheel = 'foobar-1.0-py3-none-any.whl'
        directory = 'directory'
        runner.build_wheel(wheel, directory)

        assert len(pip.calls) == 1
        call = pip.calls[0]
        assert call.args == ['wheel', '--no-deps', '--wheel-dir',
                             directory, wheel]
        assert call.env_vars == {}
        assert call.shim == ''

    def test_build_wheel_without_c_extensions(self, pip_runner):
        # Test that `pip wheel` is called with the correct params when we
        # call it with compile_c=False. These will differ by platform.
        pip, runner = pip_runner
        wheel = 'foobar-1.0-py3-none-any.whl'
        directory = 'directory'
        runner.build_wheel(wheel, directory, compile_c=False)

        assert len(pip.calls) == 1
        call = pip.calls[0]
        assert call.args == ['wheel', '--no-deps', '--wheel-dir',
                             directory, wheel]
        assert call.env_vars == pip_no_compile_c_env_vars
        assert call.shim == pip_no_compile_c_shim

    def test_download_all_deps(self, pip_runner):
        # Make sure that `pip download` is called with the correct arguments
        # for getting all sdists.
        pip, runner = pip_runner
        runner.download_all_dependencies('requirements.txt', 'directory')

        assert len(pip.calls) == 1
        call = pip.calls[0]
        assert call.args == ['download', '-r',
                             'requirements.txt', '--dest', 'directory']
        assert call.env_vars is None
        assert call.shim is None

    def test_download_wheels(self, pip_runner):
        # Make sure that `pip download` is called with the correct arguments
        # for getting lambda compatible wheels.
        pip, runner = pip_runner
        packages = ['foo', 'bar', 'baz']
        runner.download_manylinux_wheels(packages, 'directory')
        if sys.version_info[0] == 2:
            abi = 'cp27mu'
        else:
            abi = 'cp36m'
        expected_prefix = ['download', '--only-binary=:all:', '--no-deps',
                           '--platform', 'manylinux1_x86_64',
                           '--implementation', 'cp', '--abi', abi,
                           '--dest', 'directory']
        for i, package in enumerate(packages):
            assert pip.calls[i].args == expected_prefix + [package]
            assert pip.calls[i].env_vars is None
            assert pip.calls[i].shim is None

    def test_download_wheels_no_wheels(self, pip_runner):
        pip, runner = pip_runner
        runner.download_manylinux_wheels([], 'directory')
        assert len(pip.calls) == 0

    def test_raise_no_such_package_error(self, pip_runner):
        pip, runner = pip_runner
        pip.add_return((1, (b'Could not find a version that satisfies the '
                            b'requirement BadPackageName ')))
        with pytest.raises(NoSuchPackageError) as einfo:
            runner.download_all_dependencies('requirements.txt', 'directory')
        assert str(einfo.value) == ('Could not satisfy the requirement: '
                                    'BadPackageName')

    def test_raise_other_unknown_error_during_downloads(self, pip_runner):
        pip, runner = pip_runner
        pip.add_return((1, b'SomeNetworkingError: Details here.'))
        with pytest.raises(PackageDownloadError) as einfo:
            runner.download_all_dependencies('requirements.txt', 'directory')
        assert str(einfo.value) == 'SomeNetworkingError: Details here.'

    def test_inject_unknown_error_if_no_stderr(self, pip_runner):
        pip, runner = pip_runner
        pip.add_return((1, None))
        with pytest.raises(PackageDownloadError) as einfo:
            runner.download_all_dependencies('requirements.txt', 'directory')
        assert str(einfo.value) == 'Unknown error'


class TestSdistMetadataFetcher(object):
    _SETUPTOOLS = 'from setuptools import setup'
    _DISTUTILS = 'from distutils.core import setup'
    _BOTH = (
        'try:\n'
        '    from setuptools import setup\n'
        'except ImportError:\n'
        '    from distutils.core import setuptools\n'
    )

    _SETUP_PY = (
        '%s\n'
        'setup(\n'
        '    name="%s",\n'
        '    version="%s"\n'
        ')\n'
    )

    def _write_fake_sdist(self, setup_py, directory, ext):
        filename = 'sdist.%s' % ext
        path = '%s/%s' % (directory, filename)
        if ext == 'zip':
            with zipfile.ZipFile(path, 'w',
                                 compression=zipfile.ZIP_DEFLATED) as z:
                z.writestr('sdist/setup.py', setup_py)
        else:
            with tarfile.open(path, 'w:gz') as tar:
                tarinfo = tarfile.TarInfo('sdist/setup.py')
                tarinfo.size = len(setup_py)
                tar.addfile(tarinfo, io.BytesIO(setup_py.encode()))
        filepath = os.path.join(directory, filename)
        return filepath

    def test_setup_tar_gz(self, osutils, sdist_reader):
        setup_py = self._SETUP_PY % (
            self._SETUPTOOLS, 'foo', '1.0'
        )
        with osutils.tempdir() as tempdir:
            filepath = self._write_fake_sdist(setup_py, tempdir, 'tar.gz')
            name, version = sdist_reader.get_package_name_and_version(
                filepath)
        assert name == 'foo'
        assert version == '1.0'

    def test_setup_tar_gz_hyphens_in_name(self, osutils, sdist_reader):
        # The whole reason we need to use the egg info to get the name and
        # version is that we cannot deterministically parse that information
        # from the filenames themselves. This test puts hyphens in the name
        # and version which would break a simple ``split("-")`` attempt to get
        # that information.
        setup_py = self._SETUP_PY % (
            self._SETUPTOOLS, 'foo-bar', '1.0-2b'
        )
        with osutils.tempdir() as tempdir:
            filepath = self._write_fake_sdist(setup_py, tempdir, 'tar.gz')
            name, version = sdist_reader.get_package_name_and_version(
                filepath)
        assert name == 'foo-bar'
        assert version == '1.0-2b'

    def test_setup_zip(self, osutils, sdist_reader):
        setup_py = self._SETUP_PY % (
            self._SETUPTOOLS, 'foo', '1.0'
        )
        with osutils.tempdir() as tempdir:
            filepath = self._write_fake_sdist(setup_py, tempdir, 'zip')
            name, version = sdist_reader.get_package_name_and_version(
                filepath)
        assert name == 'foo'
        assert version == '1.0'

    def test_distutil_tar_gz(self, osutils, sdist_reader):
        setup_py = self._SETUP_PY % (
            self._DISTUTILS, 'foo', '1.0'
        )
        with osutils.tempdir() as tempdir:
            filepath = self._write_fake_sdist(setup_py, tempdir, 'tar.gz')
            name, version = sdist_reader.get_package_name_and_version(
                filepath)
        assert name == 'foo'
        assert version == '1.0'

    def test_distutil_zip(self, osutils, sdist_reader):
        setup_py = self._SETUP_PY % (
            self._DISTUTILS, 'foo', '1.0'
        )
        with osutils.tempdir() as tempdir:
            filepath = self._write_fake_sdist(setup_py, tempdir, 'zip')
            name, version = sdist_reader.get_package_name_and_version(
                filepath)
        assert name == 'foo'
        assert version == '1.0'

    def test_both_tar_gz(self, osutils, sdist_reader):
        setup_py = self._SETUP_PY % (
            self._BOTH, 'foo-bar', '1.0-2b'
        )
        with osutils.tempdir() as tempdir:
            filepath = self._write_fake_sdist(setup_py, tempdir, 'tar.gz')
            name, version = sdist_reader.get_package_name_and_version(
                filepath)
        assert name == 'foo-bar'
        assert version == '1.0-2b'

    def test_both_zip(self, osutils, sdist_reader):
        setup_py = self._SETUP_PY % (
            self._BOTH, 'foo', '1.0'
        )
        with osutils.tempdir() as tempdir:
            filepath = self._write_fake_sdist(setup_py, tempdir, 'zip')
            name, version = sdist_reader.get_package_name_and_version(
                filepath)
        assert name == 'foo'
        assert version == '1.0'

    def test_bad_format(self, osutils, sdist_reader):
        setup_py = self._SETUP_PY % (
            self._BOTH, 'foo', '1.0'
        )
        with osutils.tempdir() as tempdir:
            filepath = self._write_fake_sdist(setup_py, tempdir, 'tar.gz2')
            with pytest.raises(InvalidSourceDistributionNameError):
                name, version = sdist_reader.get_package_name_and_version(
                    filepath)


class TestIgnore(object):
    _FILES = [
        'foo.jpg',
        'bar.jpg',
        'foo.png',
        'bar.png',
        'foo.tiff',
        'bar.tiff',
        'nested/foo.jpg',
        'nested/bar.png',
        'deeply/nested/foo.jpg',
        'deeply/nested/bar.png',
    ]

    def test_no_file_makes_no_ignore_rules(self, osutils):
        ignore = ChaliceIgnore('.chaliceignore', osutils)
        assert ignore._ignore_rules == []

    def test_can_ignore_file_ext(self, mem_osutils):
        mem_osutils.set_file_contents('.chaliceignore',
                                      '*.jpg', binary=False)
        ignore = ChaliceIgnore('.chaliceignore', mem_osutils)
        ignored = [filename for filename in self._FILES
                   if ignore.match(filename)]
        assert ignored == ['foo.jpg', 'bar.jpg', 'nested/foo.jpg',
                           'deeply/nested/foo.jpg']

    def test_can_ignore_multiple_file_exts(self, mem_osutils):
        mem_osutils.set_file_contents('.chaliceignore',
                                      '*.jpg\n*.png', binary=False)
        ignore = ChaliceIgnore('.chaliceignore', mem_osutils)
        ignored = [filename for filename in self._FILES
                   if ignore.match(filename)]
        assert ignored == ['foo.jpg', 'bar.jpg', 'foo.png', 'bar.png',
                           'nested/foo.jpg', 'nested/bar.png',
                           'deeply/nested/foo.jpg', 'deeply/nested/bar.png']

    def test_can_ingore_nested_files(self, mem_osutils):
        mem_osutils.set_file_contents('.chaliceignore',
                                      'nested/**', binary=False)
        ignore = ChaliceIgnore('.chaliceignore', mem_osutils)
        ignored = [filename for filename in self._FILES
                   if ignore.match(filename)]
        assert ignored == ['nested/foo.jpg', 'nested/bar.png']


    def test_bang_does_invert_rules(self, mem_osutils):
        mem_osutils.set_file_contents('.chaliceignore',
                                      '!*.jpg', binary=False)
        ignore = ChaliceIgnore('.chaliceignore', mem_osutils)
        ignored = [filename for filename in self._FILES
                   if ignore.match(filename)]
        # Make sure there are no jpegs in our included files.
        for ignored_file in ignored:
            assert ignored_file.endswith('.jpg') is False
