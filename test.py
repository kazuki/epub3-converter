#!/usr/bin/python3
# -*- coding: utf-8 -*-

from epub import *
import lxml.html, math, sys, urllib.request, re

class SyosetuCom:
    image_url_regex = re.compile('[^0-9]*([0-9]+)\..*/icode/(i[0-9a-zA-Z]+)')
    def __get_all_text(self, node):
        text = ''
        for n in node.iter():
            if n.text is not None: text += n.text
            if n.tail is not None: text += n.tail
        return text.strip()
    def __get_metadata(self, ncode):
        '''
        return (title, author, description, keywords[space-separated],
                start-date, last modified, type[連載,短編], completed_flag)
        '''
        info_page = lxml.html.parse('http://ncode.syosetu.com/novelview/infotop/ncode/' + ncode)
        prev_caption = None
        title, author, description, keywords, start_date, last_modified = None, None, None, None, None, None
        novel_type, complete_flag = None, True

        for td in info_page.iter('td'):
            if 'class' in td.attrib and td.attrib['class'] in ('h1', 'h_l'):
                prev_caption = td.text
                continue
            author_a = td.find('div/a')
            title_a = td.find('div/strong/a')
            if author_a is not None: author = author_a.text.strip()
            if title_a is not None:  title = title_a.text.strip()
            if prev_caption is None: continue
            elif prev_caption == 'あらすじ': description = self.__get_all_text(td)
            elif prev_caption == 'キーワード': keywords = td.find('div').text.strip()
            elif prev_caption == '掲載日': start_date = td.text.strip()
            elif prev_caption.startswith('最終'): last_modified = td.text.strip()
            elif prev_caption == '種別':
                novel_type = td.text.strip()
                if novel_type.startswith('連載'): complete_flag = False
                if novel_type != '短編': novel_type = '連載'
        return (title, author, description, keywords, start_date, last_modified, novel_type, complete_flag)

    def __process_image(self, url):
        '''return (filename, mime, bytes)'''
        m = self.image_url_regex.match(url)
        filename = m.group(1) + '_' + m.group(2)
        with urllib.request.urlopen(url) as f:
            mime = f.info()['Content-Type']
            if mime == 'image/gif': filename += '.gif'
            elif mime == 'image/jpeg': filename += '.jpg'
            elif mime == 'image/png': filename += '.png'
            else: mime = None
            return (filename, mime, f.read())

    def __process_page(self, url, title, title_tagname, filename, css_file, package, page_decorator):
        page_tree = lxml.html.parse(url)
        def find_novel_view():
            for div in page_tree.iter('div'):
                if 'id' not in div.attrib: continue
                if div.attrib['id'] == 'novel_view':
                    return div
        novel_view = find_novel_view()
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
        prev_is_empty_p = False
        paragraph_open = False
        for n in novel_view.iter():
            if n.tag in ('ruby', 'img'):
                prev_is_empty_p = False
                if not paragraph_open:
                    paragraph_open = True
                    writer.start('p')
                if n.tag == 'ruby':
                    writer.start('ruby')
                    for ruby_child in n.iter():
                        if ruby_child.text is None: continue
                        if ruby_child.tag in ('rt', 'rp'):
                            writer.element(ruby_child.tag, text=ruby_child.text)
                        else:
                            writer.text(ruby_child.text)
                    writer.end()
                elif n.tag == 'img':
                    if 'src' in n.attrib:
                        (imgfilename, mime, data) = self.__process_image(n.attrib['src'])
                        if mime is not None and data is not None and imgfilename is not None:
                            package.manifest.add_item(imgfilename, mime, data)
                            writer.start('img', atts={'src':imgfilename})
                            if 'alt' in n.attrib:
                                writer.att('alt', n.attrib['alt'])
                            writer.end()
                continue

            # ignore
            if n.tag in ('rb', 'rt', 'rp'):
                continue

            if paragraph_open and n.tag == 'br':
                writer.end()
                paragraph_open = False
            text = n.text
            if text is None: text = n.tail
            if text is None and prev_is_empty_p: continue
            if not paragraph_open:
                writer.start('p')
                paragraph_open = True
            if text is not None:
                writer.text(text.strip())
                prev_is_empty_p = False
            else:
                prev_is_empty_p = True
        writer.end()
        package.manifest.add_item(filename, 'application/xhtml+xml', str(writer).encode('UTF-8'))

    def __process_short_story(self, ncode, metadata_tuple, css_map, package, page_decorator):
        (title, author, description, keywords, start_date, last_modified,
         novel_type, complete_flag) = metadata_tuple

        nav = EPUBNav('toc', '目次', 'ja', css_map.toc_css())
        nav.add_child(title, link = 'novel.xhtml')
        compatible_toc = EPUBCompatibleNav([nav], package.metadata, package.manifest)
        self.__process_page('http://ncode.syosetu.com/' + ncode, title, None, 'novel.xhtml', css_map.page_css(), package, page_decorator)
        package.manifest.add_item('toc.ncx', 'application/x-dtbncx+xml', str(compatible_toc).encode('UTF-8'),
                                  is_toc=True)
        package.manifest.add_item('toc.xhtml', 'application/xhtml+xml', nav.to_xml().encode('UTF-8'),
                                  add_to_spine=False, properties='nav')

    def __process_serial_story(self, ncode, metadata_tuple, css_map, package, toc_decorator, page_decorator):
        toc_page = lxml.html.parse('http://ncode.syosetu.com/' + ncode)
        def find_novel_sublist():
            for div in toc_page.iter('div'):
                if 'class' in div.attrib and div.attrib['class'] == 'novel_sublist': return div
        nav = EPUBNav('toc', '目次', 'ja', css_map.toc_css())
        child = None
        num_of_files = 0
        for td in find_novel_sublist().iter('td'):
            if 'class' not in td.attrib: continue
            if td.attrib['class'] == 'chapter': child = nav.add_child(td.text.strip())
            elif td.attrib['class'] == 'period_subtitle' or td.attrib['class'] == 'long_subtitle':
                node = nav
                link = td.find('a')
                if td.attrib['class'] == 'period_subtitle': node = child
                node.add_child(link.text.strip(), link=link.attrib['href'][len(ncode)+2:].rstrip('/'))
                num_of_files += 1

        filename_width = math.ceil(math.log10(num_of_files))
        def process_page(nav_node, indent):
            if nav_node.link is not None:
                filename = nav_node.link.zfill(filename_width) + '.xhtml'
                url = 'http://ncode.syosetu.com/' + ncode + '/' + nav_node.link + '/'
                nav_node.link = filename
                self.__process_page(url, nav_node.title, 'h' + str(indent), filename, css_map.page_css(), package, page_decorator)
            next_indent = indent + 1
            if next_indent > 6: next_indent = 6
            for child in nav_node.children:
                process_page(child, next_indent)
        process_page(nav, 2)
        compatible_toc = EPUBCompatibleNav([nav], package.metadata, package.manifest)
        package.manifest.add_item('toc.ncx', 'application/x-dtbncx+xml', str(compatible_toc).encode('UTF-8'),
                                  is_toc=True)
        package.manifest.add_item('toc.xhtml', 'application/xhtml+xml', nav.to_xml().encode('UTF-8'),
                                  spine_pos = package.manifest.find_spine_pos('cover.xhtml') + 1, properties='nav')

    def __process_cover(self, metadata_tuple, css_file, package):
        (title, author, description, keywords, start_date, last_modified,
         novel_type, complete_flag) = metadata_tuple
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
        writer.element('h2', atts={'class':'cover outline'}, text='あらすじ:')
        writer.element('p', text=description)
        package.manifest.add_item('cover.xhtml', 'application/xhtml+xml', str(writer).encode('UTF-8'))

    def __call__(self, ncode, css_map, package, toc_decorator, page_decorator):
        metadata_tuple = self.__get_metadata(ncode)
        print(metadata_tuple)

        (title, author, description, keywords, start_date, last_modified,
         novel_type, complete_flag) = metadata_tuple
        meta = package.metadata
        meta.add_title(title, lang='ja')
        meta.add_language('ja')
        meta.add_identifier('http://ncode.syosetu.com/' + ncode, unique_id=True)
        meta.add_modified('2012-05-04T04:14:53Z') # TODO
        meta.add_dcmes_info(DCMESCreatorInfo(author, lang='ja'))
        meta.add_dcmes_info(DCMESInfo('description', description, lang='ja'))

        css_map.output(package.manifest)
        self.__process_cover(metadata_tuple, css_map.cover_css(), package)
        if metadata_tuple[6] == '短編':
            self.__process_short_story(ncode, metadata_tuple, css_map, package, page_decorator)
        else:
            self.__process_serial_story(ncode, metadata_tuple, css_map, package, toc_decorator, page_decorator)

        package.save(ncode + '.epub')

