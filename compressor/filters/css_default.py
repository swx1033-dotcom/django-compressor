import os
import re
import posixpath

from compressor.cache import get_hashed_mtime, get_hashed_content
from compressor.conf import settings
from compressor.filters import FilterBase, FilterError

URL_PATTERN = re.compile(
    r"""
    url\(
    \s*      # any amount of whitespace
    ([\'"]?) # optional quote
    (.*?)    # any amount of anything, non-greedily (this is the actual url)
    \1       # matching quote (or nothing if there was none)
    \s*      # any amount of whitespace
    \)""",
    re.VERBOSE,
)
SRC_PATTERN = re.compile(r'src=([\'"])(.*?)\1')
COMBINED_PATTERN = re.compile(
    r"""
    (?:url\(\s*([\'"]?)(.*?)\1\s*\)) | (?:src=([\'"])(.*?)\3)
""",
    re.VERBOSE,
)
SCHEMES = ("http://", "https://", "/")


class CssAbsoluteFilter(FilterBase):

    run_with_compression_disabled = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.root = settings.COMPRESS_ROOT
        self.url = settings.COMPRESS_URL.rstrip("/")
        self.url_path = self.url
        self.has_scheme = False
        self._url_cache = {}
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
        return COMBINED_PATTERN.sub(self._combined_converter, self.content)

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

        if settings.COMPRESS_CSS_SKIP_FILE_EXISTS_CHECK:
            result = filename
        else:
            result = os.path.exists(filename) and filename

        self._filename_cache[url] = result
        return result

    def add_suffix(self, url):
        filename = self.guess_filename(url)
        if not filename:
            return url
        if settings.COMPRESS_CSS_HASHING_METHOD is None:
            return url
        if not url.startswith(SCHEMES):
            return url

        suffix = None
        if settings.COMPRESS_CSS_HASHING_METHOD == "mtime":
            suffix = get_hashed_mtime(filename)
        elif settings.COMPRESS_CSS_HASHING_METHOD in ("hash", "content"):
            suffix = get_hashed_content(filename)
        else:
            raise FilterError(
                "COMPRESS_CSS_HASHING_METHOD is configured "
                "with an unknown method (%s)." % settings.COMPRESS_CSS_HASHING_METHOD
            )
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

    def _converter(self, url):
        if url in self._url_cache:
            return self._url_cache[url]

        if url.startswith(("#", "data:")):
            result = url
        elif url.startswith(SCHEMES):
            result = self.add_suffix(url)
        else:
            full_url = posixpath.normpath("/".join([str(self.directory_name), url]))
            if self.has_scheme:
                full_url = "%s%s" % (self.protocol, full_url)
            full_url = self.add_suffix(full_url)
            result = self.post_process_url(full_url)

        self._url_cache[url] = result
        return result

    def post_process_url(self, url):
        return url

    def _combined_converter(self, matchobj):
        url_match = matchobj.group(2)
        if url_match is not None:
            quote = matchobj.group(1)
            converted_url = self._converter(url_match)
            return "url(%s%s%s)" % (quote, converted_url, quote)
        else:
            quote = matchobj.group(3)
            url_match = matchobj.group(4)
            converted_url = self._converter(url_match)
            return "src=%s%s%s" % (quote, converted_url, quote)


class CssRelativeFilter(CssAbsoluteFilter):
    """
    Do similar to ``CssAbsoluteFilter`` URL processing
    but add a *relative URL prefix* instead of ``settings.COMPRESS_URL``.
    """

    run_with_compression_disabled = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._relative_re = None
        self._relative_new_prefix = None

    def _ensure_relative_setup(self):
        if self._relative_re is not None:
            return
        old_prefix = self.url
        if self.has_scheme:
            old_prefix = "{}{}".format(self.protocol, old_prefix)
        self._relative_re = re.compile("^{}".format(re.escape(old_prefix)))

        new_prefix = ".."
        new_prefix += "/.." * len(
            list(
                filter(
                    None, os.path.normpath(settings.COMPRESS_OUTPUT_DIR).split(os.sep)
                )
            )
        )
        self._relative_new_prefix = new_prefix

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
        self._ensure_relative_setup()
        return self._relative_re.sub(self._relative_new_prefix, url)
