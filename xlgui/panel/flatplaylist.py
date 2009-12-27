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

import gobject
import gtk

from xl.nls import gettext as _
from xlgui import panel, guiutil, menu
from xl import metadata

class FlatPlaylistPanel(panel.Panel):
    """
        Flat playlist panel; represents a single playlist
    """
    __gsignals__ = {
        'append-items': (gobject.SIGNAL_RUN_LAST, None, (object,)),
        'queue-items': (gobject.SIGNAL_RUN_LAST, None, (object,)),
    }

    ui_info = ('flatplaylist_panel.ui', 'FlatPlaylistPanelWindow')

    def __init__(self, parent, name=None):
        panel.Panel.__init__(self, parent, name)

        self.box = self.builder.get_object('FlatPlaylistPanel')
        self.model = gtk.ListStore(int, str, object)
        self.tracks = []
        self._setup_tree()
        if not hasattr(self.parent, 'do_import'):
            self.builder.get_object("import_button").hide()
        self.menu = menu.TrackSelectMenu()
        self._connect_events()

    def _connect_events(self):
        self.builder.connect_signals({
            'on_add_button_clicked': self._on_add_button_clicked,
            'on_import_button_clicked': self._on_import_button_clicked,
        })
        self.menu.connect('append-items', lambda *e:
            self.emit('append-items', self.get_selected_tracks()))
        self.menu.connect('queue-items', lambda *e:
            self.emit('queue-items', self.get_selected_tracks()))
        self.tree.connect('row-activated', lambda *e:
            self.emit('append-items', self.get_selected_tracks()))

    def _on_add_button_clicked(self, *e):
        self.emit('append-items', self.tracks)

    def _on_import_button_clicked(self, *e):
        tracks = self.get_selected_tracks()
        if len(tracks) == 0: # nothing selected, do everything
            tracks = self.tracks
        self.parent.do_import(tracks)

    def _setup_tree(self):
        self.tree = guiutil.DragTreeView(self, False, True)
        selection = self.tree.get_selection()
        selection.set_mode(gtk.SELECTION_MULTIPLE)

        self.tree.set_headers_visible(True)
        self.tree.set_model(self.model)
        self.scroll = gtk.ScrolledWindow()
        self.scroll.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.scroll.add(self.tree)
        self.scroll.set_shadow_type(gtk.SHADOW_IN)
        self.box.pack_start(self.scroll, True, True)

        text = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_('#'))
        col.pack_start(text, False)
        col.set_attributes(text, text=0)
        col.set_fixed_width(50)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_FIXED)
        self.tree.append_column(col)

        text = gtk.CellRendererText()
        col = gtk.TreeViewColumn(_('Title'))
        col.pack_start(text, True)
        col.set_attributes(text, text=1)
        col.set_sizing(gtk.TREE_VIEW_COLUMN_AUTOSIZE)
        col.set_cell_data_func(text, self._title_data_func)
        self.tree.append_column(col)
        self.box.show_all()

    def _title_data_func(self, col, cell, model, iter):
        if not model.iter_is_valid(iter): return
        item = model.get_value(iter, 2)
        cell.set_property('text', item.get_tag_display("title"))

    def set_playlist(self, pl):
        self.model.clear()

        tracks = pl.get_tracks()
        self.tracks = tracks
        for i, track in enumerate(tracks):
            self.model.append([i + 1, track.get_tag_display("title"), track])

    def get_selected_tracks(self):
        selection = self.tree.get_selection()
        (model, paths) = selection.get_selected_rows()

        tracks = []
        for path in paths:
            iter = self.model.get_iter(path)
            track = self.model.get_value(iter, 2)
            tracks.append(track)

        return tracks

    def button_press(self, button, event):
        """
            Called when the user clicks on the playlist
        """
        if event.button == 3:
            selection = self.tree.get_selection()
            (x, y) = map(int, event.get_coords())
            path = self.tree.get_path_at_pos(x, y)
            self.menu.popup(event)

            if not path:
                return False

            if len(self.get_selected_tracks()) >= 2:
                (mods,paths) = selection.get_selected_rows()
                if (path[0] in paths):
                    if event.state & (gtk.gdk.SHIFT_MASK|gtk.gdk.CONTROL_MASK):
                        return False
                    return True
                else:
                    return False
        return False

    def drag_data_received(self, *e):
        """
            stub
        """
        pass

    def drag_data_delete(self, *e):
        """
            stub
        """
        pass

    def drag_get_data(self, treeview, context, selection, target_id, etime):
        """
            Called when a drag source wants data for this drag operation
        """
        tracks = self.get_selected_tracks()
        if not tracks: return
        for track in tracks:
            guiutil.DragTreeView.dragged_data[track.get_loc_for_io()] = track
        urls = guiutil.get_urls_for(tracks)
        selection.set_uris(urls)

