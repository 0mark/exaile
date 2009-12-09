# Copyright (C) 2008-2009 Adam Olsen
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


import logging
import shelve
import traceback
from copy import deepcopy
try:
    import cPickle as pickle
except:
    import pickle

from xl import common, event, xdg
from xl.nls import gettext as _

from track import Track
from util import sort_tracks
from search import search_tracks_from_string

logger = logging.getLogger(__name__)


class TrackHolder(object):
    def __init__(self, track, key, **kwargs):
        self._track = track
        self._key = key
        self._attrs = kwargs

    def __getattr__(self, attr):
        return getattr(self._track, attr)

class TrackDBIterator(object):
    def __init__(self, track_iterator):
        self.iter = track_iterator

    def __iter__(self):
        return self

    def next(self):
        return self.iter.next()[1]._track

class TrackDB(object):
    """
        Manages a track database.

        Allows you to add, remove, retrieve, search, save and load
        Track objects.

        :param name:   The name of this :class:`TrackDB`.
        :param location:   Path to a file where this :class:`TrackDB`
                should be stored.
        :param pickle_attrs:   A list of attributes to store in the
                pickled representation of this object. All
                attributes listed must be built-in types, with
                one exception: If the object contains the phrase
                'tracks' in its name it may be a list or dict
                of :class:`Track` objects.
    """
    def __init__(self, name="", location="", pickle_attrs=[]):
        """
            Sets up the trackDB.
        """
        self.name = name
        self.location = location
        self._dirty = False
        self.tracks = {}
        self.pickle_attrs = pickle_attrs
        self.pickle_attrs += ['tracks', 'name', '_key']
        self._saving = False
        self._key = 0
        self._dbversion = 2.0
        self._dbminorversion = 0
        self._deleted_keys = []
        if location:
            self.load_from_location()
            event.timeout_add(300000, self._timeout_save)

    def __iter__(self):
        """
            Provide the ability to iterate over a TrackDB.
            Just as with a dictionary, if tracks are added
            or removed during iteration, iteration will halt
            wuth a RuntimeError.
        """
        track_iterator = self.tracks.iteritems()
        iterator = TrackDBIterator(track_iterator)
        return iterator

    def __len__(self):
        """
            Obtain a count of how many items are in the TrackDB
        """
        return len(self.tracks)

    def _timeout_save(self):
        """
            Callback for auto-saving.
        """
        self.save_to_location()
        return True

    def set_name(self, name):
        """
            Sets the name of this :class:`TrackDB`

            :param name:   The new name.
            :type name: string
        """
        self.name = name
        self._dirty = True

    def get_name(self):
        """
            Gets the name of this :class:`TrackDB`

            :return: The name.
            :rtype: string
        """
        return self.name

    def set_location(self, location):
        """
            Sets the location to save to

            :param location: the location to save to
        """
        self.location = location
        self._dirty = True

    @common.synchronized
    def load_from_location(self, location=None):
        """
            Restores :class:`TrackDB` state from the pickled representation
            stored at the specified location.

            :param location: the location to load the data from
            :type location: string
        """
        if not location:
            location = self.location
        if not location:
            raise AttributeError(
                    _("You did not specify a location to load the db from"))

        try:
            pdata = shelve.open(self.location, flag='c',
                    protocol=common.PICKLE_PROTOCOL)
            if pdata.has_key("_dbversion"):
                if int(pdata['_dbversion']) > int(self._dbversion):
                    raise common.VersionError, \
                            "DB was created on a newer Exaile version."
                elif pdata['_dbversion'] < self._dbversion:
                    logger.info("Upgrading DB format....")
                    import xl.migrations.database as dbmig
                    dbmig.handle_migration(self, pdata, pdata['_dbversion'],
                            self._dbversion)

        except common.VersionError:
            raise
        except:
            logger.error("Failed to open music DB.")
            common.log_exception(log=logger)
            return

        for attr in self.pickle_attrs:
            try:
                if 'tracks' == attr:
                    data = {}
                    for k in (x for x in pdata.keys() \
                            if x.startswith("tracks-")):
                        p = pdata[k]
                        tr = Track(_unpickles=p[0])
                        data[tr.get_loc_for_io()] = TrackHolder(tr, p[1], **p[2])
                    setattr(self, attr, data)
                else:
                    setattr(self, attr, pdata[attr])
            except:
                pass #FIXME

        pdata.close()

        self._dirty = False

    @common.synchronized
    def save_to_location(self, location=None):
        """
            Saves a pickled representation of this :class:`TrackDB` to the
            specified location.

            :param location: the location to save the data to
            :type location: string
        """
        if not self._dirty:
            for k, track in self.tracks.iteritems():
                if track._track._dirty:
                    self._dirty = True
                    break

        if not self._dirty:
            return

        if not location:
            location = self.location
        if not location:
            raise AttributeError(_("You did not specify a location to save the db"))

        if self._saving:
            return
        self._saving = True

        logger.debug("Saving %(name)s DB to %(location)s." %
            {'name' : self.name, 'location' : location or self.location})

        try:
            pdata = shelve.open(self.location, flag='c',
                    protocol=common.PICKLE_PROTOCOL)
            if pdata.has_key("_dbversion"):
                if pdata['_dbversion'] > self._dbversion:
                    raise ValueError, "DB was created on a newer Exaile version."
        except:
            logger.error("Failed to open music DB for write.")
            return

        for attr in self.pickle_attrs:
            # bad hack to allow saving of lists/dicts of Tracks
            if 'tracks' == attr:
                for k, track in self.tracks.iteritems():
                    if track._track._dirty or "tracks-%s"%track._key not in pdata:
                        pdata["tracks-%s"%track._key] = (
                                track._track._pickles(),
                                track._key,
                                deepcopy(track._attrs))
            else:
                pdata[attr] = deepcopy(getattr(self, attr))

        pdata['_dbversion'] = self._dbversion

        for key in self._deleted_keys:
            if "tracks-%s"%key in pdata:
                del pdata["tracks-%s"%key]

        pdata.sync()
        pdata.close()

        for track in self.tracks.itervalues():
            if track._track._dirty:
                track._dirty = False

        self._dirty = False
        self._saving = False

    def get_track_by_loc(self, loc, raw=False):
        """
            returns the track having the given loc. if no such track exists,
            returns None
        """
        try:
            return self.tracks[loc]._track
        except KeyError:
            return None

    def get_tracks_by_locs(self, locs):
        """
            returns the track having the given loc. if no such track exists,
            returns None
        """
        return [self.get_track_by_loc(loc) for loc in locs]

    def loc_is_member(self, loc):
        """
            Returns True if loc is a track in this collection, False
            if it is not
        """
        # check for the actual track
        if self.get_track_by_loc(loc):
            return True
        else:
            return False

    def get_count(self):
        """
            Returns the number of tracks stored in this database
        """
        count = len(self.tracks)
        return count

    def add(self, track):
        """
            Adds a track to the database of tracks

            :param track: The :class:`xl.track.Track` to add
        """
        self.add_tracks([track])

    @common.synchronized
    def add_tracks(self, tracks):
        """
            Like add(), but takes a list of :class:`xl.track.Track`
        """
        for tr in tracks:
            self.tracks[tr.get_loc_for_io()] = TrackHolder(tr, self._key)
            self._key += 1
            event.log_event("track_added", self, tr.get_loc_for_io())
        self._dirty = True

    def remove(self, track):
        """
            Removes a track from the database

            :param track: the :class:`xl.track.Track` to remove
        """
        self.remove_tracks([track])

    @common.synchronized
    def remove_tracks(self, tracks):
        """
            Like remove(), but takes a list of :class:`xl.track.Track`
        """
        for tr in tracks:
            self._deleted_keys.append(self.tracks[tr.get_loc_for_io()]._key)
            del self.tracks[tr.get_loc_for_io()]
            event.log_event("track_removed", self, tr.get_loc_for_io())
        self._dirty = True

    def get_tracks(self):
        return list(self)


    def search(self, query, sort_fields=[], return_lim=-1, tracks=None, reverse=False):
        """
            Search the trackDB, optionally sorting by sort_field

            :param query:  the search
            :param sort_fields:  the field(s) to sort by.  Use RANDOM to sort
                randomly.
            :type sort_fields: A string or list of strings
            :param return_lim:  limit the number of tracks returned to a
                maximum
        """
        import warnings
        warnings.warn("TrackDB.search is deprecated.", DeprecationWarning)
        tracks = [ x.track for x in search_tracks_from_string(self, query, case_sensitive=False, keyword_tags=['artist', 'albumartist', 'album', 'title']) ]

        if sort_fields:
            if sort_fields == 'RANDOM':
                random.shuffle(tracks)
            else:
                tracks = sort_tracks(sort_fields, tracks, reverse)
        if return_lim > 0:
            tracks = tracks[:return_lim]

        return tracks




# vim: et sts=4 sw=4

