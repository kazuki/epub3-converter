#!/usr/bin/python3
# -*- coding: utf-8 -*-

import io, sys, os.path, urllib.parse
from urllib.parse import parse_qs, urlparse

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import syosetu_com, mai_net, epub, style
from cache import SimpleCache

class SimpleGW:
    SYOSETU_COM = 'syosetu.com'
    MAI_NET = 'mai-net.net'

    def __init__(self):
        self.cache = SimpleCache()
        self.service_map = {
            SimpleGW.SYOSETU_COM: syosetu_com.SyosetuCom(cache=self.cache),
            SimpleGW.MAI_NET: mai_net.MaiNet(cache=self.cache)
        }

    def __call__(self, environ, start_response):
        qs = parse_qs(environ['QUERY_STRING'])
        if 'url' in qs:
            return self.ConvertFromURL(qs['url'][0], environ, start_response)
        if 's' in qs and 'n' in qs:
            return self.Convert(qs['s'][0], qs['n'][0], environ, start_response)

        mime_type = 'application/xhtml+xml'
        if mime_type not in environ.get('HTTP_ACCEPT', ''):
            mime_type = 'text/html'
        start_response('200 OK', [('Content-Type', mime_type + '; charset=UTF-8')])
        contents = """<!DOCTYPE html>
<html xmlns="http://www.w3.org/1999/xhtml"><head><meta charset="UTF-8" /><title>ePub3 Converter</title></head><body>
<h1 style="font-size:x-large">ePub3 Converter</h1>
<p>下記のサイトで公開されている小説等をePub3形式に変換します．</p>
<ul>
<li><a href="http://syosetu.com/" target="_blank">小説家になろう</a></li>
<li><a href="http://www.mai-net.net/" target="_blank">Arcadia</a></li>
</ul>
<h2 style="font-size:large">URLからePub3に変換</h2>
<span>URL:</span>
<form method="GET" target="_blank" style="display:inline">
<input type="text" size="60" name="url" />
<input type="submit" value="変換" />
</form>

<div style="border-top: 1px solid black; margin-top: 3em;font-size:small">
<h2 style="font-size:medium;">ブックマークレット</h2>
<p><a href="javascript:location.href%3D%22http%3A%2F%2Foikw.org%2Fepub3-converter%2F%3Furl%3D%22%2BencodeURIComponent%28location.href%29%3B">ブックマークレット</a></p>
<h2 style="font-size:medium">ソースコードや不具合等の報告</h2>
<p>ePub3変換プログラムのソースコードや，このサイトを構成するプログラム等は<a href="https://github.com/kazuki/epub3-converter" target="_blank">GitHub</a>にて公開しています．</p>
<p>不具合等を見つけましたら<a href="https://github.com/kazuki/epub3-converter/issues" target="_blank">GitHubのバグ報告ページ</a>または，Twitter(@k_oi)，メール(k at oikw.org)へ報告すると，気が向いたときに修正するかもしれません．</p></div>
</body></html>"""
        return [contents.encode('UTF-8')]

    def ConvertFromURL(self, url, environ, start_response):
        url = urlparse(url)
        service_name = None
        code = None
        if url.hostname.endswith('.syosetu.com'):
            service_name = SimpleGW.SYOSETU_COM
            if url.path.startswith('/n'):
                code = url.path[1:]
                if code.find('/') > 0:
                    code = code[0:code.find('/')]
        elif url.hostname == 'www.mai-net.net':
            service_name = SimpleGW.MAI_NET
            code = parse_qs(url.query).get('all')[0]
        return self.Convert(service_name, code, environ, start_response)
        
    def Convert(self, service_name, code, environ, start_response):
        try:
            converter = self.service_map.get(service_name)
            if converter is None or code is None:
                raise 'argument error'

            css_map = style.StylesheetMap(('style.css', style.SimpleVerticalWritingStyle))
            package = epub.EPUBPackage()
            package.spine.set_direction('rtl')

            converter(package, css_map, code)
            bio = io.BytesIO()
            package.save(bio)

            filename = package.metadata.get_dcmes_text('title')
            if filename is None: filename = str(code)
            filename += '.epub'
            filename = "utf-8'en'" + urllib.parse.quote(filename, encoding='utf-8', errors='replace')
            epub_binary = bio.getvalue()
            start_response('200 OK', [('Content-Type', 'application/epub+zip'),
                                      ('Content-Length', str(len(epub_binary))),
                                      ('Content-Disposition', 'attachment; filename*="' + filename + '"')])
            return [epub_binary]
        except:
            start_response('500 Internel Server Error', [('Content-Type', 'text/plain; charset=UTF-8')])
            err_msg = '変換エラー．指定したURLが正しくないか，リモートサーバへのアクセスに失敗しました．\n'
            err_msg += '再度試行してもエラーとなる場合は，作者まで変換できないURLを報告してください．'
            return [err_msg.encode('UTF-8')]

application = SimpleGW()

if __name__ == '__main__':
    from wsgiref.simple_server import make_server
    httpd = make_server('', 8080, application)
    httpd.serve_forever()
