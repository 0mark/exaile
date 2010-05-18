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

import time
import logging
import traceback

import gio
import glib
import gobject
import gtk

from xl.nls import gettext as _
from xl import (
    common,
    event,
    metadata,
    settings,
    xdg
)
from xl.covers import MANAGER as cover_manager
from xlgui import commondialogs, guiutil, icons
logger = logging.getLogger(__name__)

class CoverManager(object):
    """
        Cover manager window
    """
    def __init__(self, parent, collection):
        """
            Initializes the window
        """
        self.parent = parent
        self.collection = collection

        self.cover_nodes = {}
        self.covers = {}
        self.track_dict = {}
        self._stopped = True

        self.builder = gtk.Builder()
        self.builder.add_from_file(xdg.get_data_path('ui/covermanager.ui'))

        self.window = self.builder.get_object('CoverManager')
        self.window.set_transient_for(parent)

        self.icons = self.builder.get_object('cover_icon_view')
        self.icons.connect('button-press-event',
            self._on_button_press)
        self.progress = self.builder.get_object('progress')
        self.stop_button = self.builder.get_object('stop_button')
        self.model = gtk.ListStore(str, gtk.gdk.Pixbuf, object)
        self.icons.set_item_width(100)

        self.icons.set_text_column(0)
        self.icons.set_pixbuf_column(1)

        self.nocover = icons.MANAGER.pixbuf_from_data(
            cover_manager.get_default_cover(), size=(80,80))

        self._connect_events()
        self.window.show_all()
        gobject.idle_add(self._find_initial)
        self.menu = CoverMenu(self)

    def _on_button_press(self, button, event):
        """
            Called when someone clicks on the cover widget
        """
        if event.type == gtk.gdk._2BUTTON_PRESS:
            self.show_cover()
        elif event.button == 3:
            self.menu.popup(event)

        # select the current icon
        x, y = map(int, event.get_coords())
        path = self.icons.get_path_at_pos(x, y)
        if path:
            self.icons.select_path(path)

    def get_selected_cover(self):
        """
            Returns the currently selected cover tuple
        """
        paths = self.icons.get_selected_items()
        if paths:
            path = paths[0]
            iter = self.model.get_iter(path)
            return self.model.get_value(iter, 2)

    def show_cover(self, *e):
        """
            Shows the currently selected cover
        """
        item = self._get_selected_item()
        c = cover_manager.get_cover(self.track_dict[item][0])

        cvr = icons.MANAGER.pixbuf_from_data(c)
        if cvr:
            window = CoverWindow(self.parent, cvr)
            window.show_all()

    def fetch_cover(self):
        """
            Fetches a cover for the current track
        """
        item = self._get_selected_item()
        if item:
            track = self.track_dict[item][0]
            window = CoverChooser(self.window, track)
            window.connect('cover-chosen', self.on_cover_chosen)

    def on_cover_chosen(self, object, cvr):
        paths = self.icons.get_selected_items()
        if not paths:
            return None
        path = paths[0]
        iter = self.model.get_iter(path)
        item = self.model.get_value(iter, 2)

        image = icons.MANAGER.pixbuf_from_data(cvr[1])
        image = image.scale_simple(80, 80, gtk.gdk.INTERP_BILINEAR)
        self.covers[item] = image
        self.model.set_value(iter, 1, image)

    def _get_selected_item(self):
        """
            Returns the selected item
        """
        paths = self.icons.get_selected_items()
        if not paths:
            return None
        path = paths[0]
        iter = self.model.get_iter(path)
        item = self.model.get_value(iter, 2)
        return item

    def remove_cover(self, *e):
        item = self._get_selected_item()
        paths = self.icons.get_selected_items()
        track = self.track_dict[item][0]
        cover_manager.remove_cover(track)
        self.covers[item] = self.nocover
        if paths:
            iter = self.model.get_iter(paths[0])
            self.model.set_value(iter, 1, self.nocover)

    def _find_initial(self):
        """
            Locates covers and sets the icons in the windows
        """
        items = set()
        for track in self.collection:
            try:
                artist = track.get_tag_raw('artist')[0]
                album = track.get_tag_raw('album')[0]
            except TypeError:
                continue

            if not album or not artist:
                continue

            item = (artist, album)

            try:
                self.track_dict[item].append(track)
            except KeyError:
                self.track_dict[item] = [track]

            items.add(item)

        self.items = list(items)
        self.items.sort()

        self.needs = 0
        for item in self.items:
            cover_avail = cover_manager.get_cover(self.track_dict[item][0],
                set_only=True)

            if cover_avail:
                try:
                    image = icons.MANAGER.pixbuf_from_data(
                        cover_avail, size=(80,80))
                except gobject.GError:
                    image = self.nocover
                    self.needs += 1
            else:
                image = self.nocover
                self.needs += 1

            display = "%s - %s" % item

            self.cover_nodes[item] = self.model.append([display, image, item])
            self.covers[item] = image
        self.icons.set_model(self.model)
        self.progress.set_text(_('%d covers to fetch') % self.needs)

    def _connect_events(self):
        """
            Connects the various events
        """
        self.builder.connect_signals({
            'on_stop_button_clicked': self._toggle_find,
            'on_cancel_button_clicked': self._on_destroy
        })

        self.window.connect('delete-event', self._on_destroy)

    @common.threaded
    def _find_covers(self):
        """
            Finds covers for albums that don't already have one
        """
        self.count = 0
        self._stopped = False
        for item in self.items:
            if self._stopped:
                gobject.idle_add(self._do_stop)
                return
            starttime = time.time()
            if not self.covers[item] == self.nocover:
                continue

            c = cover_manager.get_cover(self.track_dict[item][0],
                    save_cover=True)

            if c:
                node = self.cover_nodes[item]
                try:
                    image = icons.MANAGER.pixbuf_from_data(c, size=(80,80))
                except gobject.GError:
                    c = None
                else:
                    gobject.idle_add(self.model.set_value, node, 1, image)

            gobject.idle_add(self.progress.set_fraction, float(self.count) /
                float(self.needs))
            gobject.idle_add(self.progress.set_text, "%s/%s fetched" %
                    (self.count, self.needs))

            self.count += 1

            if self.count % 20 == 0:
                logger.debug("Saving cover database")
                cover_manager.save()

        gobject.idle_add(self._do_stop)

    def _calculate_needed(self):
        """
            Calculates the number of needed covers
        """
        self.needs = 0
        for item in self.items:
            cvr = self.covers[item]
            if cvr == self.nocover:
                self.needs += 1

    def _do_stop(self):
        """
            Actually stop the finder thread
        """
        self._calculate_needed()
        self.progress.set_text(_('%d covers to fetch') % self.needs)
        self.progress.set_fraction(0)
        self._stopped = True
        cover_manager.save()
        self.stop_button.set_use_stock(False)
        self.stop_button.set_label(_('Start'))
        self.stop_button.set_image(gtk.image_new_from_stock(gtk.STOCK_YES,
            gtk.ICON_SIZE_BUTTON))

    def _on_destroy(self, *e):
        self._do_stop()
        self.window.hide()

    def _toggle_find(self, *e):
        """
            Toggles cover finding
        """
        if self._stopped:
            self.stop_button.set_use_stock(True)
            self.stop_button.set_label(gtk.STOCK_STOP)
            self._find_covers()
        else:
            self._stopped = True
            self.stop_button.set_use_stock(False)
            self.stop_button.set_label(_('Start'))
            self.stop_button.set_image(gtk.image_new_from_stock(gtk.STOCK_YES,
                gtk.ICON_SIZE_BUTTON))

