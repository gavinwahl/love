from urlparse import urlparse, ParseResult
from httplib import HTTPConnection, HTTPSConnection
import urllib
import re
from lxml import etree


def format_path(parsed, data = {}):
    """
    From a urlparse result, extract the path and query component, optionally
    adding some data from a dictionary

    >>> from urlparse import urlparse
    >>> format_path(urlparse('http://example.com/path'))
    '/path'
    >>> format_path(urlparse('http://example.com/path'), {'data': 'a', 'foo': 'bar'})
    '/path?foo=bar&data=a'
    >>> format_path(urlparse('http://example.com/path?query=a'), {'data': 'b'})
    '/path?query=a&data=b'
    """

    url = parsed.path
    params = []
    if parsed.query:
        params.append(parsed.query)
    if data:
        params.append(urllib.urlencode(data))
    if params:
        url += '?' + '&'.join(params)
    return url

def find_link(link, response):
    header = response.getheader('Link')
    try:
      return parse_link_header(header)[link]
    except KeyError:
      # not in the header
      encoding = encoding_from_content_type(response.getheader('Content-Type'))
      xml = etree.parse(response.read(), encoding = encoding)
      return xml.xpath('//link[@rel="%s"]/@href' % link)

encoding_re = re.compile("charset\s*=\s*(\S+)(;|$)")
def encoding_from_content_type(content_type):
    if not content_type:
        return None
    match = encoding_re.match(content_type)
    if match:
        return match.group(1)
    else:
        return None

link_re = re.compile('\s*<([^>]+)>;\s*rel\s*="([^"]+)"')
def parse_link_header(header):
    """
    RFC 5988 parsing

    >>> parse_link_header('</foo>; rel="first", </bar>; rel="last";')
    {'last': '/bar', 'first': '/foo'}
    """
    res = {}
    if not header:
        return res
    pieces = header.split(',')
    for piece in pieces:
        match = link_re.match(piece)
        res[match.group(2)] = match.group(1)
    return res


def absolute_url(relative, base):
    base = urlparse(base)
    relative = urlparse(relative)

    scheme = relative.scheme or base.scheme
    netloc = relative.netloc or base.netloc

    if not relative.path.startswith('/'):
        path = base.path + "/" + relative.path
    else:
        path = relative.path

    return ParseResult(scheme=scheme, netloc=netloc, path=path, params=relative.params, query=relative.query, fragment=relative.fragment).geturl()

class Service(object):
    """
    Represents a HATEOAS endpoint. Follows links by attribute access.

    >>> gists = Service('https://api.github.com/gists')
    >>> gists.get().read().startswith('[{')
    True
    >>> gists.next.get().read().startswith('[{')
    True
    >>> gists.next.url == gists.next.next.prev.url
    True
    """

    def __init__(self, url, filter = None):
        self.url = url
        self.filter = filter

    def get(self, params = {}, headers = {}, path = None, namespaces = {}):
        location = urlparse(self.url)

        if location.scheme == 'http':
            connection = HTTPConnection(location.netloc or self.domain_hint)
        elif location.scheme == 'https':
            connection = HTTPSConnection(location.netloc or self.domain_hint)
        else:
            raise NotImplementedError('Only HTTP and HTTPS are supported')
        connection.request('GET', format_path(location, params), headers = headers)
        resp = connection.getresponse()
        if path:
            return etree.parse(resp).xpath(path, namespaces = namespaces)
        else:
            return resp

    def find(self, xpath):
      return Service(self.url, filter=xpath)

    def find_link(self, link, response):
        header = response.getheader('Link')
        try:
          return parse_link_header(header)[link]
        except KeyError:
          # not in the header
          xml = [etree.parse(response)]
          if self.filter:
              xml = xml[0].xpath(self.filter)
          result = []
          for node in xml:
              # what's the right way to handle namespaces here?
              result.extend(node.xpath('//*[local-name()="link" and @rel="%s"]/@href' % link))
          return result[0]


    def follow_link(self, link):
        """
        Retrieve the resource, and follow the appropriate link
        """
        response = self.get()
        link = self.find_link(link, response)
        return Service(absolute_url(link, self.url))

    __getattr__ = follow_link
