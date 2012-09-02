from epub import *

def add_simple_cover(manifest, title, author, description=None, css_file=None, filename='cover.xhtml'):
    writer = SimpleXMLWriter()
    writer.write_xhtml_dtd_and_documentelement(lang='ja')
    writer.start('head')
    writer.element('title', text=title)
    writer.write_link_stylesheet(css_file)
    writer.end()
    writer.start('body')
    writer.element('h1', atts={'class':'cover title'}, text=title)
    writer.element('h2', atts={'class':'cover author'}, text='作者:')
    writer.element('p', text=author)
    if description is not None:
        writer.element('h2', atts={'class':'cover outline'}, text='あらすじ:')
        writer.element('p', text=description)
    manifest.add_item(filename, str(writer).encode('UTF-8'))

def create_simple_page(title, title_tagname, css_file, iterator):
    writer = SimpleXMLWriter()
    writer.write_xhtml_dtd_and_documentelement(lang='ja')
    writer.start('head')
    writer.element('title', text=title)
    writer.write_link_stylesheet(css_file)
    writer.end()
    writer.start('body')
    if title_tagname is not None:
        writer.element(title_tagname, text=title)
    for line in iterator:
        writer.element('p', text=line.strip())
    writer.end()
    return str(writer)

def create_simple_page_from_html(package, filename, title, title_tagname, css_file, novel_body_element):
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

    for n in novel_body_element.iter():
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
            if n.tail is not None:
                writer.text(n.tail.strip())
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
            manifest.add_item(css[0], css[1].encode('UTF-8'))

SimpleVerticalWritingStyle = '''html {
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
'''
