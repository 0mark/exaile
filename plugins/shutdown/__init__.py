# Copyright (C) 2010 Johannes Schwarz
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 1, or (at your option)
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

import dbus
import glib
import gtk

from xl import event
from xl.nls import gettext as _
from xlgui import icons
from xlgui.widgets import dialogs

SHUTDOWN = None

class Shutdown():
    def __init__(self, exaile):
        self.exaile = exaile
        self.menu_item = gtk.CheckMenuItem(_('Shutdown after Playback'))
        self.menu_item.connect('toggled', self.on_toggled)
        self.menu_item.set_tooltip_text(_('Shutdown computer at the end of playback'))
        exaile.gui.builder.get_object('tools_menu').append(self.menu_item)
        self.menu_item.show()
        self.countdown = None
        self.counter = 10

        self.message = dialogs.MessageBar(
            parent=exaile.gui.builder.get_object('player_box'),
            buttons=gtk.BUTTONS_CLOSE)
        self.message.connect('response', self.on_response)

    def on_toggled(self, menuitem):
        """
            Enables or disables defered shutdown
        """
        if menuitem.get_active():
            event.add_callback(self.on_playback_player_end, 'playback_player_end')

            self.message.show_info(_('Shutdown scheduled'),
                _('Computer will be shutdown at the end of playback.'))
        else:
            event.remove_callback(self.on_playback_player_end, 'playback_player_end')

            # Stop possible countdown
            if self.countdown is not None:
                glib.source_remove(self.countdown)
                self.countdown = None

            # Prepare for a new run
            self.counter = 10

            # Reset message button layout
            self.message.hide()
            self.message.clear_buttons()
            self.message.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)

    def on_playback_player_end(self, event, player, track):
        """
            Tries to shutdown the computer
        """
        self.message.set_message_type(gtk.MESSAGE_INFO)
        self.message.set_markup(_('Imminent Shutdown'))
        self.message.clear_buttons()
        self.message.add_button(gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL)

        if self.countdown is not None:
            glib.source_remove(self.countdown)

        self.counter = 10
        self.countdown = glib.timeout_add_seconds(1, self.on_timeout)

    def on_response(self, widget, response):
        """
            Cancels shutdown if requested
        """
        if response == gtk.RESPONSE_CANCEL:
            self.menu_item.set_active(False)

    def on_timeout(self):
        """
            Tries to shutdown the computer
        """
        if self.counter > 0:
            self.message.set_secondary_text(
                _('The computer will be shut down in %d seconds.') % self.counter)
            self.message.show()

            self.counter -= 1;

            return True

        self.menu_item.set_active(False)

        bus = dbus.SystemBus()

        try:
            proxy = bus.get_object('org.freedesktop.ConsoleKit',
                '/org/freedesktop/ConsoleKit/Manager')
            proxy.Stop(dbus_interface='org.freedesktop.ConsoleKit.Manager')
        except dbus.exceptions.DBusException:
            try:
                proxy = bus.get_object('org.freedesktop.Hal',
                    '/org/freedesktop/Hal/devices/computer')
                proxy.Shutdown(dbus_interface='org.freedesktop.Hal.Device.SystemPowerManagement')
            except dbus.exceptions.DBusException:
                self.message.show_warning(_('Shutdown failed'),
                    _('Computer could not be shutdown using D-Bus.'))

    def destroy(self):
        """
            Cleans up
        """
        if self.countdown is not None:
            glib.source_remove(self.countdown)

        event.remove_callback(self.on_playback_player_end, 'playback_player_end')
        self.menu_item.hide()
        self.menu_item.destroy()

def enable(exaile):
    if (exaile.loading):
        event.add_callback(_enable, 'exaile_loaded')
    else:
        _enable(None, exaile, None)

def _enable(eventname, exaile, nothing):
    global SHUTDOWN
    SHUTDOWN = Shutdown(exaile)

def disable(exaile):
    global SHUTDOWN
    SHUTDOWN.destroy()

