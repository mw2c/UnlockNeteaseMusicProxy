from twisted.internet import reactor
from twisted.web import http
from twisted.python import log
from twisted.web.proxy import Proxy, ProxyRequest, ProxyClientFactory, ProxyClient
import gzip
import StringIO
import re
import json
import datetime
import md5
import urllib2

rexPl = re.compile('"pl":\\d+')
rexDl = re.compile('"dl":\\d+')
rexSt = re.compile('"st":-?\\d+')
rexSubp = re.compile('"subp":\\d+')

null_proxy_handler = urllib2.ProxyHandler({})
opener = urllib2.build_opener(null_proxy_handler)
urllib2.install_opener(opener)

def compress(content):
    zbuf = StringIO.StringIO()
    zfile = gzip.GzipFile(mode='wb', fileobj=zbuf)
    zfile.write(content)
    zfile.close()
    return zbuf.getvalue()

def needModifyDetailApi(url):
    if "/eapi/v3/song/detail/" in url or "/eapi/v1/album/" in url or "/eapi/v3/playlist/detail" in url or "/eapi/batch" in url or "/eapi/cloudsearch/pc" in url or "/eapi/v1/artist" in url or "/eapi/v1/search/get" in url:
        return True
    return False

def needModifyPlayerApi(url):
    if "/eapi/song/enhance/player/url" in url:
        return True
    return False

def getUrl(songId, quality):
    dfsId = getDfsId(getPage("http://music.163.com/api/song/detail?id=" + songId + "&ids=[" + songId + "]"), quality)
    return generateUrl(dfsId)

def getDfsId(pageContent, quality):
    obj = json.loads(pageContent)
    if quality == "hMusic" and not obj["songs"][0].has_key("hMusic"):
        print "downgrade to medium quality"
        quality = "mMusic"
    if quality == "mMusic" and not obj["songs"][0].has_key("mMusic"):
        print "downgrade to low quality"
        quality = "lMusic"
    if quality == "lMusic" and not obj["songs"][0].has_key("lMusic"):
        print "downgrade to lowest quality"
        quality = "bMusic"
    if quality == "bMusic" and not obj["songs"][0].has_key("bMusic"):
        print "no resourse"
    return json.dumps(obj["songs"][0][quality]["dfsId"])

def generateUrl(dfsId):
    url = "http://m" + str(datetime.datetime.now().second % 2 + 1) + ".music.126.net/" + getEncId(dfsId) + "/" + dfsId + ".mp3"
    return url

def getEncId(dfsId):
    magicBytes = bytearray('3go8&$8*3*3h0k(2)2')
    songId = bytearray(dfsId)
    magicBytes_len = len(magicBytes)
    for i in xrange(len(songId)):
        songId[i] = songId[i] ^ magicBytes[i % magicBytes_len]
    m = md5.new()
    m.update(songId)
    result = m.digest().encode('base64')[:-1]
    result = result.replace('/', '_')
    result = result.replace('+', '-')
    return result

def getPage(url):
    response = urllib2.urlopen(url)
    text = response.read()
    return text

def modifyPlayerApi(str):
    obj = json.loads(str)
    songId = json.dumps(obj["data"][0]["id"])
    newUrl = getUrl(songId, "hMusic")
    obj["data"][0]["url"] = newUrl
    obj["data"][0]["br"] = "320000"
    obj["data"][0]["code"] = "200"
    return json.dumps(obj)

def modifyDetailApi(str):
    str = rexPl.sub('"pl":320000', str)
    str = rexDl.sub('"dl":320000', str)
    str = rexSt.sub('"st":0', str)
    str = rexSubp.sub('"subp":1', str)
    return str

class MitmProxyClient(ProxyClient):
    def __init__(self, *args, **kwargs):
        self.buf = ""
        self.gziped = False
        ProxyClient.__init__(self, *args, **kwargs)

    def handleHeader(self, key, value):
        if self.gziped == False and "content-encoding" in key.lower() and "gzip" in value.lower():
            self.gziped = True
        ProxyClient.handleHeader(self, key, value)

    def handleEndHeaders(self):
        ProxyClient.handleEndHeaders(self)

    def handleResponsePart(self, buffer):
        url = self.father.uri
        if needModifyPlayerApi(url) or needModifyDetailApi(url):
            self.buf += buffer
        else:
            ProxyClient.handleResponsePart(self, buffer)

    def handleResponseEnd(self):
        url = self.father.uri
        if self.gziped == True:
            temp = StringIO.StringIO(self.buf)
            s = gzip.GzipFile(fileobj=temp)
            content = s.read()
        else:
            content = self.buf
        if needModifyDetailApi(url):
            content = modifyDetailApi(content)
            if self.gziped == True:
                ProxyClient.handleResponsePart(self, compress(content))
            else:
                ProxyClient.handleResponsePart(self, content)
        elif needModifyPlayerApi(url):
            print content
            content = modifyPlayerApi(content)
            if self.gziped == True:
                ProxyClient.handleResponsePart(self, compress(content))
            else:
                ProxyClient.handleResponsePart(self, content)
        ProxyClient.handleResponseEnd(self)

class MitmProxyClientFactory(ProxyClientFactory):
    protocol = MitmProxyClient

class MitmProxyRequest(ProxyRequest):
    protocols = {'http': MitmProxyClientFactory}
    def process(self):
        ProxyRequest.process(self)

class MitmProxy(Proxy):
    requestFactory = MitmProxyRequest

factory = http.HTTPFactory()
factory.protocol = MitmProxy

reactor.listenTCP(8000, factory)
reactor.run()
