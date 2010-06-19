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
from urllib2 import urlparse

import gio
import glib
import gtk

from xl import (
    common,
    covers,
    event,
    formatter,
    playlist,
    settings,
    trax,
    xdg,
)
from xl.nls import gettext as _
from xlgui import icons

def _idle_callback(func, callback, *args, **kwargs):
    value = func(*args, **kwargs)
    if callback and callable(callback):
        callback(value)

def idle_add(callback=None):
    """
        A decorator that will wrap the function in a glib.idle_add call

        NOTE: Although this decorator will probably work in more cases than
        the gtkrun decorator does, you CANNOT expect to get a return value
        from the function that calls a function with this decorator.  Instead,
        you must use the callback parameter.  If the wrapped function returns
        a value, it will be passed in as a parameter to the callback function.

        @param callback: optional callback that will be called when the
            wrapped function is done running
    """
    def wrap(f):
        def wrapped(*args, **kwargs):
            glib.idle_add(_idle_callback, f, callback,
                *args, **kwargs)

        return wrapped
    return wrap

def gtkrun(f):
    """
        A decorator that will make any function run in gtk threadsafe mode

        ALL CODE MODIFYING THE UI SHOULD BE WRAPPED IN THIS
    """
    raise DeprecationWarning('We no longer need to use this '
        'function for xl/event.')
    def wrapper(*args, **kwargs):
        # if we're already in the main thread and you try to run
        # threads_enter, stuff will break horribly, so test for the main
        # thread and if we're currently in it we simply run the function
        if threading.currentThread().getName() == 'MainThread':
            return f(*args, **kwargs)
        else:
            gtk.gdk.threads_enter()
            try:
                return f(*args, **kwargs)
            finally:
                gtk.gdk.threads_leave()

    wrapper.__name__ = f.__name__
    wrapper.__dict__ = f.__dict__
    wrapper.__doc__ = f.__doc__

    return wrapper

def get_workarea_size():
    """
        Returns the height and width of the work area
    """
    rootwindow = gtk.gdk.get_default_root_window()
    workarea = gtk.gdk.atom_intern('_NET_WORKAREA')

    return rootwindow.property_get(workarea)[2][2:4] # W,H

def gtk_widget_replace(widget, replacement):
    """
        Replaces one widget with another and
        places it exactly at the original position

        :param widget: The original widget
        :type widget: :class:`gtk.Widget`
        :param replacement: The new widget
        :type widget: :class:`gtk.Widget`
    """
    parent = widget.get_parent()

    try:
        position = parent.get_children().index(widget)
    except AttributeError: # None, not gtk.Container
        return
    else:
        try:
            packing = parent.query_child_packing(widget)
        except: # Not gtk.Box
            pass

        parent.remove(widget)
        replacement.unparent()
        parent.add(replacement)

        try:
            parent.set_child_packing(replacement, *packing)
            parent.reorder_child(replacement, position)
        except AttributeError: # Not gtk.Box
            pass

        replacement.show_all()

class ScalableImageWidget(gtk.Image):
    """
        Custom resizeable image widget
    """
    def __init__(self):
        """
            Initializes the image
        """
        self.loc = ''
        gtk.Image.__init__(self)

    def set_image_size(self, width, height):
        """
            Scales the size of the image
        """
        self.size = (width, height)

    def set_image(self, image, fill=False):
        """
            Sets the image
        """
        self.loc = gio.File(image).get_path()
        self.pixbuf = gtk.gdk.pixbuf_new_from_file(self.loc)

        self._set_image(self.pixbuf, fill)

    def set_image_data(self, data, fill=False):
        if not data:
            return

        self.pixbuf = icons.MANAGER.pixbuf_from_data(data)
        self._set_image(self.pixbuf, fill)

    def _set_image(self, pixbuf, fill=False):
        width, height = self.size
        if not fill:
            origw = float(pixbuf.get_width())
            origh = float(pixbuf.get_height())
            scale = min(width / origw, height / origh)
            width = int(origw * scale)
            height = int(origh * scale)
        self.width = width
        self.height = height
        scaled = pixbuf.scale_simple(width, height, gtk.gdk.INTERP_BILINEAR)
        self.set_from_pixbuf(scaled)

        scaled = pixbuf = None