class CoverMenu(guiutil.Menu):
    """
        Cover menu
    """
    def __init__(self, widget):
        """
            Initializes the menu
        """
        guiutil.Menu.__init__(self)
        self.widget = widget

        self.append(_('Show Cover'), self.on_show_clicked)
        self.append(_('Fetch Cover'), self.on_fetch_clicked)
        self.append(_('Remove Cover'), self.on_remove_clicked)

    def on_show_clicked(self, *e):
        """
            Shows the current cover
        """
        self.widget.show_cover()

    def on_fetch_clicked(self, *e):
        self.widget.fetch_cover()

    def on_remove_clicked(self, *e):
        self.widget.remove_cover()

class CoverWidget(gtk.EventBox):
    """
        Represents the cover widget displayed by the track information
    """
    __gsignals__ = {
        'cover-found': (gobject.SIGNAL_RUN_LAST, None, (object,)),
    }
    def __init__(self, image, player):
        """
            Initializes the widget

            :param image: the image to wrap
            :type image: :class:`gtk.Image`
            :param player: the player
            :type player: :class: `xl.player.Player`
        """
        gtk.EventBox.__init__(self)
        self.image = image 
        self.player = player
        self.menu = CoverMenu(self)
        self.parent_window = image.get_toplevel()

        guiutil.gtk_widget_replace(image, self)
        self.add(self.image)
        self.set_blank()
        self.image.show()

        self.drag_dest_set(gtk.DEST_DEFAULT_ALL,
            [("text/uri-list", 0, 0)],
            gtk.gdk.ACTION_COPY |
            gtk.gdk.ACTION_DEFAULT |
            gtk.gdk.ACTION_MOVE)

        self.connect('button-press-event', self.on_button_press)
        self.connect('drag-data-received', self.on_drag_data_received)

        event.add_callback(self.on_playback_start,
                'playback_track_start', player)
        event.add_callback(self.on_playback_end,
                'playback_player_end', player)

    def destroy(self):
        event.remove_callback(self.on_playback_start,
                'playback_track_start', player)
        event.remove_callback(self.on_playback_end,
                'playback_player_end', player)

    def show_cover(self):
        """
            Shows the current cover
        """
        window = CoverWindow(self.parent_window, self.image.get_pixbuf())
        window.show_all()

    def fetch_cover(self):
        """
            Fetches a cover for the current track
        """
        if not self.player.current: return
        window = CoverChooser(self.parent_window, self.player.current)
        window.connect('cover-chosen', self.on_cover_chosen)

    def remove_cover(self):
        """
            Removes the cover for the current track from the database
        """
        cover_manager.remove_cover(self.player.current)
        self.set_blank()

    def set_blank(self):
        """
            Sets the default cover to display
        """
        pixbuf = icons.MANAGER.pixbuf_from_data(cover_manager.get_default_cover())
        self.image.set_from_pixbuf(pixbuf)
        self.emit('cover-found', None)

    def on_button_press(self, button, event):
        """
            Called when someone clicks on the cover widget
        """
        if self.player.current is None or self.parent_window is None:
            return

        if event.type == gtk.gdk._2BUTTON_PRESS:
            window = CoverWindow(self.parent_window, self.image.get_pixbuf())
            window.show_all()
        elif event.button == 3:
            self.menu.popup(event)

    def on_cover_chosen(self, object, cover_data):
        """
            Called when a cover is selected
            from the coverchooser
        """
        pixbuf = icons.MANAGER.pixbuf_from_data(cover_data)
        width = settings.get_option('gui/cover_width', 100)
        pixbuf = pixbuf.scale_simple(width, width, gtk.gdk.INTERP_BILINEAR)
        self.image.set_from_pixbuf(pixbuf)
        self.emit('cover-found', pixbuf)

    def on_drag_data_received(self, widget, context, x, y, selection, info, time):
        """
            Sets the cover based on the dragged data
        """
        if self.player.current is not None:
            uri = selection.get_uris()[0]
            db_string = 'localfile:%s' % uri

            try:
                stream = gio.File(uri).read()
            except gio.Error:
                return

            data = stream.read()
            pixbuf = self.image.pixbuf

            try:
                self.image.set_image_data(data)
            except glib.GError: # No valid image dropped
                self.image.pixbuf = pixbuf
            else:
                cover_manager.set_cover(self.player.current, db_string, data)

    @common.threaded
    def on_playback_start(self, type, player, track):
        """
            Called when playback starts.  Fetches album covers, and displays
            them
        """
        gobject.idle_add(self.set_blank)
        fetch = not settings.get_option('covers/automatic_fetching', True)
        cover_data = cover_manager.get_cover(track, set_only=fetch)
        if not cover_data:
            return

        if self.player.current == track:
            gobject.idle_add(self.on_cover_chosen, None, cover_data)

    def on_playback_end(self, type, player, object):
        """
            Called when playback stops.  Resets to the nocover image
        """
        self.set_blank()

