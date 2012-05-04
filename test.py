#!/usr/bin/python3
# -*- coding: utf-8 -*-

from epub import *
import lxml.html, math, sys

class SyosetuCom:
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

    def __process_page(self, url, title, title_tagname, filename, package, page_decorator):
        page_tree = lxml.html.parse(url)
        def find_novel_view():
            for div in page_tree.iter('div'):
                if 'id' not in div.attrib: continue
                if div.attrib['id'] == 'novel_view':
                    return div
        novel_view = find_novel_view()
        writer = SimpleXMLWriter()
        writer.doc_type = '<!DOCTYPE html>'
        writer.start('html')
        writer.att('xmlns', 'http://www.w3.org/1999/xhtml')
        writer.att('xml:lang', 'ja')
        writer.start('head')
        writer.start('title')
        writer.text(title)
        writer.end()
        writer.end()
        writer.start('body')
        if title_tagname is not None:
            writer.start(title_tagname)
            writer.text(title)
            writer.end()
        prev_is_empty_p = False
        for n in novel_view.iter():
            text = n.text
            if text is None: text = n.tail
            if text is None and prev_is_empty_p: continue
            writer.start('p')
            if text is not None:
                writer.text(text.strip())
                prev_is_empty_p = False
            else:
                prev_is_empty_p = True
            writer.end()
        writer.end()
        package.manifest.add_item(filename, 'application/xhtml+xml', str(writer).encode('UTF-8'))

    def __process_short_story(self, ncode, metadata_tuple, package, page_decorator):
        (title, author, description, keywords, start_date, last_modified,
         novel_type, complete_flag) = metadata_tuple
        meta = package.metadata
        self.__process_page('http://ncode.syosetu.com/' + ncode, title, None, 'novel.xhtml', package, page_decorator)
    def __process_serial_story(self, ncode, metadata_tuple, package, toc_decorator, page_decorator):
        toc_page = lxml.html.parse('http://ncode.syosetu.com/' + ncode)
        def find_novel_sublist():
            for div in toc_page.iter('div'):
                if 'class' in div.attrib and div.attrib['class'] == 'novel_sublist': return div
        nav = EPUBNav('toc', '目次', 'ja', 'style.css')
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
                self.__process_page(url, nav_node.title, 'h' + str(indent), filename, package, page_decorator)
            next_indent = indent + 1
            if next_indent > 6: next_indent = 6
            for child in nav_node.children:
                process_page(child, next_indent)
        process_page(nav, 2)
        compatible_toc = EPUBCompatibleNav([nav], package.metadata, package.manifest)
        package.manifest.add_item('toc.ncx', 'application/x-dtbncx+xml', str(compatible_toc).encode('UTF-8'),
                                  is_toc=True)
        package.manifest.add_item('toc.xhtml', 'application/xhtml+xml', nav.to_xml().encode('UTF-8'),
                                  properties='nav')

    def __process_cover(self, metadata_tuple, css_file, package):
        (title, author, description, keywords, start_date, last_modified,
         novel_type, complete_flag) = metadata_tuple
        writer = SimpleXMLWriter()
        writer.doc_type = '<!DOCTYPE html>'
        writer.start('html')
        writer.att('xmlns', 'http://www.w3.org/1999/xhtml')
        writer.att('xml:lang', 'ja')
        writer.start('head')
        writer.start('title')
        writer.text(title)
        writer.end()
        if css_file is not None:
            writer.start('link')
            writer.att('rel', 'stylesheet')
            writer.att('type', 'text/css')
            writer.att('href', css_file)
            writer.end()
        writer.end()
        writer.start('body')

        writer.start('h1')
        writer.att('class', 'cover title')
        writer.text(title)
        writer.end()

        writer.start('h2')
        writer.att('class', 'cover author')
        writer.text('作者:')
        writer.end()
        writer.start('p')
        writer.text(author)
        writer.end()

        writer.start('h2')
        writer.att('class', 'cover outline')
        writer.text('あらすじ:')
        writer.end()
        writer.start('p')
        writer.text(description)
        writer.end()

        package.manifest.add_item('cover.xhtml', 'application/xhtml+xml', str(writer).encode('UTF-8'))

    def __call__(self, ncode, package, toc_decorator, page_decorator):
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

        self.__process_cover(metadata_tuple, None, package)
        if metadata_tuple[6] == '短編':
            self.__process_short_story(ncode, metadata_tuple, package, page_decorator)
        else:
            self.__process_serial_story(ncode, metadata_tuple, package, toc_decorator, page_decorator)

        package.save(ncode + '.epub')

if __name__ == '__main__':
    if len(sys.argv) != 2:
        usage()
        quit()
    SyosetuCom()(sys.argv[1], EPUBPackage(), None, None)
