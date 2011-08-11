from urlparse import urlparse
from httplib import HTTPConnection, HTTPSConnection
import urllib
import re


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
    return parse_link_header(header)[link]

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

    def __init__(self, url, domain_hint = None):
        self.url = url
        self.domain_hint = domain_hint

    def get(self, params = {}, headers = {}):
        location = urlparse(self.url)
        if location.scheme == 'http':
            connection = HTTPConnection(location.netloc or self.domain_hint)
        elif location.scheme == 'https':
            connection = HTTPSConnection(location.netloc or self.domain_hint)
        else:
            raise NotImplemented
        connection.request('GET', format_path(location, params), headers = headers)
        return connection.getresponse()
    
    def __getattr__(self, link):
        """
        Retrieve the resource, and follow the appropriate link
        """
        response = self.get()
        return Service(find_link(link, response), self.domain_hint)