class CoverWindow(object):
    """Shows the cover in a simple image viewer"""

    def __init__(self, parent, cvr, title=''):
        """Initializes and shows the cover"""
        self.builder = gtk.Builder()
        self.builder.add_from_file(xdg.get_data_path('ui/coverwindow.ui'))
        self.builder.connect_signals(self)
        self.cover_window = self.builder.get_object('CoverWindow')
        self.layout = self.builder.get_object('layout')
        self.toolbar = self.builder.get_object('toolbar')
        self.zoom_in = self.builder.get_object('zoom_in')
        self.zoom_out = self.builder.get_object('zoom_out')
        self.zoom_100 = self.builder.get_object('zoom_100')
        self.zoom_fit = self.builder.get_object('zoom_fit')
        self.image = self.builder.get_object('image')
        self.statusbar = self.builder.get_object('statusbar')
        self.scrolledwindow = self.builder.get_object('scrolledwindow')
        self.scrolledwindow.set_hadjustment(self.layout.get_hadjustment())
        self.scrolledwindow.set_vadjustment(self.layout.get_vadjustment())
        self.cover_window.set_title(title)
        self.cover_window.set_transient_for(parent)
        self.cover_window_width = 500
        self.cover_window_height = 500 + self.toolbar.size_request()[1] + \
                                   self.statusbar.size_request()[1]
        self.cover_window.set_default_size(self.cover_window_width, \
                                           self.cover_window_height)
        self.image_original_pixbuf = cvr
        self.image_pixbuf = self.image_original_pixbuf
        self.min_percent = 1
        self.max_percent = 500
        self.ratio = 1.5
        self.image_interp = gtk.gdk.INTERP_BILINEAR
        self.image_fitted = True
        self.set_ratio_to_fit()
        self.update_widgets()

    def show_all(self):
        self.cover_window.show_all()

    def available_image_width(self):
        """Returns the available horizontal space for the image"""
        return self.cover_window.get_size()[0]

    def available_image_height(self):
        """Returns the available vertical space for the image"""
        return self.cover_window.get_size()[1] - \
               self.toolbar.size_request()[1] - \
               self.statusbar.size_request()[1]

    def center_image(self):
        """Centers the image in the layout"""
        new_x = max(0, int((self.available_image_width() - \
                            self.image_pixbuf.get_width()) / 2))
        new_y = max(0, int((self.available_image_height() - \
                            self.image_pixbuf.get_height()) / 2))
        self.layout.move(self.image, new_x, new_y)

    def update_widgets(self):
        """Updates image, layout, scrolled window, tool bar and status bar"""
        if self.cover_window.window:
            self.cover_window.window.freeze_updates()
        self.apply_zoom()
        self.layout.set_size(self.image_pixbuf.get_width(), \
                             self.image_pixbuf.get_height())
        if self.image_fitted or \
           (self.image_pixbuf.get_width() == self.available_image_width() and \
           self.image_pixbuf.get_height() == self.available_image_height()):
            self.scrolledwindow.set_policy(gtk.POLICY_NEVER, gtk.POLICY_NEVER)
        else:
            self.scrolledwindow.set_policy(gtk.POLICY_AUTOMATIC,
                                           gtk.POLICY_AUTOMATIC)
        percent = int(100 * self.image_ratio)
        message = str(self.image_original_pixbuf.get_width()) + " x " + \
                      str(self.image_original_pixbuf.get_height()) + \
                      " pixels " + str(percent) + '%'
        self.zoom_in.set_sensitive(percent < self.max_percent)
        self.zoom_out.set_sensitive(percent > self.min_percent)
        self.statusbar.pop(self.statusbar.get_context_id(''))
        self.statusbar.push(self.statusbar.get_context_id(''), message)
        self.image.set_from_pixbuf(self.image_pixbuf)
        self.center_image()
        if self.cover_window.window:
            self.cover_window.window.thaw_updates()

    def apply_zoom(self):
        """Scales the image if needed"""
        new_width = int(self.image_original_pixbuf.get_width() * \
                        self.image_ratio)
        new_height = int(self.image_original_pixbuf.get_height() * \
                         self.image_ratio)
        if new_width != self.image_pixbuf.get_width() or \
           new_height != self.image_pixbuf.get_height():
            self.image_pixbuf = self.image_original_pixbuf.scale_simple(new_width, \
                                  new_height, self.image_interp)

    def set_ratio_to_fit(self):
        """Calculates and sets the needed ratio to show the full image"""
        width_ratio = float(self.image_original_pixbuf.get_width()) / \
                            self.available_image_width()
        height_ratio = float(self.image_original_pixbuf.get_height()) / \
                             self.available_image_height()
        self.image_ratio = 1 / max(1, width_ratio, height_ratio)

    def cover_window_destroy(self, widget):
        self.cover_window.destroy()

    def on_zoom_in_clicked(self, widget):
        self.image_fitted = False
        self.image_ratio *= self.ratio
        self.update_widgets()

    def on_zoom_out_clicked(self, widget):
        self.image_fitted = False
        self.image_ratio *= 1 / self.ratio
        self.update_widgets()

    def on_zoom_100_clicked(self, widget):
        self.image_fitted = False
        self.image_ratio = 1
        self.update_widgets()

    def on_zoom_fit_clicked(self, widget):
        self.image_fitted = True
        self.set_ratio_to_fit()
        self.update_widgets()

    def cover_window_size_allocate(self, widget, allocation):
        if self.cover_window_width != allocation.width or \
           self.cover_window_height != allocation.height:
            if self.image_fitted:
                self.set_ratio_to_fit()
            self.update_widgets()
            self.cover_window_width = allocation.width
            self.cover_window_height = allocation.height

