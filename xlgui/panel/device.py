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

import threading

import gobject
import gtk

from xl.nls import gettext as _
from xl import event
from xlgui import panel
from xlgui.panel.collection import CollectionPanel
from xlgui.panel.flatplaylist import FlatPlaylistPanel


class DeviceTransferThread(threading.Thread):
    def __init__(self, device, main, panel):
        threading.Thread.__init__(self)
        self.setDaemon(True)

        self.device = device
        self.main = main
        self.panel = panel

    def stop_thread(self):
        self.device.transfer.cancel()

    def thread_complete(self):
        """
            Called when the thread has finished normally
        """
        gobject.idle_add(self.panel.load_tree)

    def progress_update(self, type, transfer, progress):
        event.log_event('progress_update', self, progress)

    def run(self):
        """
            Runs the thread
        """
        event.add_callback(self.progress_update, 'track_transfer_progress',
            self.device.transfer)
        try:
            self.device.start_transfer()
        finally:
            event.remove_callback(self.progress_update, 'track_transfer_progress',
                self.device.transfer)

class ReceptiveCollectionPanel(CollectionPanel):
    def drag_data_received(self, widget, context, x, y, data, info, stamp):
        uris = data.get_uris()
        tracks, playlists = self.tree.get_drag_data(uris)
        tracks = [ t for t in tracks if not \
                self.collection.loc_is_member(t.get_loc_for_io()) ]

        self.add_tracks_func(tracks)

    def add_tracks_func(self, tracks):
        locs = [ t['__loc'] for t in tracks ]
        # FIXME:
        lib = self.collection.get_libraries()[0]

        # TODO: there should be a queue for ipod and such devices,
        # otherwise you'll have to write the database on every track add and
        # that won't be good
        # this _needs_ to be asynchronous
        for l in locs:
            lib.add(l)

class DevicePanel(panel.Panel):
    """
        generic panel for devices
    """
    __gsignals__ = {
        'append-items': (gobject.SIGNAL_RUN_LAST, None, (object,)),
        'replace-items': (gobject.SIGNAL_RUN_LAST, None, (object,)),
        'queue-items': (gobject.SIGNAL_RUN_LAST, None, (object,)),
        'collection-tree-loaded': (gobject.SIGNAL_RUN_LAST, None, ()),
    }

    ui_info = ('device_panel.ui', 'DevicePanelWindow')

    def __init__(self, parent, main,
        device, name=None):

        panel.Panel.__init__(self, name)
        self.device = device
        self.main = main

        self.notebook = self.builder.get_object("device_notebook")

        self.collectionpanel = ReceptiveCollectionPanel(parent,
            collection=device.collection, name=name)
        self.collectionpanel.add_tracks_func = self.add_tracks_func

        self.collectionpanel.connect('append-items',
            lambda *e: self.emit('append-items', *e[1:]))
        self.collectionpanel.connect('replace-items',
            lambda *e: self.emit('replace-items', *e[1:]))
        self.collectionpanel.connect('queue-items',
            lambda *e: self.emit('queue-items', *e[1:]))
        self.collectionpanel.connect('collection-tree-loaded',
            lambda *e: self.emit('collection-tree-loaded'))

    def add_tracks_func(self, tracks):
        self.device.add_tracks(tracks)
        thread = DeviceTransferThread(self.device, self.main, self)
        self.main.controller.progress_manager.add_monitor(thread,
                _("Transferring to %s...")%self.name, gtk.STOCK_GO_UP)

    def get_panel(self):
        return self.collectionpanel.get_panel()

    def add_panel(self, child, name):
        label = gtk.Label(name)
        self.notebook.append_page(child, label)

    def load_tree(self, *args):
        self.collectionpanel.load_tree(*args)

class FlatPlaylistDevicePanel(panel.Panel):
    __gsignals__ = {
        'append-items': (gobject.SIGNAL_RUN_LAST, None, (object,)),
        'queue-items': (gobject.SIGNAL_RUN_LAST, None, (object,)),
    }

    ui_info = ('device_panel.ui', 'DevicePanelWindow')

    def __init__(self, parent, main,
        device, name=None):

        panel.Panel.__init__(self, name)
        self.device = device
        self.main = main

        self.notebook = self.builder.get_object("device_notebook")

        self.fppanel = FlatPlaylistPanel(self, name)

        self.fppanel.connect('append-items',
            lambda *e: self.emit('append-items', *e[1:]))
        self.fppanel.connect('queue-items',
            lambda *e: self.emit('queue-items', *e[1:]))

    def get_panel(self):
        return self.fppanel.get_panel()

    def add_panel(self, child, name):
        label = gtk.Label(name)
        self.notebook.append_page(child, label)

    def load_tree(self, *e):
        # TODO: handle *all* the playlists
        self.fppanel.set_playlist(
            self.device.get_playlists()[0])
