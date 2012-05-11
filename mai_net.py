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

    def __call__(self, package, css_file, content_id):
        tree = lxml.html.parse('http://www.mai-net.net/bbs/sst/sst.php?act=all_msg&cate=&all=' + content_id)
        posts = self.__parse(tree)
        if len(posts) == 0: raise Exception()

        meta = package.metadata
        meta.add_title(posts[0].title, lang='ja')
        meta.add_language('ja')
        meta.add_identifier(str(uuid.uuid4()), unique_id=True)
        meta.add_modified(functools.reduce(lambda x,y: x if x.date > y.date else y, posts).date)
        meta.add_date(datetime.datetime.utcnow())
        meta.add_creator(posts[0].author, lang='ja')

        add_simple_cover(package.manifest, posts[0].title, posts[0].author, css_file=css_map.cover_css())
        css_map.output(package.manifest)

        autoid = 0
        id_width = math.ceil(math.log10(len(posts)))
        nav = EPUBNav('toc', '目次', 'ja', css_map.toc_css())
        for post in posts[1:]:
            filename = str(autoid).zfill(id_width) + '.xhtml'
            autoid += 1
            nav.add_child(post.title, filename)
            data = create_simple_page(post.title, 'h2', css_map.page_css(), post.body.split('\n'))
            package.manifest.add_item(filename, data)

        compatible_toc = EPUBCompatibleNav([nav], package.metadata, package.manifest)
        package.manifest.add_item('toc.ncx', str(compatible_toc), is_toc=True)
        package.manifest.add_item('toc.xhtml', nav.to_xml(), properties='nav',
                                  spine_pos=package.manifest.find_spine_pos('cover.xhtml') + 1)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: %s [code]' % (sys.argv[0],))
        quit()

    converter = MaiNet()
    content_id = sys.argv[1]

    css_map = StylesheetMap(('style.css', SimpleVerticalWritingStyle))
    package = EPUBPackage()
    package.spine.set_direction('rtl')
    converter(package, css_map, content_id)
    package.save(content_id + '.epub')