class CoverChooser(gobject.GObject):
    """
        Fetches all album covers for a string, and allows the user to choose
        one out of the list
    """
    __gsignals__ = {
        'cover-chosen': (gobject.SIGNAL_RUN_LAST, None, (object,)),
    }
    def __init__(self, parent, track, search=None):
        """
            Expects the parent control, a track, an an optional search string
        """
        gobject.GObject.__init__(self)
        self.parent = parent
        self.builder = gtk.Builder()
        self.builder.add_from_file(xdg.get_data_path('ui/coverchooser.ui'))
        self.builder.connect_signals(self)
        self.window = self.builder.get_object('CoverChooser')

        tempartist = track.get_tag_display('artist')
        tempalbum = track.get_tag_display('album')
        self.window.set_title(_("Cover options for %(artist)s - %(album)s") % {
            'artist': tempartist,
            'album': tempalbum
        })
        self.window.set_transient_for(parent)

        self.track = track
        self.covers = []
        self.current = 0

        self.previous_button = self.builder.get_object('previous_button')
        self.previous_button.set_sensitive(False)
        self.next_button = self.builder.get_object('next_button')
        self.next_button.set_sensitive(False)
        self.ok_button = self.builder.get_object('ok_button')
        self.ok_button.set_sensitive(False)
        self.box = self.builder.get_object('cover_image_box')
        self.cover = guiutil.ScalableImageWidget()
        self.cover.set_image_size(350, 350)
        self.box.pack_start(self.cover, True, True)

        self.last_search = "%s - %s"  % (tempartist, tempalbum)

        self.fetch_cover(track)

    @common.threaded
    def fetch_cover(self, search):
        """
            Searches for a cover
        """
        self.covers = []
        self.current = 0

        covers = cover_manager.find_covers(self.track)
        covers = [(x, cover_manager.get_cover_data(x)) for x in covers]

        if covers:
            self.covers = covers

            if len(covers) > 0:
                self.ok_button.set_sensitive(True)
            if len(covers) > 1:
                self.next_button.set_sensitive(True)

            gobject.idle_add(self.show_cover, covers[0])
        else:
            gobject.idle_add(self.__show_no_cover_found)

    def __show_no_cover_found(self):
        # FIXME: this causes gtk to hang horribly
        #commondialogs.error(None, _('No covers found'))
        self.window.show_all()

    def on_previous_button_clicked(self, button):
        """
            Shows the previous cover
        """
        if self.current - 1 < 0:
            return

        self.current = self.current - 1
        self.show_cover(self.covers[self.current])

        if self.current + 1 < len(self.covers):
            self.next_button.set_sensitive(True)

        if self.current - 1 < 0:
            self.previous_button.set_sensitive(False)

    def on_next_button_clicked(self, button):
        """
            Shows the next cover
        """
        if self.current + 1 >= len(self.covers):
            return

        self.current = self.current + 1
        self.show_cover(self.covers[self.current])

        if self.current + 1 >= len(self.covers):
            self.next_button.set_sensitive(False)

        if self.current - 1 >= 0:
            self.previous_button.set_sensitive(True)

    def on_cancel_button_clicked(self, button):
        """
            Closes the cover chooser
        """
        self.window.destroy()

    def on_ok_button_clicked(self, button):
        """
            Chooses the current cover and saves it to the database
        """
        track = self.track
        coverdata = self.covers[self.current]

        cover_manager.set_cover(track, coverdata[0], coverdata[1])

        self.emit('cover-chosen', coverdata[1])
        self.window.destroy()

    def show_cover(self, coverdata):
        """
            Shows the current cover
        """
        self.cover.set_image_data(coverdata[1])
        self.window.show_all()