class DragTreeView(gtk.TreeView):
    """
        A TextView that does easy dragging/selecting/popup menu
    """
    targets = [("text/uri-list", 0, 0)]
    dragged_data = dict()

    def __init__(self, container, receive=True, source=True, drop_pos=None):
        """
            Initializes the tree and sets up the various callbacks
            :param container: The container to place the TreeView into
            :param receive: True if the TreeView should receive drag events
            :param source: True if the TreeView should send drag events
            :param drop_pos: Indicates where a drop operation should occur
                    w.r.t. existing entries: 'into', 'between', or None (both).
        """
        gtk.TreeView.__init__(self)
        self.container = container

        if source:
            self.drag_source_set(
                gtk.gdk.BUTTON1_MASK, self.targets,
                gtk.gdk.ACTION_COPY|gtk.gdk.ACTION_MOVE)

        if receive:
            self.drop_pos = drop_pos
            self.drag_dest_set(gtk.DEST_DEFAULT_ALL, self.targets,
                gtk.gdk.ACTION_COPY|gtk.gdk.ACTION_DEFAULT|
                gtk.gdk.ACTION_MOVE)
            self.connect('drag_data_received',
                self.container.drag_data_received)
            self.connect('drag_data_delete',
                self.container.drag_data_delete)
        self.receive = receive
        self.dragging = False
        self.show_cover_drag_icon = True
        self.connect('drag-begin', self.on_drag_begin)
        self.connect('drag-end', self.on_drag_end)
        self.connect('drag-motion', self.on_drag_motion)
        self.connect('button-release-event', self.on_button_release)
        self.connect('button-press-event', self.on_button_press)

        if source:
            self.connect('drag-data-get', self.container.drag_get_data)
            self.drag_source_set_icon_stock(gtk.STOCK_DND)

    def get_selected_tracks(self):
        """
            Returns the currently selected tracks (stub)
        """
        pass

    def on_button_release(self, button, event):
        """
            Called when a button is released
        """
        if event.button != 1 or self.dragging:
            self.dragging = False
            return True

        if event.state & (gtk.gdk.SHIFT_MASK|gtk.gdk.CONTROL_MASK):
            return True

        selection = self.get_selection()
        selection.unselect_all()

        path = self.get_path_at_pos(int(event.x), int(event.y))

        if not path:
            return False

        selection.select_path(path[0])

        try:
            return self.container.button_release(button, event)
        except AttributeError:
            pass

    def on_drag_end(self, list, context):
        """
            Called when the dnd is ended
        """
        self.dragging = False
        self.unset_rows_drag_dest()
        self.drag_dest_set(gtk.DEST_DEFAULT_ALL, self.targets,
            gtk.gdk.ACTION_COPY|gtk.gdk.ACTION_MOVE)

    def on_drag_begin(self, widget, context):
        """
            Sets the cover of dragged tracks as drag icon
        """
        self.dragging = True
        context.drag_abort(gtk.get_current_event_time())

        self._on_drag_begin(widget, context)

    @common.threaded
    def _on_drag_begin(self, widget, context):
        """
            Async call counterpart to on_drag_begin, so that cover fetching
            doesn't block dragging.
        """
        if self.show_cover_drag_icon:
            tracks = self.get_selected_tracks()
            cover_manager = covers.MANAGER
            width = height = settings.get_option('gui/cover_width', 100)

            if tracks:
                tracks = trax.util.sort_tracks(['album', 'tracknumber'], tracks)
                pixbuf = None
                first_pixbuf = None
                albums = []

                for track in tracks:
                    album = track.get_tag_raw('album', join=True)
                    if album not in albums:
                        image_data = cover_manager.get_cover(track)
                        if image_data is not None:
                            pixbuf = icons.MANAGER.pixbuf_from_data(
                                image_data, (width, height))

                            if first_pixbuf is None:
                                first_pixbuf = pixbuf
                            albums += [album]

                            if len(albums) >= 2:
                                break

                if pixbuf is not None:
                    cover_pixbuf = pixbuf

                    if len(albums) > 1:
                        # Create stacked-cover effect
                        cover_pixbuf = gtk.gdk.Pixbuf(
                            gtk.gdk.COLORSPACE_RGB,
                            True,
                            8,
                            width + 10, height + 10
                        )

                        fill_pixbuf = cover_pixbuf.subpixbuf(
                            0, 0, width + 10, height + 10)
                        fill_pixbuf.fill(0x00000000) # Fill with transparent background

                        fill_pixbuf = cover_pixbuf.subpixbuf(
                            0, 0, width, height)
                        fill_pixbuf.fill(0xccccccff)

                        if first_pixbuf != pixbuf:
                            pixbuf.copy_area(
                                0, 0, width, height,
                                cover_pixbuf,
                                5, 5
                            )
                        else:
                            fill_pixbuf = cover_pixbuf.subpixbuf(
                                5, 5, width, height)
                            fill_pixbuf.fill(0x999999ff)

                        first_pixbuf.copy_area(
                            0, 0, width, height,
                            cover_pixbuf,
                            10, 10
                        )

                    glib.idle_add(self._set_drag_cover, context, cover_pixbuf)
        else:
            if self.get_selection().count_selected_rows() > 1:
                self.drag_source_set_icon_stock(gtk.STOCK_DND_MULTIPLE)
            else:
                self.drag_source_set_icon_stock(gtk.STOCK_DND)

    def _set_drag_cover(self, context, pixbuf):
        """
            Completes drag icon setup
        """
        context.set_icon_pixbuf(pixbuf, 0, 0)

    def on_drag_motion(self, treeview, context, x, y, timestamp):
        """
            Called when a row is dragged over this treeview
        """
        if not self.receive:
            return False
        self.enable_model_drag_dest(self.targets,
            gtk.gdk.ACTION_DEFAULT)
        if self.drop_pos is None:
            return False
        info = treeview.get_dest_row_at_pos(x, y)
        if not info:
            return False
        path, pos = info
        if self.drop_pos == 'into':
            # Only allow dropping into entries.
            if pos == gtk.TREE_VIEW_DROP_BEFORE:
                pos = gtk.TREE_VIEW_DROP_INTO_OR_BEFORE
            elif pos == gtk.TREE_VIEW_DROP_AFTER:
                pos = gtk.TREE_VIEW_DROP_INTO_OR_AFTER
        elif self.drop_pos == 'between':
            # Only allow dropping between entries.
            if pos == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE:
                pos = gtk.TREE_VIEW_DROP_BEFORE
            elif pos == gtk.TREE_VIEW_DROP_INTO_OR_AFTER:
                pos = gtk.TREE_VIEW_DROP_AFTER
        treeview.set_drag_dest_row(path, pos)
        context.drag_status(context.suggested_action, timestamp)
        return True

    def on_button_press(self, button, event):
        """
            The popup menu that is displayed when you right click in the
            playlist
        """
        selection = self.get_selection()
        (x, y) = event.get_coords()
        x = int(x)
        y = int(y)
        path = self.get_path_at_pos(x, y)

        if path:
            if event.button != 3:
                if event.type == gtk.gdk._2BUTTON_PRESS:
                    self.container.button_press(button, event)

                if selection.count_selected_rows() <= 1:
                    return False
                else:
                    if selection.path_is_selected(path[0]):
                        if event.state & (gtk.gdk.SHIFT_MASK|gtk.gdk.CONTROL_MASK):
                            selection.unselect_path(path[0])
                        return True
                    elif not event.state & (gtk.gdk.SHIFT_MASK|gtk.gdk.CONTROL_MASK):
                        return True
                    return False

            if not selection.count_selected_rows():
                selection.select_path(path[0])
        return self.container.button_press(button, event)

    #TODO maybe move this somewhere else? (along with _handle_unknown_drag_data)
    def get_drag_data(self, locs, compile_tracks = True, existing_tracks = []):
        """
            Handles the locations from drag data

            @param locs: locations we are dealing with (can
                be anything from a file to a folder)
            @param compile_tracks: if true any tracks in the playlists
                that are not found as tracks are added to the list of tracks
            @param existing_tracks: a list of tracks that have already
                been loaded from files (used to skip loading the dragged
                tracks from the filesystem)

            @returns: a 2 tuple in which the first part is a list of tracks
                and the second is a list of playlist (note: any files that are
                in a playlist are not added to the list of tracks, but a track could
                be both in as a found track and part of a playlist)
        """
        #TODO handle if they pass in existing tracks
        trs = []
        playlists = []
        for loc in locs:
            (found_tracks, found_playlist) = self._handle_unknown_drag_data(loc)
            trs.extend(found_tracks)
            playlists.extend(found_playlist)

        if compile_tracks:
            #Add any tracks in the playlist to the master list of tracks
            for playlist in playlists:
                for track in playlist.get_tracks():
                    if track not in trs:
                        trs.append(track)

        return (trs, playlists)

    def _handle_unknown_drag_data(self, loc):
        """
            Handles unknown drag data that has been recieved by
            drag_data_received.  Unknown drag data is classified as
            any loc (location) that is not in the collection of tracks
            (i.e. a new song, or a new playlist)

            @param loc:
                the location of the unknown drag data

            @returns: a 2 tuple in which the first part is a list of tracks
                and the second is a list of playlist
        """
        filetype = None
        info = urlparse.urlparse(loc)

        # don't use gio to test the filetype if it's a non-local file
        # (otherwise gio will try to connect to every remote url passed in and
        # cause the gui to hang)
        if info.scheme in ('file', ''):
            try:
                filetype = gio.File(loc).query_info(
                    'standard::type').get_file_type()
            except gio.Error:
                filetype = None

        if trax.is_valid_track(loc) or info.scheme not in ('file', ''):
            new_track = trax.Track(loc)
            return ([new_track],[])
        elif playlist.is_valid_playlist(loc):
            #User is dragging a playlist into the playlist list
            # so we add all of the songs in the playlist
            # to the list
            new_playlist = playlist.import_playlist(loc)
            return ([], [new_playlist])
        elif filetype == gio.FILE_TYPE_DIRECTORY:
            return (trax.get_tracks_from_uri(loc), [])
        else: #We don't know what they dropped
            return ([], [])

