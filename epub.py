#!/usr/bin/python3
# -*- coding: utf-8 -*-

from io import RawIOBase, IOBase
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED, ZIP_STORED
import xml.etree.ElementTree as ET
import xml.sax.saxutils as SAX
import datetime, os.path

class SimpleXMLWriter:
    def __init__(self):
        self.root = None
        self.current = None
        self.doc_type = None
        self.stack = []

    def __push(self, name):
        if self.current is None:
            if self.root is not None:
                raise Exception
            self.root = ET.Element(name)
            self.current = self.root
        else:
            self.stack.append(self.current)
            self.current = ET.SubElement(self.current, name)
        
    def __pop(self): self.current = self.stack.pop()
    def start(self, name, atts={}, text=None):
        self.__push(name)
        for key,value in atts.items():
            self.att(key,value)
        if text is not None: self.text(text)
    def end(self): self.__pop()
    def text(self, text):
        if self.current.text is None:
            self.current.text = text
        else:
            self.current.text += text
    def att(self, name, value):
        self.current.attrib[name] = value
    def element(self, name, atts={}, text=None):
        self.start(name, atts, text)
        self.end()

    def __to_string(self, node, indent):
        xml = indent + '<' + node.tag
        for (key,value) in node.attrib.items():
            xml += ' ' + key + '=' + SAX.quoteattr(value)
        children = node.getchildren()
        if len(children) == 0 and (node.text is None or len(node.text) == 0):
            xml += ' />\n'
        else:
            xml += '>'
            if node.text is not None and len(node.text) > 0: xml += SAX.escape(node.text)
            if len(children) > 0:
                xml += '\n'
                next_indent = indent + '  '
                for child in children:
                    xml += self.__to_string(child, next_indent)
                xml += indent
            xml += '</' + node.tag + '>\n'
        return xml
        
    def __str__(self):
        doc_type = self.doc_type
        if doc_type is None: doc_type = ''
        else: doc_type = doc_type.strip() + '\n'
        return '<?xml version="1.0" encoding="utf-8" ?>\n' + doc_type + \
            self.__to_string(self.root, '')

    def write_xhtml_dtd_and_documentelement(self, lang=None):
        self.doc_type = '<!DOCTYPE html>'
        self.start('html', atts={'xmlns':'http://www.w3.org/1999/xhtml'})
        if lang is not None: self.att('xml:lang', lang)
    def write_link_stylesheet(self, href):
        if href is not None:
            self.element('link', atts={'rel':'stylesheet', 'type':'text/css', 'href':href})

class EPUBPackage:
    def __init__(self):
        self.version = "3.0"
        self.lang = None
        self.metadata = EPUBMetadata()
        self.manifest = EPUBManifest(self, EPUBSpine())
        self.spine = self.manifest.spine
        self.files = []

    def add_file(self, path, file_or_bytes):
        self.files.append((path, file_or_bytes))

    def __validate(self):
        self.metadata.validate()
        self.manifest.validate()

    def __create_container_xml(self, opf_path):
        return """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="%s" media-type="application/oebps-package+xml" />
  </rootfiles>
</container>""" % (opf_path,)

    def __create_opf(self):
        writer = SimpleXMLWriter()
        writer.start('package', atts={'xmlns':'http://www.idpf.org/2007/opf', 'version':'3.0'})
        if self.metadata.unique_id is not None:
            writer.att('unique-identifier', 'BookId')
        self.metadata.write_xml(writer)
        self.manifest.write_xml(writer)
        self.spine.write_xml(writer)
        output = str(writer)
        print(output)
        return output.encode("UTF-8")

    def save(self, file, compression = ZIP_DEFLATED):
        self.__validate()
        rootdir = "OPBES/"
        opf_path = rootdir + "content.opf"
        with ZipFile(file, "w", compression) as epub:
            epub.writestr("mimetype", "application/epub+zip".encode("UTF-8"), compress_type=ZIP_STORED)
            epub.writestr("META-INF/container.xml",
                          self.__create_container_xml(opf_path).encode("UTF-8"))
            epub.writestr(opf_path, self.__create_opf())
            for (path, file_or_bytes) in self.files:
                data = file_or_bytes
                if isinstance(file_or_bytes, RawIOBase):
                    data = file_or_bytes.readall()
                if isinstance(file_or_bytes, IOBase):
                    buf = bytearray(1024 * 64)
                    data = bytes()
                    while True:
                        read_size = file_or_bytes.readinto(buf)
                        if read_size == 0: break
                        data = data + buf[0:read_size]
                epub.writestr(rootdir + path, data)

class MetadataError(Exception):
    def __init__(self, msg):
        self.msg = msg
    def __str__(self):
        return self.msg

