#!/usr/bin/python

# Copyright (C) 2010 by Brian Parma
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

import gtk
import gobject

class CellRendererDays(gtk.CellRendererText):
    '''Custom Cell Renderer for showing a ListView of 7 days with checkboxes, based off pygtk FAQ example'''
    
    __gtype_name__ = 'CellRendererDays'
    __gproperties__ = { 'days':(object, 'days', 'List of enabled days', gobject.PARAM_READWRITE) }
    __gsignals__ = { 'days-changed':(gobject.SIGNAL_RUN_FIRST, gobject.TYPE_NONE,
                                    (str, object))}
    property_names = __gproperties__.keys()

    def __init__(self):
        self.__gobject_init__()
        self.model = gtk.ListStore(bool, str)
        self.view = None
        self.view_window = None
        
        for day in ['Sunday','Monday','Tuesday','Wednesday', 'Thursday', 'Friday', 'Saturday']:
            self.model.append([True, day])
            
        self.set_property('text','Edit me')


    def _create_view(self, treeview):
        '''Create the Window and View to display when editing'''
        self.view_window = gtk.Window()
        self.view_window.set_decorated(False)
        self.view_window.set_property('skip-taskbar-hint', True)

        self.view = gtk.TreeView()
        
        self.view.set_model(self.model)
        self.view.set_headers_visible(False)
        
        cr = gtk.CellRendererToggle()
        cr.connect('toggled', self._toggle)
        col = gtk.TreeViewColumn('Enabled', cr, active=0)
        self.view.append_column(col)
        
        cr = gtk.CellRendererText()
        col = gtk.TreeViewColumn('Day', cr, text=1)
        self.view.append_column(col)

        # events
        self.view.connect('focus-out-event', self._close)
        self.view.connect('key-press-event', self._key_pressed)
        
        # should be automatic
        self.view_window.set_modal(False)
        self.view_window.set_transient_for(None) # cancel the modality of dialog
        self.view_window.add(self.view)

        # necessary for getting the (width, height) of calendar_window
        self.view.show()
        self.view_window.realize()

    def do_set_property(self, pspec, value):
        '''Set property overload'''
        setattr(self, pspec.name, value)
        
    def do_get_property(self, pspec):
        '''Get property overload'''
        return getattr(self, pspec.name)

    def do_start_editing(self, event, treeview, path, background_area, cell_area, flags):
        '''Called when user starts editing the cell'''
        
        if not self.get_property('editable'):
            return

        # create window/view if it doesn't exist
        if not self.view_window:
            self._create_view(treeview)
        else:
            self.view_window.show()

        # set display to reflect 'days' property
        for i,row in enumerate(self.model):
            row[0] = self.days[i]


        # position the popup below the edited cell (and try hard to keep the popup within the toplevel window)
        (tree_x, tree_y) = treeview.get_bin_window().get_origin()
        (tree_w, tree_h) = treeview.window.get_geometry()[2:4]
        (my_w, my_h) = self.view_window.window.get_geometry()[2:4]
        x = tree_x + min(cell_area.x, tree_w - my_w + treeview.get_visible_rect().x)
        y = tree_y + min(cell_area.y, tree_h - my_h + treeview.get_visible_rect().y)
        self.view_window.move(x, y)

        # save the path so we can return it in _done, and we aren't using dialog so we can't block....
        self._path = path        
            
        return None # don't return any editable, our gtk.Dialog did the work already

    def _done(self):
        '''Called when we are done editing'''
        days = [ row[0] for row in self.model ]
        
        if days != self.days:
            self.emit('days-changed', self._path, days)
            
        self.view_window.hide()
    

    def _key_pressed(self, view, event):
        '''Key pressed event handler, finish editing on Return'''
        # event == None for day selected via doubleclick
        if not event or event.type == gtk.gdk.KEY_PRESS and gtk.gdk.keyval_name(event.keyval) == 'Return':
            self._done()
            return True

    def _toggle(self, cell, path):
        '''Checkbox toggle event handler'''
        active = self.model[path][0]
        self.model[path][0] = not active
        return True

    def _close(self, view, event):
        '''Focus-out-event handler'''
        self._done()
        return True