class SearchEntry(object):
    """
        A gtk.Entry that emits the "activated" signal when something has
        changed after the specified timeout
    """
    def __init__(self, entry=None, timeout=500):
        """
            Initializes the entry
        """
        self.entry = entry
        self.timeout = timeout
        self.change_id = None

        if self.entry is None:
            self.entry = gtk.Entry()

        self.entry.connect('changed', self.on_entry_changed)
        self.entry.connect('icon-press', self.on_entry_icon_press)

    def on_entry_changed(self, *e):
        """
            Called when the entry changes
        """
        if self.change_id:
            glib.source_remove(self.change_id)

        self.change_id = glib.timeout_add(self.timeout,
            self.entry_activate)

    def on_entry_icon_press(self, entry, icon_pos, event):
        """
            Clears the entry
        """
        self.entry.set_text('')

    def entry_activate(self, *e):
        """
            Emit the activate signal
        """
        self.entry.activate()

    def __getattr__(self, attr):
        """
            Tries to pass attribute requests
            to the internal entry item
        """
        return getattr(self.entry, attr)

class VolumeControl(gtk.Alignment):
    """
        Encapsulates a button and a slider to
        control the volume indicating the current
        status via icon and tooltip
    """
    def __init__(self):
        gtk.Alignment.__init__(self, xalign=1)

        self.restore_volume = settings.get_option('player/volume', 1)
        self.icon_names = ['low', 'medium', 'high']

        builder = gtk.Builder()
        builder.add_from_file(xdg.get_data_path('ui', 'widgets',
            'volume_control.ui'))
        builder.connect_signals(self)

        box = builder.get_object('volume_control')
        box.reparent(self)

        self.button = builder.get_object('button')
        self.button.add_events(gtk.gdk.KEY_PRESS_MASK)
        self.button_image = builder.get_object('button_image')
        self.slider = builder.get_object('slider')
        self.slider_adjustment = builder.get_object('slider_adjustment')
        self.__update(self.restore_volume)

        event.add_callback(self.on_option_set, 'player_option_set')

    def __update(self, volume):
        """
            Sets the volume level indicator
        """
        icon_name = 'audio-volume-muted'
        tooltip = _('Muted')

        if volume > 0:
            i = int(round(volume * 2))
            icon_name = 'audio-volume-%s' % self.icon_names[i]
            #TRANSLATORS: Volume percentage
            tooltip = _('%d%%') % (volume * 100)

        if volume == 1.0:
            tooltip = _('Full Volume')

        if volume > 0:
            self.button.set_active(False)

        self.button_image.set_from_icon_name(icon_name, gtk.ICON_SIZE_BUTTON)
        self.button.set_tooltip_text(tooltip)
        self.slider.set_value(volume)
        self.slider.set_tooltip_text(tooltip)

    def on_scroll_event(self, widget, event):
        """
            Changes the volume on scrolling
        """
        page_increment = self.slider_adjustment.page_increment
        step_increment = self.slider_adjustment.step_increment
        value = self.slider.get_value()

        if event.direction == gtk.gdk.SCROLL_DOWN:
            if event.state & gtk.gdk.SHIFT_MASK:
                self.slider.set_value(value - page_increment)
            else:
                self.slider.set_value(value - step_increment)
            return True
        elif event.direction == gtk.gdk.SCROLL_UP:
            if event.state & gtk.gdk.SHIFT_MASK:
                self.slider.set_value(value + page_increment)
            else:
                self.slider.set_value(value + step_increment)
            return True

        return False

    def on_button_toggled(self, button):
        """
            Mutes or unmutes the volume
        """
        if button.get_active():
            self.restore_volume = settings.get_option('player/volume', 1)
            volume = 0
        else:
            volume = self.restore_volume

        if self.restore_volume > 0:
            settings.set_option('player/volume', volume)

    def on_slider_value_changed(self, slider):
        """
            Stores the preferred volume
        """
        settings.set_option('player/volume', slider.get_value())

    def on_slider_key_press_event(self, slider, event):
        """
            Changes the volume on key press
            while the slider is focussed
        """
        page_increment = slider.get_adjustment().page_increment
        step_increment = slider.get_adjustment().step_increment
        value = slider.get_value()

        if event.keyval == gtk.keysyms.Down:
            slider.set_value(value - step_increment)
            return True
        elif event.keyval == gtk.keysyms.Page_Down:
            slider.set_value(value - page_increment)
            return True
        elif event.keyval == gtk.keysyms.Up:
            slider.set_value(value + step_increment)
            return True
        elif event.keyval == gtk.keysyms.Page_Up:
            slider.set_value(value + page_increment)
            return True

        return False

    def on_option_set(self, event, sender, option):
        """
            Updates the volume indication
        """
        if option == 'player/volume':
            self.__update(settings.get_option(option, 1))