class DCMESInfo:
    def datetime_to_str(dt):
        dt = dt.replace(microsecond=0)
        if dt.utcoffset() is not None:
            dt = (dt - dt.utcoffset()).replace(tzinfo=None)
        return dt.isoformat() + 'Z'
    def __init__(self, name, content, lang=None, dir=None):
        self.name = name
        self.content = content
        self.atts = {}
        self.props = []
        if lang is not None: self.set_att('xml:lang', lang)
        if dir is not None:  self.set_att('dir', dir)

    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc_value, traceback):
        pass
    def clear_props(self):
        self.props = []
    def set_att(self, name, value):
        self.atts[name] = value
    def add_prop(self, name, content, atts = None):
        if atts is None:
            atts = {}
        atts['property'] = name
        atts['__content__'] = content
        self.props.append(atts)
    def set_prop(self, name, content, atts = None):
        remove_idx = None
        for i in range(len(self.props)):
            if self.props[i]['property'] == name:
                remove_idx = i
                break
        if remove_idx is not None:
            del self.props[remove_idx]
        self.add_prop(name, content, atts)
    def write_xml(self, id, writer):
        writer.start('dc:' + self.name)
        if id is not None and len(self.props) > 0: writer.att('id', id)
        for (key,value) in self.atts.items():
            if value is None: continue
            writer.att(key, value)
        if self.content is not None:
            writer.text(self.content)
        writer.end()
        for prop in self.props:
            writer.start('meta', atts={'refines':'#' + id})
            for (key,value) in prop.items():
                if value is None or key[0] == '_': continue
                writer.att(key, value)
            if '__content__' in prop:
                writer.text(prop['__content__'])
            writer.end()

    def set_alternate_script(self, lang, content):
        self.set_prop('alternate-script', content, {'xml:lang': lang})
    def set_display_seq(self, seq):
        self.set_prop('display-seq', str(int(seq)))
    def set_file_as(self, file_as):
        self.set_prop('file-as', file_as)
    def set_group_position(self, pos):
        self.set_prop('group-position', str(int(pos)))
    def _set_identifier_type(self, scheme, content):
        self.set_prop('identifier-type', content, {'scheme': scheme})
    def set_meta_auth(self, auth):
        self.set_prop('meta-auth', auth)
    def _set_role(self, scheme, role):
        self.set_prop('role', role, {'scheme': scheme})
    def _set_title_type(self, title_type):
        if title_type not in ('main', 'subtitle', 'short', 'collection', 'edition', 'expanded'):
            raise MetadataError("unknown title-type")
        self.set_prop('title-type', title_type)

class DCMESIdentifierInfo(DCMESInfo):
    def __init__(self, identifier, unique_id=False):
        DCMESInfo.__init__(self, 'identifier', identifier)
        self.unique_id = unique_id
    def set_type(self, scheme, content): self._set_identifier_type(scheme, content)

class DCMESTitleInfo(DCMESInfo):
    def __init__(self, title, lang=None, dir=None):
        DCMESInfo.__init__(self, 'title', title, lang=lang, dir=dir)
    def set_type(self, title_type): self._set_title_type(title_type)

class DCMESLanguageInfo(DCMESInfo):
    def __init__(self, lang):
        DCMESInfo.__init__(self, 'language', lang)

class DCMESContributorInfo(DCMESInfo):
    def __init__(self, contributor, lang=None, dir=None):
        DCMESInfo.__init__(self, 'contributor', contributor, lang=lang, dir=dir)
    def set_role(self, scheme, role): self._set_role(scheme, role)

class DCMESCreatorInfo(DCMESInfo):
    def __init__(self, creator, lang=None, dir=None):
        DCMESInfo.__init__(self, 'creator', creator, lang=lang, dir=dir)
    def set_role(self, scheme, role): self._set_role(scheme, role)

class DCMESDateInfo(DCMESInfo):
    def __init__(self, dt):
        DCMESInfo.__init__(self, 'date', DCMESInfo.datetime_to_str(dt))

class DCMESSourceInfo(DCMESInfo):
    def __init__(self, source):
        DCMESInfo.__init__(self, 'source', source)

