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

import gtk

from xl.nls import gettext as _
from xl import providers, player, event
from xlgui.widgets import menu
from xlgui.widgets.notebook import NotebookPage
from xlgui.widgets.playlist import PlaylistView



def __create_queue_tab_context_menu():
    smi = menu.simple_menu_item
    sep = menu.simple_separator
    items = []
    items.append(smi('clear', [], _("Clear"), 'gtk-clear',
        lambda w, n, o, c: player.QUEUE.clear()))
    items.append(sep('tab-close-sep', ['clear']))
    items.append(smi('tab-close', ['tab-close-sep'], _("Close"), 'gtk-close',
        lambda w, n, o, c: o.tab.close()))
    for item in items:
        providers.register('queue-tab-context', item)
__create_queue_tab_context_menu()

class QueuePage(NotebookPage):
    menu_provider_name = 'queue-tab-context'
    def __init__(self):
        NotebookPage.__init__(self)

        self.swindow = gtk.ScrolledWindow()
        self.swindow.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
        self.pack_start(self.swindow, True, True)

        self.view = PlaylistView(player.QUEUE)
        self.swindow.add(self.view)

        event.add_callback(self.on_length_changed, "playlist_tracks_added", player.QUEUE)
        event.add_callback(self.on_length_changed, "playlist_tracks_removed", player.QUEUE)

        self.show_all()

    def on_length_changed(self, *args):
        self.name_changed()
        if len(player.QUEUE) == 0:
            self.tab.set_closable(True)
        else:
            self.tab.notebook.show_queue(switch=False)
            self.tab.set_closable(False)


    ## NotebookPage API ##

    def get_name(self):
        return _("Queue (%d)") % len(player.QUEUE)

    def set_tab(self, tab):
        NotebookPage.set_tab(self, tab)
        tab.set_closable(False)

    def do_closing(self):
        """
            Allows closing only if the queue is empty
        """
        return len(player.QUEUE) != 0

    ## End NotebookPage ##



# vim: et sw=4 st=4