class Menu(gtk.Menu):
    """
        A proxy for making it easier to add icons to menu items
    """
    def __init__(self):
        """
            Initializes the menu
        """
        gtk.Menu.__init__(self)
        self._dynamic_builders = []    # list of (callback, args, kwargs)
        self._destroy_dynamic = []     # list of children added by dynamic
                                       # builders. Will be destroyed and
                                       # recreated at each map()
        self.connect('map', self._check_dynamic)

        self.show()

    def append_image(self, pixbuf, callback, data=None):
        """
            Appends a graphic as a menu item
        """
        item = gtk.MenuItem()
        image = gtk.Image()
        image.set_from_pixbuf(pixbuf)
        item.add(image)

        if callback: item.connect('activate', callback, data)
        gtk.Menu.append(self, item)
        item.show_all()
        return item

    def _insert(self, label=None, callback=None, stock_id=None, data=None, prepend=False):
        """
            Inserts a menu item (append by default)
        """
        if stock_id:
            if label:
                item = gtk.ImageMenuItem(label)
                image = gtk.image_new_from_stock(stock_id,
                    gtk.ICON_SIZE_MENU)
                item.set_image(image)
            else:
                item = gtk.ImageMenuItem(stock_id=stock_id)
        else:
            item = gtk.MenuItem(label)

        if callback: item.connect('activate', callback, data)

        if prepend:
            gtk.Menu.prepend(self, item)
        else:
            gtk.Menu.append(self, item)

        item.show_all()
        return item

    def append(self, label=None, callback=None, stock_id=None, data=None):
        """
            Appends a menu item
        """
        return self._insert(label, callback, stock_id, data)

    def prepend(self, label=None, callback=None, stock_id=None, data=None):
        """
            Prepends a menu item
        """
        return self._insert(label, callback, stock_id, data, prepend=True)

    def append_item(self, item):
        """
            Appends a menu item
        """
        gtk.Menu.append(self, item)
        item.show_all()

    def append_menu(self, label, menu, stock_id=None):
        """
            Appends a submenu
        """
        if stock_id:
            item = self.append(label, None, stock_id)
            item.set_submenu(menu)
            return item

        item = gtk.MenuItem(label)
        item.set_submenu(menu)
        item.show()
        gtk.Menu.append(self, item)

        return item

    def insert_menu(self, index, label, menu):
        """
            Inserts a menu at the specified index
        """
        item = gtk.MenuItem(label)
        item.set_submenu(menu)
        item.show()
        gtk.Menu.insert(self, item, index)

        return item

    def append_separator(self):
        """
            Adds a separator
        """
        item = gtk.SeparatorMenuItem()
        item.show()
        gtk.Menu.append(self, item)

    def add_dynamic_builder(self, callback, *args, **kwargs):
        """
            Adds a callback that will be run every time the menu is mapped,
            to add any items that change frequently. The items they add are
            destroyed and re-created with each map event.

        """
        self._dynamic_builders.append((callback, args, kwargs))

    def remove_dynamic_builder(self, callback):
        """
            Removes the given dynamic builder callback.
        """
        self._dynamic_builders = [ tuple for tuple in self._dynamic_builders
                                   if tuple[0] != callback ]

    def _check_dynamic(self, *args):
        """
           Deletes and builds again items added by the last batch of
           dynamic builder callbacks.
        """
        if self._destroy_dynamic:
            for child in self._destroy_dynamic:
                self.remove(child)
            self._destroy_dynamic = []

        if self._dynamic_builders:
            children_before = set(self.get_children())
            for callback, args, kwargs in self._dynamic_builders:
                callback(*args, **kwargs)
            self._destroy_dynamic = [ child for child in self.get_children()
                                      if child not in children_before ]

    def popup(self, *e):
        """
            Shows the menu
        """
        if len(e) == 1:
            event = e[0]
            gtk.Menu.popup(self, None, None, None, event.button, event.time)
        else:
            gtk.Menu.popup(self, *e)

class ProgressBarFormatter(formatter.ProgressTextFormatter):
    """
        A formatter for progress bars
    """
    def __init__(self):
        formatter.ProgressTextFormatter.__init__(self, self.get_option_value())

        event.add_callback(self.on_option_set, 'gui_option_set')

    def get_option_value(self):
        """
            Returns the current option value
        """
        return settings.get_option('gui/progress_bar_text_format',
            '$current_time / $remaining_time')

    def on_option_set(self, event, settings, option):
        """
            Updates the internal format on setting change
        """
        if option == 'gui/progress_bar_text_format':
            self.props.format = self.get_option_value()

def finish(repeat=True):
    """
        Waits for current pending gtk events to finish
    """
    while gtk.events_pending():
        gtk.main_iteration()
        if not repeat: break

# vim: et sts=4 sw=4
