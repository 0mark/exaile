# Copyright (C) 2008-2010 Adam Olsen
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 675 Mass Ave, Cambridge, MA 02139, USA.
#
#
# The developers of the Exaile media player hereby grant permission
# for non-GPL compatible GStreamer and Exaile plugins to be used and
# distributed together with GStreamer and Exaile. This permission is
# above and beyond the permissions granted by the GPL license by which
# Exaile is covered. If you modify this code, you may extend this
# exception to your version of the code, but you are not obligated to
# do so. If you do not wish to do so, delete this exception statement
# from your version.

import gio
import gobject
import logging
import os
import random
import string
import subprocess
import sys
import threading
import traceback
from functools import wraps
from collections import deque
from UserDict import DictMixin

logger = logging.getLogger(__name__)

#TODO: get rid of this. only plugins/cd/ uses it.
VALID_TAGS = (
    # Ogg Vorbis spec tags
    "title version album tracknumber artist genre performer copyright "
    "license organization description location contact isrc date "

    # Other tags we like
    "arranger author composer conductor lyricist discnumber labelid part "
    "website language encodedby bpm albumartist originaldate originalalbum "
    "originalartist recordingdate"
    ).split()

PICKLE_PROTOCOL=2


# use this for general logging of exceptions
def log_exception(log=logger, message="Exception caught!"):
    """
        Convenience function to log an exception + traceback

        :param log: the logger object to use.  important to specify
            so that it will be logged under the right module name.
        :param message: a message describing the error condition.
    """
    log.debug(message + "\n" + traceback.format_exc())

def to_unicode(x, default_encoding=None):
    """Force getting a unicode string from any object."""
    if isinstance(x, unicode):
        return x
    elif default_encoding and isinstance(x, str):
        # This unicode constructor only accepts "string or buffer".
        return unicode(x, default_encoding)
    else:
        return unicode(x)

def threaded(f):
    """
        A decorator that will make any function run in a new thread
    """
    @wraps(f)
    def wrapper(*args, **kwargs):
        t = threading.Thread(target=f, args=args, kwargs=kwargs)
        t.setDaemon(True)
        t.start()

    return wrapper

def synchronized(func):
    """
        A decorator to make a function synchronized - which means only one
        thread is allowed to access it at a time
    """
    @wraps(func)
    def wrapper(self, *__args, **__kw):
        try:
            rlock = self._sync_lock
        except AttributeError:
            from threading import RLock
            rlock = self.__dict__.setdefault('_sync_lock', RLock())
        rlock.acquire()
        try:
            return func(self, *__args, **__kw)
        finally:
            rlock.release()
    return wrapper

def profileit(func):
    """
        Decorator to profile a function
    """
    import hotshot, hotshot.stats
    @wraps(func)
    def wrapper(*args, **kwargs):
        prof = hotshot.Profile("profiling.data")
        res = prof.runcall(func, *args, **kwargs)
        prof.close()
        stats = hotshot.stats.load("profiling.data")
        stats.strip_dirs()
        stats.sort_stats('time', 'calls')
        print ">>>---- Begin profiling print"
        stats.print_stats()
        print ">>>---- End profiling print"
        return res
    return wrapper

def escape_xml(text):
    """
        Replaces &, <, and > with their entity references
    """
    # Note: the order is important.
    table = [('&', '&amp;'), ('<', '&lt;'), ('>', '&gt;')]
    for old, new in table:
        text = text.replace(old, new)
    return text

def random_string(n):
    """
        returns a random string of length n, comprised of ascii characters
    """
    s = ""
    for i in xrange(n):
        s += random.choice(string.ascii_letters)
    return s

class VersionError(Exception):
    """
       Represents version discrepancies
    """
    def __init__(self, message):
        Exception.__init__(self)
        self.message = message

    def __str__(self):
        return repr(self.message)

def open_file(path):
    """
        Opens a file or folder using the system configured program
    """
    platform = sys.platform
    if platform == 'win32':
        # pylint will error here on non-windows platforms unless we do this
        # pylint: disable-msg=E1101
        os.startfile(path)
        # pylint: enable-msg=E1101
    elif platform == 'darwin':
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])