class EPUBMetadata:
    def __init__(self):
        self.unique_id = None
        self.dcmes = []
        self.meta = []
        self.link = []

    def add_identifier(self, identifier, unique_id = False):
        return self.add_dcmes_info(DCMESIdentifierInfo(identifier, unique_id))
    def add_title(self, title, lang=None, dir=None):
        return self.add_dcmes_info(DCMESTitleInfo(title, lang, dir))
    def add_language(self, lang):
        return self.add_dcmes_info(DCMESLanguageInfo(lang))
    def add_created(self, dt):
        self.add_date_term('created', dt)
    def add_modified(self, dt):
        self.add_date_term('modified', dt)
    def add_date_term(self, term, dt):
        self.add_meta('dcterms:' + term, DCMESInfo.datetime_to_str(dt))

    def add_creator(self, creator, lang = None):
        self.add_dcmes_info(DCMESCreatorInfo(creator, lang=lang))
    def add_date(self, dt):
        self.add_dcmes_info(DCMESDateInfo(dt))
    def add_description(self, description, lang = None):
        self.add_dcmes_info(DCMESInfo('description', description, lang=lang))
    def add_dcmes_info(self, dcmes_info):
        self.dcmes.append(dcmes_info)
        if self.unique_id is None and isinstance(dcmes_info, DCMESIdentifierInfo) and dcmes_info.unique_id:
            self.unique_id = dcmes_info
            dcmes_info.set_att('id', 'BookId')
        return dcmes_info
    def add_meta(self, propname, content, scheme = None):
        self.meta.append({'property':propname, '__content__': content, 'scheme': scheme})
    def add_link(self, rel, href, media_type = None):
        self.link.append({'rel':rel, 'href':href, 'media-type':media_type})

    def validate(self):
        pass

    def get_dcmes_text(self, name):
        for dcmes_info in self.dcmes:
            if dcmes_info.name == name and dcmes_info.content is not None:
                return dcmes_info.content
        return None

    def write_xml(self, writer):
        writer.start('metadata', atts={'xmlns:dc':'http://purl.org/dc/elements/1.1/'})
        dcmes_id_map = {}
        for dcmes_info in self.dcmes:
            id = dcmes_info.name
            if dcmes_info.name not in dcmes_id_map:
                dcmes_id_map[dcmes_info.name] = 1
            else:
                dcmes_id_map[dcmes_info.name] += 1
            id += str(dcmes_id_map[dcmes_info.name])
            dcmes_info.write_xml(id, writer)
        for m in self.meta:
            writer.start('meta')
            for (key,value) in m.items():
                if key[0] == '_' or value is None: continue
                writer.att(key, value)
            if m['__content__'] is not None:
                writer.text(m['__content__'])
            writer.end()
        for l in self.link:
            writer.start('link')
            for (key,value) in m.items():
                if value is None: continue
                writer.att(key, value)
            writer.end()
        writer.end()

class EPUBManifest:
    MimeMap = {'xhtml':'application/xhtml+xml',
               'ncx':'application/x-dtbncx+xml',
               'css':'text/css'}

    def __init__(self, package, spine):
        self.package = package
        self.spine = spine
        self.items = []
        self.id_set = set()
        self.autoid = 0

    def __create_id(self):
        while True:
            id = "id_" + hex(self.autoid)[2:].zfill(4)
            self.autoid += 1
            if id not in self.id_set:
                return id

    def add_item(self, href, file_or_bytes,
                 media_type = None, id = None, spine_pos = None,
                 add_to_spine=None, is_toc = False,
                 fallback=None, properties=None, media_overlay=None):

        if media_type is None:
            file_extension = os.path.splitext(href)[1][1:]
            if file_extension not in EPUBManifest.MimeMap:
                print(file_extension)
                raise 'unknown media-type'
            media_type = EPUBManifest.MimeMap[file_extension]

        if add_to_spine is None:
            add_to_spine = False
            if media_type in ('application/xhtml+xml'):
                add_to_spine = True

        if isinstance(file_or_bytes, str):
            file_or_bytes = file_or_bytes.encode('UTF-8')

        if id is None: id = self.__create_id()
        if id in self.id_set: raise MetadataError("duplicate id")
        if is_toc and self.spine.toc is not None: raise MetadataError('already added TOC')
        if properties is not None: properties = self.__check_properties(properties)
        if add_to_spine: self.spine.add_itemref(id, pos=spine_pos)
        if is_toc: self.spine.toc = id
        self.id_set.add(id)
        self.package.add_file(href, file_or_bytes)
        self.items.append({'id':id, 'href':href, 'media-type':media_type,
                           'fallback':fallback, 'properties':properties,
                           'media-overlay':media_overlay})

    __defined_properties = ('cover-image', 'mathml', 'nav', 'remote-resources',
                            'scripted', 'svg', 'switch')
    def __check_properties(self, properties):
        props = properties.split()
        ret = set()
        for prop in props:
            if prop not in self.__defined_properties:
                raise MetadataError('unknown property "' + prop + '"')
            ret.add(prop)
        return " ".join(ret)
    def validate(self):
        # fallback id check
        # properties check
        pass

    def find_spine_pos(self, filename):
        id = self.lookup_id(filename)
        if id is None:
            return -1
        for i in range(len(self.spine.itemrefs)):
            if self.spine.itemrefs[i]['idref'] == id:
                return i
        return -1

    def lookup_id(self, filename):
        for item in self.items:
            if item['href'] == filename:
                return item['id']
        return None

    def write_xml(self, writer):
        writer.start('manifest')
        for item in self.items:
            writer.start('item')
            for (key, value) in item.items():
                if value is None: continue
                writer.att(key, value)
            writer.end()
        writer.end()

