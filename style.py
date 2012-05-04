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
