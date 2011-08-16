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

encoding_re = re.compile("charset\s*=\s*(\S+?)(;|$)")
def encoding_from_content_type(content_type):
    """
    Extracts the charset from a Content-Type header.

    >>> encoding_from_content_type('text/html; charset=utf-8')
    'utf-8'
    >>> encoding_from_content_type('text/html')
    >>>
    """

    if not content_type:
        return None
    match = encoding_re.search(content_type)
    return match and match.group(1) or None

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

    def __init__(self, url, filter = None, namespaces = {}, persistent_headers = {}):
        self.filter = filter
        self.namespaces = namespaces
        self.persistent_headers = persistent_headers
        self.url = url

    def get(self, params = {}, headers = {}):
        location = urlparse(self.url)


        if location.scheme == 'http':
            connection = HTTPConnection(location.netloc)
        elif location.scheme == 'https':
            connection = HTTPSConnection(location.netloc)
        else:
            raise NotImplementedError('Only HTTP and HTTPS are supported')
        headers = dict(headers.items() + self.persistent_headers.items())
        connection.request('GET', format_path(location, params), headers = headers)
        resp = connection.getresponse()
        return Representation.factory(resp, self)

    def find(self, xpath):
      return Service(self.url, filter=xpath, persistent_headers=self.persistent_headers, namespaces=self.namespaces)

    def follow_link(self, link):
        """
        Retrieve the resource and follow the appropriate link.
        """
        response = self.get()
        link = response.find_link(link, self.filter)
        return Service(absolute_url(link, self.url), namespaces = self.namespaces, persistent_headers = self.persistent_headers)

    __getattr__ = follow_link


class Representation(object):

    @staticmethod
    def mime_type(response):
        if response.getheader('Content-Type'):
            return response.getheader('Content-Type').partition(';')[0]
        else:
            return None

    @staticmethod
    def factory(response, service):
        if Representation.mime_type(response) in ['application/xml', 'application/atom+xml', 'text/xml']:
            return XMLRepresentation(response, service.namespaces)
        else:
            return Representation(response)

    def __init__(self, response):
        self.response = response
        self.getheader = response.getheader
        self.getheaders = response.getheaders

        self.encoding = encoding_from_content_type(self.getheader('Content-Type'))

    def find_link(self, link, filter=None):
        header = self.getheader('Link')
        return parse_link_header(header)[link]

    def read(self, count=None):
        data = self.response.read(count)
        if self.encoding:
            return unicode(data, self.encoding)
        else:
            return data


class XMLRepresentation(Representation):

    def __init__(self, response, namespaces = {}):
        super(XMLRepresentation, self).__init__(response)
        self.parsed = etree.parse(self)
        self.namespaces = namespaces

    def xpath(self, path):
        return self.parsed.xpath(path, namespaces = self.namespaces)

    def find_link(self, link, filter=None):
        try:
            super(XMLRepresentation, self).find_link(link)
        except KeyError:
            xml = [self.parsed]
            if filter:
                xml = self.xpath(filter)
            else:
                xml = [self]
            result = []
            for node in xml:
                # what's the right way to handle namespaces here?
                result.extend(node.xpath('//*[local-name()="link" and @rel="%s"]/@href' % link))
            return result[0]