class StylesheetMap:
    def __init__(self, default_css, cover_css = None, toc_css = None, page_css = None):
        self.default = default_css
        self.cover = cover_css if cover_css is not None else self.default
        self.toc = toc_css if toc_css is not None else self.default
        self.page = page_css if page_css is not None else self.default

    def default_css(self): return self.default[0]
    def cover_css(self): return self.cover[0]
    def toc_css(self): return self.toc[0]
    def page_css(self): return self.page[0]

    def output(self, manifest):
        css_list = (self.default, self.cover, self.toc, self.page)
        wrote_set = set()
        for css in css_list:
            if css[0] in wrote_set: continue
            wrote_set.add(css[0])
            manifest.add_item(css[0], 'text/css', css[1].encode('UTF-8'))

if __name__ == '__main__':
    if len(sys.argv) != 2:
        usage()
        quit()

    css_map = StylesheetMap(('style.css',
'''html {
  -epub-writing-mode: vertical-rl;
  direction: ltr;
  unicode-bidi:bidi-override;
}
ol {
  list-style-type: none;
  padding-top: 0.5em;
  padding-left: 1em;
}
ol ol {
  list-style-type: none;
  padding-top: 1em;
}
h2, h3, h4, h5, h6 {
  font-size: medium;
}
p {
  margin: 0;
  line-height: 140%;
}
body {
  margin: 0;
  padding: 0;
}
'''))
    package = EPUBPackage()
    package.spine.set_direction('rtl')
    SyosetuCom()(sys.argv[1], css_map, package, None, None)
