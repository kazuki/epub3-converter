import datetime, hashlib, zlib, urllib.request
import concurrent.futures
import sqlalchemy

class SimpleCache:
    def __init__(self, cache_db_path = 'data/cache.sqlite',
                 expiration_time = datetime.timedelta(hours=6), max_parallel_fetches=8):
        self.expiration_time = expiration_time
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_fetches)

        from sqlalchemy.schema import Table, Column
        from sqlalchemy.types import Integer, DateTime, LargeBinary, String
        self.cache_db= sqlalchemy.create_engine('sqlite:///' + cache_db_path)
        self.meta = sqlalchemy.MetaData()

        # expiration model cache
        self.url_table = Table('html_cache_url', self.meta,
                               Column('url', String, primary_key=True),
                               Column('accessed', DateTime, nullable=False),
                               Column('hash', String(64), nullable=False))
        self.data_table = Table('html_cache_data', self.meta,
                                Column('hash', String(64), primary_key=True),
                                Column('url', String, nullable=False),
                                Column('modified', DateTime, nullable=True),
                                Column('accessed', DateTime, nullable=False),
                                Column('data', LargeBinary, nullable=False))
        self.meta.create_all(self.cache_db)

        # build query
        from sqlalchemy.sql import select, bindparam
        self.query_lookup_cache_url_record = select([self.url_table.c.accessed, self.url_table.c.hash],
                                                    self.url_table.c.url==bindparam('url'))
        self.query_lookup_data = select([self.data_table.c.data],
                                        self.data_table.c.hash==bindparam('hash'))

    def connect_deferred(self, db):
        return db.connect(_execution_options={'isolation_level':'DEFERRED'})

    def connect_immediate(self, db):
        return db.connect(_execution_options={'isolation_level':'IMMEDIATE'})

    def __lookup_cache(self, url, use_cache_newer_than=None):
        if use_cache_newer_than is None or not isinstance(use_cache_newer_than, datetime.datetime):
            use_cache_newer_than = datetime.datetime.max
        c = self.connect_deferred(self.cache_db)
        with c.begin() as transaction:
            cache_entry = c.execute(self.query_lookup_cache_url_record, url=url).fetchone()
            if cache_entry is not None:
                if cache_entry[0] >= use_cache_newer_than or cache_entry[0] + self.expiration_time >= datetime.datetime.utcnow():
                    return (cache_entry, zlib.decompress(c.execute(self.query_lookup_data, hash=cache_entry[1]).fetchone()[0]))
            return (cache_entry, None)

    def __download(self, url):
        dt_modified = None
        dt_accessed = datetime.datetime.utcnow().replace(microsecond=0)
        with urllib.request.urlopen(url) as res:
            binary = res.readall()
            compressed_binary = zlib.compress(binary)
            dt_modified = res.info().get('Last-Modified', None)
            if dt_modified is not None:
                try:
                    dt_modified = datetime.datetime.strptime(dt_modified, '%a, %d %b %Y %H:%M:%S GMT')
                except:
                    pass
        hash_value = hashlib.sha512(binary).hexdigest()[0:64]
        return (binary, compressed_binary, hash_value, dt_accessed, dt_modified)

    def __update_cache(self, url, cache_entry, compressed_binary, hash_value, dt_accessed, dt_modified):
        c = self.connect_immediate(self.cache_db)
        with c.begin() as transaction:
            try:
                if cache_entry is None:
                    c.execute(self.url_table.insert(), url=url, accessed=dt_accessed, hash=hash_value)
                else:
                    c.execute(self.url_table.update().values({
                                self.url_table.c.accessed: dt_accessed,
                                self.url_table.c.hash:hash_value
                              }).where(self.url_table.c.url==url))
                if cache_entry is None or hash_value != cache_entry[1]:
                    c.execute(self.data_table.insert(), hash=hash_value, url=url, data=compressed_binary,
                              accessed=dt_accessed, modified=dt_modified)
                else:
                    c.execute(self.data_table.update().values({
                                self.data_table.c.accessed: dt_accessed
                              }).where(self.data_table.c.hash == hash_value))
                transaction.commit()
            except:
                # rollback. ignore exception
                transaction.rollback()

    def fetch(self, url, use_cache_newer_than=None):
        (cache_entry, binary) = self.__lookup_cache(url, use_cache_newer_than)
        if binary is not None: return binary
        (binary, compressed_binary, hash_value, dt_accessed, dt_modified) = self.__download(url)
        self.__update_cache(url, cache_entry, compressed_binary, hash_value, dt_accessed, dt_modified)
        return binary

    def fetch_all(self, url_list, use_cache_newer_than_map=None):
        futures = {}
        results = {}
        for url in url_list:
            dt = use_cache_newer_than_map.get(url) if use_cache_newer_than_map is not None else None
            (cache_entry, binary) = self.__lookup_cache(url, dt)
            if binary is None:
                futures[self.executor.submit(self.__download, url)] = (url, cache_entry)
            else:
                results[url] = binary
        for future in concurrent.futures.as_completed(futures):
            (url, cache_entry) = futures[future]
            if future.exception() is not None:
                results[url] = None
                continue
            (binary, compressed_binary, hash_value, dt_accessed, dt_modified) = future.result()
            self.__update_cache(url, cache_entry, compressed_binary, hash_value, dt_accessed, dt_modified)
            results[url] = binary
        return [results[url] for url in url_list]

class DummyCache:
    def __init__(self, max_parallel_fetches=8):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_fetches)

    def fetch(self, url, use_cache_newer_than=None):
        with urllib.request.urlopen(url) as res:
            return res.readall()

    def fetch_all(self, url_list, use_cache_newer_than_list=None, use_cache_newer_than_map=None):
        futures = [self.executor.submit(self.fetch, url) for url in url_list]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except:
                results.append(None)
        return results
