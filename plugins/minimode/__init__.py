# Copyright (C) 2009-2010 Mathias Brodala
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

import cairo
import gtk

from xl import event, providers, settings
from xl.nls import gettext as _
from xlgui.accelerators import Accelerator
from xlgui.widgets import menu

import controls
import minimode_preferences

MINIMODE = None

def __migrate_fixed_controls():
    """
        Makes sure fixed controls are selected,
        mostly for migration from older versions
    """
    option_name = 'plugin/minimode/selected_controls'

    if settings.MANAGER.has_option(option_name):
        selected_controls = settings.get_option(option_name)

        if not 'restore' in selected_controls:
            selected_controls += ['restore']
            settings.set_option(option_name, selected_controls)

def enable(exaile):
    """
        Enables the mini mode plugin
    """
    __migrate_fixed_controls()

    if exaile.loading:
        event.add_callback(_enable, 'gui_loaded')
    else:
        _enable(None, exaile, None)

def _enable(event, exaile, nothing):
    """
        Handles the deferred enable call
    """
    controls.register()

    global MINIMODE
    MINIMODE = MiniMode(exaile)

def disable(exaile):
    """
        Disables the mini mode plugin
    """
    controls.unregister()

    global MINIMODE
    MINIMODE.destroy()
    MINIMODE = None

def teardown(exaile):
    """
        Unregisters control providers
    """
    controls.unregister()

def get_preferences_pane():
    return minimode_preferences

class MiniMode(gtk.Window):
    """
        Mini Mode main window
    """
    __gsignals__ = {'show': 'override'}

    def __init__(self, exaile):
        """
            Sets up the mini mode main window and
            options to access it
        """
        gtk.Window.__init__(self)
        self.set_title('Exaile Mini Mode')
        self.set_resizable(False)

        self.exaile_window = exaile.gui.main.window

        self.box = controls.ControlBox()
        self.box.set_spacing(3)
        alignment = gtk.Alignment(xscale=1, yscale=1)
        alignment.set_padding(0, 0, 3, 3)
        alignment.add(self.box)
        self.border_frame = gtk.Frame()
        self.border_frame.add(alignment)
        self.add(self.border_frame)

        self.menuitem = menu.simple_menu_item(
            'minimode', ['clear-playlist'],
            _('Mini Mode'), 'exaile-minimode',
            self.on_menuitem_activate, accelerator='<Control><Alt>M')
        self.accelerator = Accelerator('<Control><Alt>M',
            self.on_menuitem_activate)
        providers.register('menubar-view-menu', self.menuitem)
        providers.register('mainwindow-accelerators', self.accelerator)
        
        self.__active = False
        self.__dirty = True
        # XXX: Until defaults are implemented in xl.settings
        self.__defaults = {
            'plugin/minimode/always_on_top': True,
            'plugin/minimode/show_in_panel': False,
            'plugin/minimode/on_all_desktops': True,
            'plugin/minimode/display_window_decorations': True,
            'plugin/minimode/window_decoration_type': 'full',
            'plugin/minimode/use_alpha': False,
            'plugin/minimode/transparency': 0.3,
            'plugin/minimode/horizontal_position': 10,
            'plugin/minimode/vertical_position': 10
        }

        exaile.gui.main.connect('main-visible-toggle',
            self.on_main_visible_toggle)
        event.add_callback(self.on_option_set, 'plugin_minimode_option_set')

    def destroy(self):
        """
            Cleanups
        """
        providers.unregister('mainwindow-accelerators', self.accelerator)
        providers.unregister('menubar-view-menu', self.menuitem)

        self.set_active(False)
        self.box.destroy()
        gtk.Window.destroy(self)

    def set_active(self, active):
        """
            Enables or disables the Mini Mode window
        """
        if active == self.__active:
            return

        if active and not self.props.visible:
            self.exaile_window.hide()
            self.show_all()
        elif not active and self.props.visible:
            self.hide_all()
            self.exaile_window.show()

        self.__active = active

    def do_show(self):
        """
            Updates the appearance if
            settings have been changed
        """
        if self.__dirty:
            for option, default in self.__defaults.iteritems():
                value = settings.get_option(option, default)

                if option == 'plugin/minimode/always_on_top':
                    self.set_keep_above(value)
                elif option == 'plugin/minimode/show_in_panel':
                    self.props.skip_taskbar_hint = not value
                elif option == 'plugin/minimode/on_all_desktops':
                    if value: self.stick()
                    else: self.unstick()
                elif option == 'plugin/minimode/display_window_decorations':
                    if value:
                        option = 'plugin/minimode/window_decoration_type'
                        value  = settings.get_option(option,
                            self.__defaults[option])

                        if value == 'full':
                            self.set_decorated(True)
                            self.border_frame.set_shadow_type(gtk.SHADOW_NONE)
                        elif value == 'simple':
                            self.set_decorated(False)
                            self.border_frame.set_shadow_type(gtk.SHADOW_OUT)
                    else:
                        self.set_decorated(False)
                        self.border_frame.set_shadow_type(gtk.SHADOW_NONE)
                elif option == 'plugin/minimode/use_alpha':
                    self.unrealize()
                    self.set_app_paintable(value)
                    self.emit('screen-changed', self.get_screen())
                    self.realize()
                elif option == 'plugin/minimode/horizontal_position':
                    x, y = self.get_position()
                    self.move(value, y)
                elif option == 'plugin/minimode/vertical_position':
                    x, y = self.get_position()
                    self.move(x, value)

            self.__dirty = False

        self.resize(*self.size_request())
        self.queue_draw()
        gtk.Window.do_show(self)

    def do_expose_event(self, event):
        """
            Paints the window alpha transparency
        """
        context = self.window.cairo_create()
        context.rectangle(event.area.x, event.area.y,
            event.area.width, event.area.height)
        context.clip()

        background = self.style.bg[gtk.STATE_NORMAL]
        opacity = 1 - settings.get_option('plugin/minimode/transparency', 0.3)
        context.set_source_rgba(
            float(background.red) / 256**2,
            float(background.green) / 256**2,
            float(background.blue) / 256**2,
            opacity
        )
        context.set_operator(cairo.OPERATOR_SOURCE)
        context.paint()

        gtk.Window.do_expose_event(self, event)

    def do_screen_changed(self, screen):
        """
            Updates the colormap on screen change
        """
        colormap = screen.get_rgba_colormap() or screen.get_rgb_colormap()
        self.set_colormap(colormap)

        self.chain(screen)

    def do_configure_event(self, event):
        """
            Stores the window position upon window movement
        """
        settings.set_option('plugin/minimode/horizontal_position', event.x)
        settings.set_option('plugin/minimode/vertical_position', event.y)

    def do_delete_event(self, event):
        """
            Takes care of restoring Exaile's main window
        """
        self.set_active(False)

        return True

    def on_menuitem_activate(self, menuitem, name, parent, context):
        """
            Shows the Mini Mode window
        """
        self.set_active(True)

    def on_main_visible_toggle(self, main):
        """
            Handles visiblity toggles in
            Exaile's main window stead
        """
        if self.__active:
            if self.props.visible:
                self.hide_all()
            else:
                self.show_all()

            return True

        return False

    def on_option_set(self, event, settings, option):
        """
            Queues updates upon setting change
        """
        self.__dirty = True

# vim: et sts=4 sw=4
