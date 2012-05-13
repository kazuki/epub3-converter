#!/usr/bin/python3
# -*- coding: utf-8 -*-

from epub import *
from style import *
from cache import DummyCache
import lxml.html, math, sys, urllib.request, re, datetime, io

class SyosetuCom:
    image_url_regex = re.compile('[^0-9]*([0-9]+)\..*/icode/(i[0-9a-zA-Z]+)')

    def __init__(self, cache=DummyCache()):
        self.cache = cache

    def __get_all_text(self, node):
        text = ''
        for n in node.iter():
            if n.text is not None: text += n.text
            if n.tail is not None: text += n.tail
        return text.strip()
    def __get_metadata(self, ncode):
        ''' return (title, author, description, keywords[space-separated],
            start-date, last modified, type[連載,短編], completed_flag)    '''
        fetch_url = 'http://ncode.syosetu.com/novelview/infotop/ncode/' + ncode
        info_page = lxml.html.parse(io.BytesIO(self.cache.fetch(fetch_url)))
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

        def to_datetime(s):
            s2 = ''
            for c in s:
                if c >= '0' and c <= '9':
                    s2 += c
            return datetime.datetime(int(s2[0:4]), int(s2[4:6]), int(s2[6:8]), int(s2[8:10]), int(s2[10:12]),
                                     tzinfo=datetime.timezone(datetime.timedelta(hours=9)))
        start_date = to_datetime(start_date)
        last_modified = to_datetime(last_modified)
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

    def __process_page(self, url, title, title_tagname, filename, css_file, package):
        page_tree = lxml.html.parse(io.BytesIO(self.cache.fetch(url)))
        def find_novel_view():
            for div in page_tree.iter('div'):
                if 'id' not in div.attrib: continue
                if div.attrib['id'] == 'novel_view':
                    return div
        novel_view = find_novel_view()
        writer = SimpleXMLWriter()
        writer.write_xhtml_dtd_and_documentelement(lang='ja')
        writer.start('head')
        writer.element('title', text=title)
        writer.write_link_stylesheet(css_file)
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
                            package.manifest.add_item(imgfilename, data, media_type=mime)
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
        package.manifest.add_item(filename, str(writer))

    def __process_short_story(self, ncode, metadata_tuple, css_map, package):
        (title, author, description, keywords, start_date, last_modified,
         novel_type, complete_flag) = metadata_tuple

        nav = EPUBNav('toc', '目次', 'ja', css_map.toc_css())
        nav.add_child(title, link = 'novel.xhtml')
        compatible_toc = EPUBCompatibleNav([nav], package.metadata, package.manifest)
        self.__process_page('http://ncode.syosetu.com/' + ncode, title, None, 'novel.xhtml', css_map.page_css(), package)
        package.manifest.add_item('toc.ncx', str(compatible_toc), is_toc=True)
        package.manifest.add_item('toc.xhtml', nav.to_xml(), add_to_spine=False, properties='nav')

    def __process_serial_story(self, ncode, metadata_tuple, css_map, package):
        toc_page = lxml.html.parse(io.BytesIO(self.cache.fetch('http://ncode.syosetu.com/' + ncode)))
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
                self.__process_page(url, nav_node.title, 'h' + str(indent), filename, css_map.page_css(), package)
            next_indent = indent + 1
            if next_indent > 6: next_indent = 6
            for child in nav_node.children:
                process_page(child, next_indent)
        process_page(nav, 2)
        compatible_toc = EPUBCompatibleNav([nav], package.metadata, package.manifest)
        package.manifest.add_item('toc.ncx', str(compatible_toc), is_toc=True)
        package.manifest.add_item('toc.xhtml', nav.to_xml(), properties='nav',
                                  spine_pos = package.manifest.find_spine_pos('cover.xhtml') + 1)

    def __call__(self, package, css_map, ncode):
        metadata_tuple = self.__get_metadata(ncode)
        print(metadata_tuple)

        (title, author, description, keywords, start_date, last_modified,
         novel_type, complete_flag) = metadata_tuple
        meta = package.metadata
        meta.add_title(title, lang='ja')
        meta.add_language('ja')
        meta.add_identifier('http://ncode.syosetu.com/' + ncode, unique_id=True)
        meta.add_created(start_date)
        meta.add_modified(last_modified)
        meta.add_date(datetime.datetime.utcnow())
        meta.add_creator(author, lang='ja')
        meta.add_description(description, lang='ja')

        css_map.output(package.manifest)
        add_simple_cover(package.manifest, title, author, description=description, css_file=css_map.cover_css())
        if metadata_tuple[6] == '短編':
            self.__process_short_story(ncode, metadata_tuple, css_map, package)
        else:
            self.__process_serial_story(ncode, metadata_tuple, css_map, package)

if __name__ == '__main__':
    if len(sys.argv) != 2:
        print('usage: %s [ncode (example: n0000a)]' % (sys.argv[0],))
        quit()
    converter = SyosetuCom()
    ncode = sys.argv[1]

    css_map = StylesheetMap(('style.css', SimpleVerticalWritingStyle))
    package = EPUBPackage()
    package.spine.set_direction('rtl')
    converter(package, css_map, ncode)
    package.save(ncode + '.epub')
