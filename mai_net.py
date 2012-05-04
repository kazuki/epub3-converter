#!/usr/bin/python3
# -*- coding: utf-8 -*-

from epub import *
from style import *
import lxml.html, math, sys, datetime, uuid, functools

class MaiNet:
    class PostData:
        def __init__(self):
            self.title  = None
            self.body   = None
            self.author = None
            self.date   = None
    def __parse(self, tree):
        posts = []
        def ParseBody(root):
            body = ''
            for e in root.iter():
                if e.text is not None: body += e.text
                if e.tag == 'br': body += '\n'
                if e.tail is not None: body += e.tail
            return body

        cur = MaiNet.PostData()
        for e in tree.iter():
            if e.tag == 'td':
                if 'class' not in e.attrib: continue
                if e.attrib['class'] == 'bgb':
                    cur.title = e.find('font').text.rstrip()
                if e.attrib['class'] == 'bgc':
                    t = e.find('tt').text[6:].strip()
                    cur.author = e.find('table').find('tr').find('td').find('tt').text[6:].strip()
                    cur.date   = datetime.datetime(int(t[0:4]), int(t[5:7]), int(t[8:10]), int(t[11:13]),
                                                   int(t[14:16]), tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
                    cur.body   = ParseBody(e.find('blockquote').find('div'))
                    if '◆' in cur.author: cur.author = cur.author[0:cur.author.find('◆')]
                    posts.append(cur)
                    cur = MaiNet.PostData()
        return posts

    def __process_cover(self, title, author, css_file):
        writer = SimpleXMLWriter()
        writer.doc_type = '<!DOCTYPE html>'
        writer.start('html', atts={'xmlns':'http://www.w3.org/1999/xhtml', 'xml:lang':'ja'})
        writer.start('head')
        writer.element('title', text=title)
        if css_file is not None:
            writer.element('link', atts={'rel':'stylesheet', 'type':'text/css', 'href':css_file})
        writer.end()
        writer.start('body')
        writer.element('h1', atts={'class':'cover title'}, text=title)
        writer.element('h2', atts={'class':'cover author'}, text='作者:')
        writer.element('p', text=author)
        return str(writer)

    def __create_page(self, title, body, title_tagname, css_file):
        writer = SimpleXMLWriter()
        writer.doc_type = '<!DOCTYPE html>'
        writer.start('html', atts={'xmlns':'http://www.w3.org/1999/xhtml', 'xml:lang':'ja'})
        writer.start('head')
        writer.element('title', text=title)
        if css_file is not None:
            writer.element('link', atts={'rel':'stylesheet', 'type':'text/css', 'href':css_file})
        writer.end()
        writer.start('body')
        if title_tagname is not None:
            writer.element(title_tagname, text=title)
        for line in body.split('\n'):
            writer.element('p', text=line.strip())
        writer.end()
        return str(writer)

    def __call__(self, content_id, css_map, package):
        tree = lxml.html.parse('http://www.mai-net.net/bbs/sst/sst.php?act=all_msg&cate=&all=' + content_id)
        posts = self.__parse(tree)
        if len(posts) == 0: raise Exception()

        meta = package.metadata
        meta.add_title(posts[0].title, lang='ja')
        meta.add_language('ja')
        meta.add_identifier(str(uuid.uuid4()), unique_id=True)
        meta.add_modified(functools.reduce(lambda x,y: x if x.date > y.date else y, posts).date)
        meta.add_dcmes_info(DCMESDateInfo(datetime.datetime.utcnow()))
        meta.add_dcmes_info(DCMESCreatorInfo(posts[0].author, lang='ja'))

        package.manifest.add_item('cover.xhtml', 'application/xhtml+xml',
                                  self.__process_cover(posts[0].title, posts[0].author, css_map.cover_css()).encode('UTF-8'))
        css_map.output(package.manifest)

        autoid = 0
        id_width = math.ceil(math.log10(len(posts)))
        nav = EPUBNav('toc', '目次', 'ja', css_map.toc_css())
        for post in posts[1:]:
            filename = str(autoid).zfill(id_width)
            autoid += 1
            nav.add_child(post.title, filename)
            data = self.__create_page(post.title, post.body, 'h2', css_map.page_css()).encode('UTF-8')
            package.manifest.add_item(filename, 'application/xhtml+xml', data)

        compatible_toc = EPUBCompatibleNav([nav], package.metadata, package.manifest)
        package.manifest.add_item('toc.ncx', 'application/x-dtbncx+xml',
                                  str(compatible_toc).encode('UTF-8'), is_toc=True)
        package.manifest.add_item('toc.xhtml', 'application/xhtml+xml', nav.to_xml().encode('UTF-8'),
                                  spine_pos=package.manifest.find_spine_pos('cover.xhtml') + 1, properties='nav')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: %s [code]' % (sys.argv[0],))
        quit()

    css_map = StylesheetMap(('style.css', SimpleVerticalWritingStyle))
    package = EPUBPackage()
    package.spine.set_direction('rtl')
    MaiNet()(sys.argv[1], css_map, package)
    package.save(sys.argv[1] + '.epub')