class EPUBSpine:
    def __init__(self):
        self.toc = None
        self.page_direction = None
        self.itemrefs = []
        self.refset = set()
    def set_direction(self, dir):
        self.page_direction = dir
    def add_itemref(self, idref, pos = None):
        if idref in self.refset:
            raise MetadataError('duplicate idref')
        self.refset.add(idref)
        if pos is None: pos = len(self.itemrefs)
        self.itemrefs.insert(pos, {'idref':idref})
    def write_xml(self, writer):
        writer.start('spine')
        if self.toc is not None: writer.att('toc', self.toc)
        if self.page_direction is not None: writer.att('page-progression-direction', self.page_direction)
        for itemref in self.itemrefs:
            writer.start('itemref')
            for (key,value) in itemref.items():
                writer.att(key,value)
            writer.end()
        writer.end()

class EPUBNavNode:
    def __init__(self, title, link=None):
        self.title = title
        self.link = link
        self.children = []
    def add_child(self, title, link=None):
        node = EPUBNavNode(title, link)
        self.children.append(node)
        return node
    def to_xml(self, writer):
        if self.link is None:
            writer.start('span')
        else:
            writer.start('a')
            writer.att('href', self.link)
        writer.text(self.title)
        writer.end()
        if len(self.children) > 0:
            writer.start('ol')
            for child in self.children:
                writer.start('li')
                child.to_xml(writer)
                writer.end()
            writer.end()

class EPUBNav(EPUBNavNode):
    def __init__(self, type, title, lang, css_file):
        EPUBNavNode.__init__(self, title)
        self.type = type
        self.lang = lang
        self.css = css_file
        self.head_write_func = None
        self.tail_write_func = None

    def to_xml(self):
        writer = SimpleXMLWriter()

        writer.start('html', atts={'xmlns':'http://www.w3.org/1999/xhtml', 'xmlns:epub':'http://www.idpf.org/2007/ops'})
        writer.start('head')
        writer.element('title', text=self.title)
        if self.css is not None:
            writer.element('link', atts={'rel':'stylesheet', 'type':'text/css', 'href':self.css})
        writer.end()
        writer.start('body')

        if self.head_write_func is not None:
            self.head_write_func(self, writer)
        else:
            writer.element('h1', text=self.title)

        writer.start('nav', atts={'epub:type':self.type})
        if len(self.children) > 0:
            writer.start('ol')
            for child in self.children:
                writer.start('li')
                child.to_xml(writer)
                writer.end()
            writer.end()
        writer.end()

        if self.tail_write_func is not None:
            self.tail_write_func(self, writer)
        return str(writer)

class EPUBCompatibleNav:
    def __init__(self, navs, meta, manifest):
        self.title = meta.get_dcmes_text('title')
        self.uid = meta.get_dcmes_text('identifier')
        self.lang = meta.get_dcmes_text('language')
        self.navs = navs
        self.manifest = manifest
    def __output_navMap(self, nav, writer, autoid):
        writer.start('navMap')
        def output_navPoint(curnav):
            autoid[0] += 1
            writer.start('navPoint', atts={'id':'navpoint' + str(autoid[0])})
            writer.start('navLabel')
            writer.element('text', text=curnav.title)
            writer.end()
            if curnav.link is not None:
                writer.element('content', atts={'src':curnav.link})
            for child in curnav.children:
                output_navPoint(child)
            writer.end()
        for child in nav.children:
            output_navPoint(child)
        writer.end()
    def __str__(self):
        writer = SimpleXMLWriter()
        writer.doc_type = '<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN" "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">'
        writer.start('ncx', atts={'xmlns':'http://www.daisy.org/z3986/2005/ncx/',
                                  'xml:lang':self.lang, 'version':'2005-1'})
        writer.start('head')
        writer.element('meta', atts={'name':'dtb:uid', 'content':self.uid})
        writer.end()
        writer.start('docTitle')
        writer.element('text', text=self.title)
        writer.end()

        autoid = [0]
        for nav in self.navs:
            if nav.type == 'toc':
                self.__output_navMap(nav, writer, autoid)
        return str(writer)
