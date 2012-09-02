import datetime, hashlib, zlib, urllib.request
import concurrent.futures, os.path, shelve, sys, time
from urllib.error import HTTPError

def url_readall(url):
    last_exception_is_503 = False
    max_retry_count = 3
    for retry_count in range(max_retry_count):
        last_retry = (retry_count == max_retry_count - 1)
        sleep_time = 1
        last_exception_is_503 = False
        try:
            with urllib.request.urlopen(url) as res:
                return (res.readall(), res)
        except HTTPError as ex:
            if ex.code in (503,):
                sys.stderr.write('urlopen failed. retry...' + url + '\n')
                sleep_time = 10
                last_exception_is_503 = True
        except Exception as ex:
            sys.stderr.write(str(ex) + '. url=' + url + '\n')
        except:
            sys.stderr.write('unknown exception. url=' + url + '\n')
        if not last_retry:
            time.sleep(sleep_time)
    if last_exception_is_503:
        raise HTTPError(url, 503, None, None, None)
    else:
        raise HTTPError(url, 500, None, None, None)

class SimpleCache:
    def __init__(self, cache_dir = 'data',
                 expiration_time = datetime.timedelta(hours=6), max_parallel_fetches=8):
        self.expiration_time = expiration_time
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_fetches)

        """ GNU dbm key-value spec.
        url_db:  key=url, value=(accessed, hash)
        data_db: key=hash, value=(url, modified, data) """
        self.url_db = shelve.open(os.path.join(cache_dir, 'urldb'), flag='c')
        self.data_db = shelve.open(os.path.join(cache_dir, 'datadb'), flag='c')

    def __lookup_cache(self, url, use_cache_newer_than=None):
        if use_cache_newer_than is None or not isinstance(use_cache_newer_than, datetime.datetime):
            use_cache_newer_than = datetime.datetime.max
        entry = self.url_db.get(url)
        if entry is not None:
            if entry[0] >= use_cache_newer_than or entry[0] + self.expiration_time >= datetime.datetime.utcnow():
                data_entry = self.data_db.get(entry[1])
                return (entry, zlib.decompress(data_entry[2]))
        return (entry, None)

    def __download(self, url):
        dt_modified = None
        dt_accessed = datetime.datetime.utcnow().replace(microsecond=0)
        (binary, res) = url_readall(url)
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
        if cache_entry is None or hash_value != cache_entry[1]:
            self.data_db[hash_value] = (url, dt_modified, compressed_binary)
        self.url_db[url] = (dt_accessed, hash_value)

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
                for tmp in futures:
                    try:
                        tmp.cancel()
                    except:
                        pass
                print("error url =", url, ". cancelled all download task")
                raise future.exception()
            (binary, compressed_binary, hash_value, dt_accessed, dt_modified) = future.result()
            self.__update_cache(url, cache_entry, compressed_binary, hash_value, dt_accessed, dt_modified)
            results[url] = binary
        return [results[url] for url in url_list]

class DummyCache:
    def __init__(self, max_parallel_fetches=8):
        self.executor = concurrent.futures.ThreadPoolExecutor(max_workers=max_parallel_fetches)

    def fetch(self, url, use_cache_newer_than=None):
        (data, res) = url_readall(url)
        return data

    def fetch_all(self, url_list, use_cache_newer_than_list=None, use_cache_newer_than_map=None):
        futures = [self.executor.submit(self.fetch, url) for url in url_list]
        results = []
        for future in futures:
            try:
                results.append(future.result())
            except:
                results.append(None)
        return results
