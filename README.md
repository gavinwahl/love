# Love
Love is an experimental HATEOAS client. Retrieves HTTP(S) resources and follows links
found in them. Currently only supports the Link HTTP header.


# TODO
- Support more than HTTP GET
- Support finding links in hypertext (XML + XPath?). JSON would be nice, but
  how does hyperlinking work without hypertext?

# Goal



Given an api that looks like this:

    GET /

```xml
<links>
  <link rel="users" href="/users/"/>
  <link rel="items" href="/items/"/>
</links>
```


    GET /users/

```xml
<users>
  <user name="alice">
    <link rel="profile" href="/users/alice/"/>
  </user>
</users>
```



    GET /users/alice/

```xml
<user>
  <city>Anytown</city>
</user>
```


One should be able to write something like:

    >>> service = Service('http://example.com/')
    >>> service.users.find('//[@name="alice"]').profile.get('//city/text()')
    'Anytown'