def open_file_directory(path):
    """
        Opens the parent directory of a file, selecting the file if possible.
    """
    import gio
    f = gio.File(path)
    platform = sys.platform
    if platform == 'win32':
        subprocess.Popen(["explorer", "/select,", f.get_parse_name()])
    elif platform == 'darwin':
        subprocess.Popen(["open", f.get_parent().get_parse_name()])
    else:
        subprocess.Popen(["xdg-open", f.get_parent().get_parse_name()])

class LimitedCache(DictMixin):
    """
        Simple cache that acts much like a dict, but has a maximum # of items
    """
    def __init__(self, limit):
        self.limit = limit
        self.order = deque()
        self.cache = dict()

    def __iter__(self):
        return self.cache.__iter__()

    def __contains__(self, item):
        return self.cache.__contains__(item)

    def __delitem__(self, item):
        del self.cache[item]
        self.order.remove(item)

    def __getitem__(self, item):
        val = self.cache[item]
        self.order.remove(item)
        self.order.append(item)
        return val

    def __setitem__(self, item, value):
        self.cache[item] = value
        self.order.append(item)
        while len(self) > self.limit:
            del self.cache[self.order.popleft()]

    def keys(self):
        return self.cache.keys()

class cached(object):
    """
        Decorator to make a function's results cached

        does not cache if there is an exception.

        this probably breaks on functions that modify their arguments
    """
    def __init__(self, limit):
        self.limit = limit

    @staticmethod
    def _freeze(d):
        return frozenset(d.iteritems())

    def __call__(self, f):
        try:
            f._cache
        except AttributeError:
            f._cache = LimitedCache(self.limit)
        @wraps(f)
        def wrapper(*args, **kwargs):
            try:
                return f._cache[(args, self._freeze(kwargs))]
            except KeyError:
                pass
            ret = f(*args, **kwargs)
            f._cache[(args, self._freeze(kwargs))] = ret
            return ret
        return wrapper

def walk(root):
    """
        Walk through a Gio directory, yielding each file

        Files are enumerated in the following order: first the
        directory, then the files in that directory. Once one
        directory's files have all been listed, it moves on to
        the next directory. Order of files within a directory
        and order of directory traversal is not specified.

        :param root: a :class:`gio.File` representing the
            directory to walk through
        :returns: a generator object
        :rtype: :class:`gio.File`
    """
    queue = deque()
    queue.append(root)

    while len(queue) > 0:
        dir = queue.pop()
        yield dir
        try:
            for fileinfo in dir.enumerate_children("standard::type,"
                    "standard::is-symlink,standard::name,"
                    "standard::symlink-target,time::modified"):
                fil = dir.get_child(fileinfo.get_name())
                # FIXME: recursive symlinks could cause an infinite loop
                if fileinfo.get_is_symlink():
                    target = fileinfo.get_symlink_target()
                    if not "://" in target and not os.path.isabs(target):
                        fil2 = dir.get_child(target)
                    else:
                        fil2 = gio.File(target)
                    # already in the collection, we'll get it anyway
                    if fil2.has_prefix(root):
                        continue
                type = fileinfo.get_file_type()
                if type == gio.FILE_TYPE_DIRECTORY:
                    queue.append(fil)
                elif type == gio.FILE_TYPE_REGULAR:
                    yield fil
        except gio.Error, e: # why doesnt gio offer more-specific errors?
            log_exception(e)

def walk_directories(root):
    """
        Walk through a Gio directory, yielding each subdirectory

        :param root: a :class:`gio.File` representing the
            directory to walk through
        :returns: a generator object
        :rtype: :class:`gio.File`
    """
    yield root

    try:
        for fileinfo in root.enumerate_children(
                'standard::name,standard::type'):
            if fileinfo.get_file_type() == gio.FILE_TYPE_DIRECTORY:
                directory = root.get_child(fileinfo.get_name())

                for subdirectory in walk_directories(directory):
                    yield subdirectory
    except gio.Error, e:
        log_exception(e)

