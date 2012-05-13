import datetime, hashlib, zlib, urllib.request
import concurrent.futures
import sqlalchemy

class SimpleCache:
    def __init__(self, expiration_time = datetime.timedelta(hours=6), max_parallel_fetches=8):
        self.expiration_time = expiration_time
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_fetches)

        from sqlalchemy.schema import Table, Column
        from sqlalchemy.types import Integer, DateTime, LargeBinary, String
        self.cache_db= sqlalchemy.create_engine('sqlite:///data/cache.sqlite')
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

    def fetch(self, url, force_use_cache=False):
        c = self.connect_deferred(self.cache_db)
        with c.begin() as transaction:
            cache_entry = c.execute(self.query_lookup_cache_url_record, url=url).fetchone()
            if cache_entry is not None:
                if force_use_cache or (cache_entry[0] + self.expiration_time >= datetime.datetime.utcnow()):
                    return zlib.decompress(c.execute(self.query_lookup_data, hash=cache_entry[1]).fetchone()[0])

        # download
        dt_modified = None
        dt_accessed = datetime.datetime.utcnow().replace(microsecond=0)
        with urllib.request.urlopen(url) as res:
            binary = res.readall()
            compressed_binary = zlib.compress(binary)
            try:
                dt_modified = datetime.datetime.strptime(res.info().get('Last-Modified', None),
                                                         '%a, %d %b %Y %H:%M:%S GMT')
            except:
                pass
        hash_value = hashlib.sha512(binary).hexdigest()[0:64]

        # add/update cache entry
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
        return binary

    def fetch_all(self, url_list, force_use_cache=False):
        futures = [self.executor.submit(self.fetch, url, force_use_cache=force_use_cache) for url in url_list]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except:
                results.append(None)
        return results

class DummyCache:
    def __init__(self, max_parallel_fetches=8):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_fetches)

    def fetch(self, url, force_use_cache=False):
        with urllib.request.urlopen(url) as res:
            return res.readall()

    def fetch_all(self, url_list, force_use_cache=False):
        futures = [self.executor.submit(self.fetch, url, force_use_cache=force_use_cache) for url in url_list]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except:
                results.append(None)
        return results
