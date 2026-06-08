import re

URL_AND_SRC_PATTERN = re.compile(
    r"""
    url\(
    \s*      # any amount of whitespace
    (?P<url_quote>[\'"]?) # optional quote
    (?P<url_url>.*?)    # any amount of anything, non-greedily (this is the actual url)
    (?P=url_quote)       # matching quote (or nothing if there was none)
    \s*      # any amount of whitespace
    \)
    |
    src=
    (?P<src_quote>[\'"])  # quote
    (?P<src_url>.*?)    # url
    (?P=src_quote)       # matching quote
    """,
    re.VERBOSE,
)

def converter(matchobj):
    if matchobj.group('url_url') is not None:
        return f"url({matchobj.group('url_quote')}CONVERTED_{matchobj.group('url_url')}{matchobj.group('url_quote')})"
    elif matchobj.group('src_url') is not None:
        return f"src={matchobj.group('src_quote')}CONVERTED_{matchobj.group('src_url')}{matchobj.group('src_quote')}"

text = 'background: url("foo.png");\n filter: progid:DXImageTransform.Microsoft.AlphaImageLoader(src="bar.png");'
print(URL_AND_SRC_PATTERN.sub(converter, text))
