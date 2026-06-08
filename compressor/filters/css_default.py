import os
import re
import posixpath
from functools import lru_cache

from compressor.cache import get_hashed_mtime, get_hashed_content
from compressor.conf import settings
from compressor.filters import FilterBase, FilterError

SCHEMES = ("http://", "https://", "/")


@lru_cache(maxsize=1)
def get_resource_pattern():
    return re.compile(
        r"""
        (?P<url>
            url\(
            \s*
            (?P<url_quote>[\'"]?)
            (?P<url_value>.*?)
            (?P=url_quote)
            \s*
            \)
        )
        |
        (?P<src>
            src=
            (?P<src_quote>[\'"])
            (?P<src_value>.*?)
            (?P=src_quote)
        )
        """,
        re.VERBOSE,
    )


class CssAbsoluteFilter(FilterBase):

    run_with_compression_disabled = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root = settings.COMPRESS_ROOT
        self.url = settings.COMPRESS_URL.rstrip("/")
        self.url_path = self.url
        self.has_scheme = False
        self.strict_path_checks = (
            settings.COMPRESS_CSS_ABSOLUTE_FILTER_STRICT_PATH_CHECKS
        )
        self._converted_url_cache = {}
        self._resolved_relative_url_cache = {}
        self._filename_cache = {}

    def input(self, filename=None, basename=None, **kwargs):
        if not filename:
            return self.content
        self.path = basename.replace(os.sep, "/")
        self.path = self.path.lstrip("/")
        if self.url.startswith(("http://", "https://")):
            self.has_scheme = True
            parts = self.url.split("/")
            self.url = "/".join(parts[2:])
            self.url_path = "/%s" % "/".join(parts[3:])
            self.protocol = "%s/" % "/".join(parts[:2])
            self.host = parts[2]
        self.directory_name = "/".join((self.url, os.path.dirname(self.path)))
        return get_resource_pattern().sub(self.resource_converter, self.content)

    def guess_filename(self, url):
        if url in self._filename_cache:
            return self._filename_cache[url]

        local_path = url
        if self.has_scheme:
            local_path = local_path.replace(self.protocol + self.host, "", 1)
        local_path = local_path.rsplit("#", 1)[0]
        local_path = local_path.rsplit("?", 1)[0]
        if local_path.startswith(self.url_path):
            local_path = local_path.replace(self.url_path, "", 1)
        filename = os.path.join(self.root, local_path.lstrip("/"))
        if self.strict_path_checks and not os.path.exists(filename):
            filename = None
        self._filename_cache[url] = filename
        return filename

    def get_hash_suffix(self, filename, hashing_method):
        try:
            if hashing_method == "mtime":
                return get_hashed_mtime(filename)
            if hashing_method in ("hash", "content"):
                return get_hashed_content(filename)
        except OSError:
            return None
        raise FilterError(
            "COMPRESS_CSS_HASHING_METHOD is configured "
            "with an unknown method (%s)." % hashing_method
        )

    def add_suffix(self, url):
        hashing_method = settings.COMPRESS_CSS_HASHING_METHOD
        if hashing_method is None:
            return url
        if not url.startswith(SCHEMES):
            return url

        filename = self.guess_filename(url)
        if not filename:
            return url

        suffix = self.get_hash_suffix(filename, hashing_method)
        if not suffix:
            return url

        fragment = None
        if "#" in url:
            url, fragment = url.rsplit("#", 1)
        if "?" in url:
            url = "%s&%s" % (url, suffix)
        else:
            url = "%s?%s" % (url, suffix)
        if fragment is not None:
            url = "%s#%s" % (url, fragment)
        return url

    def _resolve_relative_url(self, url):
        if url not in self._resolved_relative_url_cache:
            full_url = posixpath.normpath("/".join([str(self.directory_name), url]))
            if self.has_scheme:
                full_url = "%s%s" % (self.protocol, full_url)
            self._resolved_relative_url_cache[url] = full_url
        return self._resolved_relative_url_cache[url]

    def _converter(self, url):
        if url in self._converted_url_cache:
            return self._converted_url_cache[url]

        if url.startswith(("#", "data:")):
            converted_url = url
        elif url.startswith(SCHEMES):
            converted_url = self.add_suffix(url)
        else:
            full_url = self._resolve_relative_url(url)
            converted_url = self.post_process_url(self.add_suffix(full_url))

        self._converted_url_cache[url] = converted_url
        return converted_url

    def post_process_url(self, url):
        """
        Extra URL processing, to be overridden in subclasses.
        """
        return url

    def resource_converter(self, matchobj):
        if matchobj.group("url") is not None:
            quote = matchobj.group("url_quote")
            converted_url = self._converter(matchobj.group("url_value"))
            return "url(%s%s%s)" % (quote, converted_url, quote)

        quote = matchobj.group("src_quote")
        converted_url = self._converter(matchobj.group("src_value"))
        return "src=%s%s%s" % (quote, converted_url, quote)


class CssRelativeFilter(CssAbsoluteFilter):
    """
    Do similar to ``CssAbsoluteFilter`` URL processing
    but add a *relative URL prefix* instead of ``settings.COMPRESS_URL``.
    """

    run_with_compression_disabled = True

    def post_process_url(self, url):
        """
        Replace ``settings.COMPRESS_URL`` URL prefix with  '../' * (N + 1)
        where N is the *depth* of ``settings.COMPRESS_OUTPUT_DIR`` folder.

        E.g. by default ``settings.COMPRESS_OUTPUT_DIR == 'CACHE'``,
        the depth is 1, and the prefix will be '../../'.

        If ``settings.COMPRESS_OUTPUT_DIR == 'my/compiled/data'``,
        the depth is 3, and the prefix will be '../../../../'.

        Example:

        - original file URL: '/static/my-app/style.css'
        - it has an image link: ``url(images/logo.svg)``
        - compiled file URL: '/static/CACHE/css/output.abcdef123456.css'
        - replaced image link URL: ``url(../../my-app/images/logo.svg)``
        """
        old_prefix = self.url
        if self.has_scheme:
            old_prefix = "{}{}".format(self.protocol, old_prefix)
        new_prefix = ".."
        new_prefix += "/.." * len(
            list(
                filter(
                    None, os.path.normpath(settings.COMPRESS_OUTPUT_DIR).split(os.sep)
                )
            )
        )
        return re.sub("^{}".format(old_prefix), new_prefix, url)
