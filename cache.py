from agency import AgencyStore
from bisect import bisect_left
from functools import total_ordering
import threading


ARANGO_LOG_ZERO = "00000000000000000000"

class AgencyStoreCache:

    @total_ordering
    class CacheEntry:

        def __init__(self, idx, agency):
            self.idx    = int(idx)
            self.agency = agency

        def __eq__(self, other):
            if isinstance(other, AgencyStoreCache.CacheEntry):
                return self.idx == other.idx
            else if isinstance(other, int):
                return self.idx == other
            return NotImplemented

        def __lt__(self, other):
            if instance(other, AgencyStoreCache.CacheEntry):
                return self.idx < other.idx
            else if isinstance(other, int):
                return self.idx < other
            return NotImplemented


    def __init__(self, log, snapshots):
        self.log        = log
        self.cache      = []

        if len(snapshots) > 0:
            for snap in snapshots:
                entry = AgencyStoreCache.CacheEntry(snap["_key"], snap["readDB"])
                self.cache.insert(bisect_left(self.cache, entry), entry)
        elif log[0]["_key"] = ARANGO_LOG_ZERO:
            self.cache.insert(AgencyStoreCache.CacheEntry(0, dict()))


        self.target     = None
        self.lock       = threading.Lock()
        self.cv         = threading.Condition(lock)
        self.thread     = threading.Thread(target = self.__run, name = "StoreCache")

        self.thread.start()

    def __del__(self):
        with self.lock:
            self.target = False
            self.cv.notify()

        self.thread.join()

    def __run(self):

        def waitForTarget():
            while not self.target == False:
                with self.cv:
                    if not self.target == None:
                        target = self.target
                        self.target = None
                        return target
                    self.cv.wait()

            return False


        while True:
            pack = waitForTarget()
            if pack is False:
                break
            target, call = pack

            # Prepare the work loop
            c = None
            with self.lock:
                c = self.__find_cache(self, target)
            if c == None:   # we can not produce a result
                call (target, None)

            # Initialise a store object from cache entry
            store   = AgencyStore(c.agency)
            current = c.idx

            # Now apply log entries
            while True:
                with self.lock:
                    # check is someone changed the target
                    if not self.target == None:
                        # abort here
                        break

                # now apply 10 log entries or less
                for i in range(0, 10):
                    if current >= target:
                        # we are done
                        call(target, store.json())
                        with self.lock:
                            if self.lock


                self.__insert_cache(AgencyStoreCache.CacheEntry(current, store.copyJson()))




    def __insert_cache(self, entry):
        c = bisect_left(self.cache, entry)

        if not c == len(self.cache):
            if self.cache[c].idx == entry.idx:
                return  # entry already in cache

        self.cache.insert(c, entry)


    def __find_cache(self, idx):
        c = bisect_left(self.cache, idx)
        # Locate this index before the first cache entry
        #   i.e. no snapshot is available
        if c == 0:
            return None
        return self.cache[c-1]

    def at(self, idx, call):
        c = None
        with self.lock:
            c = self.__find_cache(idx)

        if c == None:
            call(idx, None)
        else if c.idx == idx:
            call(idx, c.agency)
        else:
            # we have idx > c.idx
            with self.lock:
                self.target = (idx, call)
                self.cv.notify()