class TimeSpan:
    """
        Calculates the amount of years, days,
        hours, minutes and seconds of a time span
    """
    _seconds_per_minute = 60.0
    _seconds_per_hour = 60 * _seconds_per_minute
    _seconds_per_day = 24 * _seconds_per_hour
    # XXX: Check leap years
    _seconds_per_year = 365 * _seconds_per_day

    def __init__(self, span):
        """
            :param span: Time span in seconds
            :type span: float
        """
        try:
            span = float(span)
        except:
            span = 0

        self.years = span // self._seconds_per_year
        span %= self._seconds_per_year

        self.days = span // self._seconds_per_day
        span %= self._seconds_per_day

        self.hours = span // self._seconds_per_hour
        span %= self._seconds_per_hour

        self.minutes = span // self._seconds_per_minute
        span %= self._seconds_per_minute

        self.seconds = span

    def __repr__(self):
        return str(self)

    def __str__(self):
        return '%dy, %dd, %dh, %dm, %ds' % (
            self.years, self.days, self.hours,
            self.minutes, self.seconds
        )

class MetadataList(object):
    __slots__ = ['__list', 'metadata']
    """
        Like a list, but also associates an object of metadata
        with each entry.

        (get|set|del)_meta_key are the metadata interface - they
        allow the metadata to act much like a dictionary, with a few
        optimizations.

        List aspects that are not supported:
            sort
            comparisons other than equality
            multiply
    """
    def __init__(self, iterable=[], metadata=[]):
        self.__list = list(iterable)
        meta = list(metadata)
        if meta and len(meta) != len(self.__list):
            raise ValueError, "Length of metadata must match length of items."
        if not meta:
            meta = [None] * len(self.__list)
        self.metadata = meta

    def __repr__(self):
        return "MetadataList(%s)"%self.__list

    def __len__(self):
        return len(self.__list)

    def __iter__(self):
        return self.__list.__iter__()

    def __add__(self, other):
        l = MetadataList(self, self.metadata)
        l.extend(other)
        return l

    def __iadd__(self, other):
        self.extend(other)
        return self

    def __eq__(self, other):
        if isinstance(other, MetadataList):
            other = list(other)
        return self.__list == other

    def __getitem__(self, i):
        val = self.__list.__getitem__(i)
        if isinstance(i, slice):
            return MetadataList(val, self.metadata.__getitem__(i))
        else:
            return val

    def __setitem__(self, i, value):
        self.__list.__setitem__(i, value)
        if isinstance(value, MetadataList):
            metadata = list(value.metadata)
        else:
            metadata = [None]*len(value)
        self.metadata.__setitem__(i, metadata)

    def __delitem__(self, i):
        self.__list.__delitem__(i)
        self.metadata.__delitem__(i)

    def append(self, other, metadata=None):
        self.insert(len(self), other, metadata=metadata)

    def extend(self, other):
        self[len(self):len(self)] = other

    def insert(self, i, item, metadata=None):
        if i >= len(self):
            i = len(self)
            e = len(self)+1
        else:
            e = i
        self[i:e] = [item]
        self.metadata[i:e] = [metadata]

    def pop(self, i=-1):
        item = self[i]
        del self[i]
        return item

    def remove(self, item):
        del self[self.index(item)]

    def reverse(self):
        self.__list.reverse()
        self.metadata.reverse()

    def index(self, i, start=0, end=None):
        if end is None:
            return self.__list.index(i, start)
        else:
            return self.__list.index(i, start, end)

    def count(self, i):
        return self.__list.count(i)

    def get_meta_key(self, index, key, default=None):
        if not self.metadata[index]:
            return default
        return self.metadata[index].get(key, default)

    def set_meta_key(self, index, key, value):
        if not self.metadata[index]:
            self.metadata[index] = {}
        self.metadata[index][key] = value

    def del_meta_key(self, index, key):
        if not self.metadata[index]:
            raise KeyError, key
        del self.metadata[index][key]
        if not self.metadata[index]:
            self.metadata[index] = None

class ProgressThread(gobject.GObject, threading.Thread):
    """
        A basic thread with progress updates
    """
    __gsignals__ = {
        'progress-update': (
            gobject.SIGNAL_RUN_FIRST,
            gobject.TYPE_NONE,
            (gobject.TYPE_INT,)
        ),
        # TODO: Check if 'stopped' is required
        'done': (
            gobject.SIGNAL_RUN_FIRST,
            gobject.TYPE_NONE,
            ()
        )
    }

    def __init__(self):
        gobject.GObject.__init__(self)
        threading.Thread.__init__(self)
        self.setDaemon(True)

    def stop(self):
        """
            Stops the thread
        """
        self.emit('done')

    def run(self):
        """
            Override and make sure that the 'progress-update'
            signal is emitted regularly with the progress
        """
        pass

# vim: et sts=4 sw=4
