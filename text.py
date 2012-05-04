#!/usr/bin/python3
# -*- coding: utf-8 -*-

from epub import *
from style import *
import sys, os.path, operator, math, uuid

class TextToEpub:
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

    def __create_page(self, path, title, title_tagname, css_file):
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
        for line in open(path, 'r'):
            writer.element('p', text=line.strip())
        writer.end()
        return str(writer)

    def __call__(self, title, author, filelist, css_map, package):
        def find_date_info():
            created = datetime.datetime.max
            modified = datetime.datetime.min
            for path in filelist:
                if not os.path.isfile(path): continue
                s = os.stat(path)
                c = datetime.datetime.utcfromtimestamp(s.st_ctime)
                m = datetime.datetime.utcfromtimestamp(s.st_mtime)
                if c < created: created = c
                if modified < m: modified = m
            return (created, modified)
        meta = package.metadata
        meta.add_title(title, lang='ja')
        meta.add_language('ja')
        meta.add_identifier(str(uuid.uuid4()), unique_id=True)
        created, modified = find_date_info()
        meta.add_modified(modified)
        meta.add_date_term('created', created)
        meta.add_dcmes_info(DCMESDateInfo(datetime.datetime.utcnow()))
        meta.add_dcmes_info(DCMESCreatorInfo(author, lang='ja'))

        package.manifest.add_item('cover.xhtml', 'application/xhtml+xml',
                                  self.__process_cover(title, author, css_map.cover_css()).encode('UTF-8'))
        css_map.output(package.manifest)

        nav = EPUBNav('toc', '目次', 'ja', css_map.toc_css())
        toc_list = []
        class Entry:
            def __init__(self, path, prefix, title, levels):
                self.path = path
                self.prefix = prefix
                self.title = title
                self.levels = levels
                self.filename = None
        for x in filelist:
            items = os.path.splitext(os.path.basename(x))[0].split('_', 2)
            prefix, title, levels = items[0], items[1], items[0].split('-')
            toc_list.append(Entry(x, prefix, title, levels))
        toc_list = sorted(toc_list, key=operator.attrgetter('prefix'))

        autoid = 0
        id_width = math.ceil(math.log10(len(toc_list)))
        for entry in toc_list:
            entry.filename = str(autoid).zfill(id_width)
            autoid += 1
            nav.add_child(entry.title, entry.filename)
            data = self.__create_page(entry.path, entry.title, 'h2', css_map.page_css()).encode('UTF-8')
            package.manifest.add_item(entry.filename, 'application/xhtml+xml', data)

        compatible_toc = EPUBCompatibleNav([nav], package.metadata, package.manifest)
        package.manifest.add_item('toc.ncx', 'application/x-dtbncx+xml',
                                  str(compatible_toc).encode('UTF-8'), is_toc=True)
        package.manifest.add_item('toc.xhtml', 'application/xhtml+xml', nav.to_xml().encode('UTF-8'),
                                  spine_pos=package.manifest.find_spine_pos('cover.xhtml') + 1, properties='nav')

if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('''usage: python3 text.py [title] [author] text files...

if non-existent file attached, import title only.

Example1:
  $ python3 text.py "novel title" "novel author" 0_section1.txt 1_section2.txt

  output TOC:
    section1
    section2

Example2 (not implemented...):
  $ python3 text.py "novel title" "novel author" 00_chaptor1 00-0_section1.txt 00-1_section2.txt 01_chaptor2 01-0_section3

  output TOC:
    chaptor1
      section1
      section2
    chaptor2
      section3''')
        quit()

    title = sys.argv[1]
    author = sys.argv[2]
    filelist = sys.argv[3:]

    css_map = StylesheetMap(('style.css', SimpleVerticalWritingStyle))
    package = EPUBPackage()
    package.spine.set_direction('rtl')
    TextToEpub()(title, author, filelist, css_map, package)
    package.save(title + '.epub')
