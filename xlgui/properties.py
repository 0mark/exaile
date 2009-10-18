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

from xl import xdg, metadata
from xl.nls import gettext as _
import os
import gtk
import gobject
import pango, copy, datetime, string

dialog_tags = { 'originalalbum': (_('Original Album'), 'text'),
                'lyricist': (_('Lyricist'), 'text'),
                'part': (_('Part'), 'IGNORE'), #
                'website': (_('Website'), 'text'),
                'cover': (_('Cover'), 'IGNORE'), #
                'originalartist': (_('Original Artist'), 'text'),
                'author': (_('Author'), 'text'),
                'originaldate': (_('Original Date'), 'int', 1000, 2100),
                'date': (_('Date'), 'int', 0, 2100),
                'arranger': (_('Arranger'), 'text'),
                'conductor': (_('Conductor'), 'text'), 
                'performer': (_('Performer'), 'text'),
                'artist': (_('Artist'), 'text'),
                'album': (_('Album'), 'text'),
                'copyright': (_('Copyright'), 'text'),
                'lyrics': (_('Lyrics'), 'text'),
                'tracknumber': (_('Track'), 'int', 0, 500),
                'version': (_('Version'), 'text'),
                'title': (_('Title'), 'text'),
                'isrc': (_('ISRC'), 'text'),
                'genre': (_('Genre'), 'text'),
                'composer': (_('Composer'), 'text'),
                'encodedby': (_('Encoded By'), 'text'), 
                'organization': (_('Organization'), 'text'),
                'discnumber': (_('Disc'), 'int', 0, 50),
                'bpm': (_('BPM'), 'int', 0, 300),
                '__bitrate': (_('Bitrate'), 'prop:bitrate'),
                '__date_added': (_('Date Added'), 'prop:datetime'),
                '__length': (_('Length'), 'prop:time'),
                '__loc': (_('Location'), 'text'),
                '__basedir': (_('Base Directory'), 'text'),
                '__modified': (_('Modified'), 'prop:datetime'),
                '__playtime': (_('playtime'), 'IGNORE'),
                '__playcount': (_('Times Played'), 'text'),
                '__last_played': (_('Last Played'), 'prop:datetime'),
                }

class TrackPropertiesDialog(gobject.GObject):

    def __init__(self, parent, tracks):
        gobject.GObject.__init__(self)

        self.builder = gtk.Builder()
        self.builder.add_from_file(
                xdg.get_data_path('ui/trackproperties_dialog.glade'))
        self.dialog = self.builder.get_object('TrackPropertiesDialog')
	self.dialog.set_transient_for(parent)
        self._connect_events()

        self.remove_tag_button = self.builder.get_object('remove_tag_button')
        self.cur_track_label = self.builder.get_object('current_track_label')
        self.apply_button = self.builder.get_object('apply_button')
        self.prev_button = self.builder.get_object('prev_track_button')
        self.next_button = self.builder.get_object('next_track_button')
        self.prev_button.set_sensitive(False)
        if len(tracks) == 1:
            self.next_button.set_sensitive(False)

        self.tags_table = self.builder.get_object('tags_table')
        self.properties_table = self.builder.get_object('properties_table')
        self.rows = []

        self.new_tag_combo = self.builder.get_object('new_tag_combo')
        self.new_tag_combo_list = gtk.ListStore(str, str)
        for tag in dialog_tags:
            if not tag.startswith('__'):
                self.new_tag_combo_list.append((tag, dialog_tags[tag][0]))
        self.new_tag_combo_list.set_sort_column_id(1, gtk.SORT_ASCENDING)
        self.new_tag_combo.set_model(self.new_tag_combo_list)
        self.new_tag_combo.set_text_column(1)
        
        self.def_tags = [   'tracknumber', 
                            'title', 
                            'artist',
                            'album',
                            'discnumber',
                            'date', 
                            'genre', 
                            ]

        #Store the tracks and a working copy
        self.track_refs = tracks
        self.tracks = self._tags_copy(tracks)
        self.tracks_original = self._tags_copy(tracks)

        self.current = 0
        self._build_from_track(self.current)

        self.dialog.show()

    def _connect_events(self):
        self.builder.connect_signals({
            'on_apply_button_clicked': self._on_apply,
            'on_close_button_clicked': self._on_close,
            'on_prev_track_button_clicked': self._on_prev,
            'on_next_track_button_clicked': self._on_next,
            'on_title_case_button_clicked': self._title_case,
            'on_add_tag_button_clicked': self._add_tag,
            'on_remove_tag_button_toggled': self._remove_tag_mode,
        })

    def _tags_copy(self, tracks):
        l = []
        for track in tracks:
            t = {}
            for tag in self.def_tags:
                if track[tag]:
                    if isinstance(track[tag], list):
                        t[tag] = track[tag][:]
                    else:
                        t[tag] = [ track[tag] ]
                else:
                    t[tag] = ['']

                if tag == "tracknumber" or tag == "discnumber":
                    for i, entry in enumerate(t[tag]):
                        if len(entry.split('/')) < 2:
                            t[tag][i] += '/0'

            for tag in track.tags:
                if tag not in self.def_tags:
                    if isinstance(track[tag], list):
                        t[tag] = track[tag][:]
                    else:
                        t[tag] = [ track[tag] ]

            l.append(t)

        return l

    def _tags_write(self):
        for n, track in enumerate(self.tracks):
            for tag in track:
                if not tag.startswith("__"):
                    self.track_refs[n].set_tag(tag, track[tag], emit_signal=False)

            #in case a tag has been removed..
            if len(self.track_refs[n].tags) > len(track):
                poplist = []
                for tag in self.track_refs[n].tags:
                    if tag in dialog_tags:
                        if dialog_tags[tag][1] != "IGNORE":
                            try:
                                track[tag]
                            except KeyError:
                                poplist.append(tag)
                
                for tag in poplist:
                    self.track_refs[n].tags.pop(tag)

            self.track_refs[n].write_tags()

    def _build_from_track(self, track):

        for table in [self.tags_table, self.properties_table]:
            for child in table.get_children():
                table.remove(child)
            
            table.resize(1,4)

        self.rows = []

        #Previous, next and current track label
        self.prev_button.set_sensitive(True)
        self.next_button.set_sensitive(True)

        if track == 0:
            self.prev_button.set_sensitive(False)

        if track == (len(self.tracks) - 1):
            self.next_button.set_sensitive(False)

        self.cur_track_label.set_text(_("Editing track %(cur)d of %(tot)d") % {'cur': self.current+1, 'tot': len(self.track_refs)})

        t = self.tracks[track]

        for tag in self.def_tags:

            for i, entry in enumerate(t[tag]):
                if len(self.tracks) == 1:
                    ab = False
                    ab_dbl = 0
                else:
                    ab = True
                    ab_dbl = 2

                f = None
                if dialog_tags[tag][1] == 'int':
                    if tag == 'tracknumber': 
                        f = TagDblNumField(dialog_tags[tag][2], dialog_tags[tag][3], all_button=ab_dbl)
                    elif tag == 'discnumber':
                        f = TagDblNumField(dialog_tags[tag][2], dialog_tags[tag][3], all_button=ab_dbl)
                    else:
                        f = TagNumField(dialog_tags[tag][2], dialog_tags[tag][3], all_button=ab)
                else:
                    f = TagField(all_button=ab)

                self.rows.append(TagRow(self, self.tags_table, f, tag, entry, i))

        for tag in t:
            if tag not in self.def_tags: 

                try:
                    type = dialog_tags[tag][1]
                except KeyError:
                    type = 'text'
                
                if type != 'IGNORE':
                    for i, entry in enumerate(t[tag]):
                        f = None
                        if tag[:2] != '__':
                            if type == 'int':
                                f = TagNumField(dialog_tags[tag][2], 
                                        dialog_tags[tag][3], all_button=ab)
                            else:
                                f = TagField(all_button=ab)

                            self.rows.append(TagRow(self, self.tags_table, f, tag, entry, i))

                        else:
                            f = PropertyField(type)
                            
                            self.rows.append(TagRow(self, self.properties_table, f, tag, entry, i))


        self._check_for_changes()
        self._build_tables_from_rows()

    def _build_tables_from_rows(self):

        tables = [self.tags_table, self.properties_table]

        #clear the tables to start with
        for table in tables:
            for child in table.get_children():
                table.remove(child)

            table.resize(1,4)

        cur_row = {tables[0]:0, tables[1]:0}

        paddings = [0, 0, gtk.FILL|gtk.EXPAND, 0]

        for row in self.rows:
            columns = [
                    gtk.Label(),
                    row.label,
                    row.field,
                    gtk.Label()]
            for col, content in enumerate(columns):
                row.table.attach(content, col, col + 1, cur_row[row.table], 
                        cur_row[row.table] + 1, xoptions=paddings[col], yoptions=0)

            cur_row[row.table] += 1
            row.table.resize(cur_row[row.table] + 1, 4)

        for table in tables:
            table.show_all()

        self._remove_tag_mode(self.remove_tag_button)

    def _on_apply(self, w):
        if self.tracks != self.tracks_original:
            self._tags_write()

            self.tracks = None
            self.tracks_original = None
            self.tracks = self._tags_copy(self.track_refs)
            self.tracks_original = self._tags_copy(self.track_refs)
 
            self.apply_button.set_sensitive(False)
            for row in self.rows:
                if row.multi_id == 0:
                    row.label.set_markup(row.name + ':')

    def _on_close(self, w):
        if self.tracks != self.tracks_original:
            dialog = gtk.MessageDialog(self.dialog,
                      gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT, 
                      gtk.MESSAGE_WARNING,
                      gtk.BUTTONS_OK_CANCEL,
                      _("Close without applying changes to tags?"))

            response = dialog.run()
            if response == gtk.RESPONSE_OK:
                self.dialog.destroy()
            else:
                dialog.destroy()
        else:
            self.dialog.destroy()

    def _on_prev(self, widget):
        self.current -= 1
        self._build_from_track(self.current)

    def _on_next(self, widget):
        self.current += 1
        self._build_from_track(self.current)

    def _title_case(self, w):
        for row in self.rows:
            if isinstance(row.field, TagField):
                val = row.field.get_value()
                val = string.capwords(val, ' ')
                row.field.set_value(val)

        self._check_for_changes()

    def _add_tag(self, w):
        tag = None
        row = self.new_tag_combo.get_active()
        if row != -1:
            tag = self.new_tag_combo_list[row][0]
        else:
            tag = self.new_tag_combo.get_child().get_text()

        t = self.tracks[self.current]
        try:
            t[tag].append('')
        except KeyError:
            t[tag] = ['']

        self._build_from_track(self.current)

    def _remove_tag_mode(self, widget):
        for row in self.rows:
            row.set_remove_mode(widget.get_active())

    def _check_for_changes(self):
        apply_flag = False
        for i, track in enumerate(self.tracks):
            for tag in track:
                try:
                    if track[tag] != self.tracks_original[i][tag]:
                        apply_flag = True
                except KeyError:
                    apply_flag = True

            if len(track) != len(self.tracks_original[i]):
                apply_flag = True

        if apply_flag: 
            if not self.apply_button.get_property("sensitive"):
                self.apply_button.set_sensitive(True)
        else:
            self.apply_button.set_sensitive(False)

    def update_tag(self, widget, tag, multi_id, val):

        t = self.tracks[self.current]
        o = self.tracks_original[self.current]
        t[tag][multi_id] = val()

        for row in self.rows:
            if row.tag == tag and row.multi_id == 0:
                if t[tag] != o[tag]:
                    row.label.set_markup('<i>' + row.name + ':</i>')
                else:
                    row.label.set_markup(row.name + ':')

            if row.tag == tag and row.multi_id == multi_id:
                all_vals = []
                for track in self.tracks:
                    try:
                        all_vals.append(track[tag][multi_id])
                    except:
                        all_vals.append('')

                row.field.set_value(val(), all_vals, doupdate=False)

        self._check_for_changes()

    def apply_all(self, field, multi_id, val, split_num=0):
        special_cases = ["discnumber", "tracknumber"]
        apply_flag = False
        if field not in special_cases:
            for i, track in enumerate(self.tracks):
                try:
                    track[field][multi_id] = val()
                except KeyError:
                    track[field] = [val()]
                except IndexError:
                    track[field].append(val())
                o = self.tracks_original[i]

        else:
            v = val().split("/")
            for i, track in enumerate(self.tracks):
                x = track[field][multi_id].split("/")
                x[split_num] = v[split_num]
                try:
                    track[field][multi_id] = x[0] + "/" + x[1]
                except KeyError:
                    track[field] = [x[0] + "/" + x[1]]
                except IndexError:
                    track[field].append(x[0] + "/" + x[1])

        self._check_for_changes()

    def remove_row(self, w, tag, multi_id):
        for row in self.rows:
            if row.tag == tag and row.multi_id == multi_id:
                self.rows.remove(row)
                self.tracks[self.current][tag].pop(multi_id)
                if len(self.tracks[self.current][tag]) == 0:
                    self.tracks[self.current].pop(tag)

        self._build_from_track(self.current)

    def run(self):
        return self.dialog.run()

    def hide(self):
        self.dialog.hide()

class TagRow():
    def __init__(self, parent, parent_table, field, tag_name, value, multi_id):
        self.parent = parent
        self.table = parent_table
        self.tag = tag_name
        self.field = field
        self.field.register_parent_row(self)
        self.multi_id = multi_id
        all_vals = []
        for track in parent.tracks:
            try:
                all_vals.append(track[self.tag][self.multi_id])
            except:
                all_vals.append(None)

        self.field.set_value(value, all_vals)
    
        try:
            name = dialog_tags[self.tag][0]
        except:
            if self.tag[:2] != '__':
                name = self.tag
            else:
                name = self.tag[2:]

        self.name = name

        if multi_id == 0:
            self.label = gtk.Label(name + ':')
            self.label.create_pango_context()
            if parent.tracks[parent.current][self.tag] != \
                    parent.tracks_original[parent.current][self.tag]:
                self.label.set_markup('<i>' + name + '</i>:')
        else:
            self.label = gtk.Label()

        self.clear_button = gtk.Button()
        im = gtk.Image()
        im.set_from_stock(gtk.STOCK_CLEAR, gtk.ICON_SIZE_BUTTON)
        self.clear_button.set_image(im)
        self.clear_button.connect("clicked", self.clear)
        self.field.pack_start(self.clear_button, expand=False, fill=False)
        self.field.show_all()

        #Remove mode settings
        self.remove_mode = False
        self.remove_button = gtk.Button()
        im = gtk.Image()
        im.set_from_stock(gtk.STOCK_REMOVE, gtk.ICON_SIZE_BUTTON)
        self.remove_button.set_image(im)
        self.remove_button.connect("clicked", parent.remove_row, self.tag, self.multi_id)

        #self.field.register_update_func(tag_name, parent.update_tag, self.multi_id)
        self.field.register_update_func(parent.update_tag)
        self.field.register_all_func(parent.apply_all)

    def set_remove_mode(self, val):
        if self.tag not in self.parent.def_tags or self.multi_id != 0:
            if val and not self.remove_mode:
                self.field.remove(self.clear_button)
                self.field.pack_start(self.remove_button, expand=False, fill=False)
                self.field.show_all()
                self.remove_mode = True

            if not val and self.remove_mode:
                self.field.remove(self.remove_button)
                self.remove_mode = False
                self.field.pack_start(self.clear_button, expand=False, fill=False)
                self.field.show_all()

    def clear(self, w):
        self.field.set_value('')

class TagField(gtk.HBox):
    def __init__(self, all_button=True): 
        gtk.HBox.__init__(self, homogeneous=False, spacing=5)

        #Create the widgets
        self.field = gtk.Entry()
        self.all_func = None
        self.parent_row = None

        self.pack_start(self.field)

        self.all_button = None
        if all_button:
            self.all_button = AllButton(self)
            self.pack_start(self.all_button, expand=False, fill=False)

    def register_parent_row(self, parent_row):
        self.parent_row = parent_row

    def set_value(self, val, all_vals=None, doupdate=True):
        if doupdate:
            self.field.set_text(val)
        
        if all_vals != None and self.all_button != None:
            #Set the value of the all button
            flag = True
            for v in all_vals:
                if val != v:
                    flag = False

            if flag:
                self.all_button.set_active(True)
            else:
                self.all_button.set_active(False)

    def get_value(self):
        return self.field.get_text()

    def register_update_func(self, f):
        tag = self.parent_row.tag
        multi_id = self.parent_row.multi_id
        self.field.connect("changed", f, tag, multi_id, self.get_value)

    def register_all_func(self, f):
        self.all_func = f

class TagNumField(gtk.HBox):
    def __init__(self, min=0, max=10000, step=1, page=10, all_button=True): 
        gtk.HBox.__init__(self, homogeneous=False, spacing=5)

        #Create the widgets
        self.field = gtk.SpinButton()
        self.field.set_range(min, max)
        self.field.set_increments(step, page)
        self.all_func = None
        self.parent_row = None

        self.pack_start(self.field)

        self.all_button = None
        if all_button:
            self.all_button = AllButton(self)
            self.pack_start(self.all_button, expand=False, fill=False)

    def register_parent_row(self, parent_row):
        self.parent_row = parent_row

    def set_value(self, val, all_vals=None, doupdate=True):
        if doupdate:
            if val != '':
                self.field.set_value(float(val))
            else:
                self.field.set_value(0)

        if all_vals != None and self.all_button != None:
            #Set the value of the all button
            flag = True
            for v in all_vals:
                if val != v:
                    flag = False

            if flag:
                self.all_button.set_active(True)
            else:
                self.all_button.set_active(False)

    def get_value(self):
        return str(int(self.field.get_value()))

    def register_update_func(self, f):
        tag = self.parent_row.tag
        multi_id = self.parent_row.multi_id
        self.field.connect("value-changed", f, tag, multi_id, self.get_value)

    def register_all_func(self, f):
        self.all_func = f

class TagDblNumField(gtk.HBox):

    def __init__(self, min=0, max=10000, step=1, page=10, all_button=1):
        gtk.HBox.__init__(self, homogeneous=False, spacing=5)
    
        self.field = [gtk.SpinButton(), gtk.SpinButton()]
        self.all_func = None
        self.parent_row = None
        for f in self.field:
            f.set_range(min, max)
            f.set_increments(step, page)

        lbl = gtk.Label(_('of') + ':')
        self.all_button = [None, None]
        if all_button:
            if all_button == 1:
                self.all_button = [None, AllButton(self, 1)]
            if all_button == 2:
                self.all_button = [AllButton(self), AllButton(self, 1)]

        self.pack_start(self.field[0])
        if all_button and self.all_button[0] != None:
            self.pack_start(self.all_button[0], expand=False, fill=False)
        self.pack_start(lbl)
        self.pack_start(self.field[1])
        if all_button:
            self.pack_start(self.all_button[1], expand=False, fill=False)

    def register_parent_row(self, parent_row):
        self.parent_row = parent_row

    def register_all_func(self, f):
        self.all_func = f

    def set_value(self, val, all_val=None, doupdate=True):
        if len(val.split('/')) < 2:
            val += '/'

        vals = val.split('/')
        
        if doupdate:
            for x in range(2):
                if vals[x] != '':
                    self.field[x].set_value(float(vals[x]))
                else:
                    self.field[x].set_value(0)

        if all_val != None:
            all_vals = []
            for v in all_val:
                all_vals.append(v.split('/'))

            #Set the value of the all button
            flags = [True, True]
            for i in range(2):
                for v in all_vals:
                    if vals[i] != v[i]:
                        flags[i] = False

                if self.all_button[i] != None:
                    if flags[i]:
                        self.all_button[i].set_active(True)
                    else:
                        self.all_button[i].set_active(False)

    def get_value(self):
        f0 = str(int(self.field[0].get_value()))
        f1 = str(int(self.field[1].get_value()))
        return f0 + '/' + f1

    def register_update_func(self, f):
        tag = self.parent_row.tag
        multi_id = self.parent_row.multi_id
        val = str(self.field[0].get_value()) + '/' \
                + str(self.field[1].get_value())
        self.field[0].connect("value-changed", f, tag, multi_id, self.get_value)
        self.field[1].connect("value-changed", f, tag, multi_id, self.get_value)

class PropertyField(gtk.HBox):
    def __init__(self, property_type='text'):
        gtk.HBox.__init__(self, homogeneous=False, spacing=5)

        #property_type informs of special formatting required
        self.property_type = property_type
        self.field = gtk.Label()
        self.field.set_ellipsize(pango.ELLIPSIZE_MIDDLE)
        self.field.set_max_width_chars(50)
        self.field.set_selectable(True)
        self.pack_start(self.field)
        self.parent_row = None

    def register_parent_row(self, parent_row):
        self.parent_row = parent_row

    def set_value(self, val, all_vals=None, doupdate=True):
        if self.property_type == 'prop:bitrate':
            output = str( val / 1000.0 ) + ' Kbps'
        elif self.property_type == 'prop:datetime':
            d = datetime.datetime.fromtimestamp(val)
            output = d.strftime("%Y/%m/%d %H:%M:%S")
        elif self.property_type == 'prop:time':
            output = "%(m)d:%(s)02d" % {'m': val // 60, 's': val % 60}
        else:
            output = str(val)

        if doupdate:
            self.field.set_text(output)
            self.field.set_tooltip_text(output)

    def register_update_func(self, f):
        pass

    def register_all_func(self, f):
        pass

class AllButton(gtk.ToggleButton):
    def __init__(self, parent_field, id_num=0):
        gtk.ToggleButton.__init__(self)
        self.set_tooltip_text(_("Apply current value to all tracks"))
        self.connect("toggled", self.set_all_mode)
        self.field = parent_field
        self.id_num = id_num
        self.set_active(True)
        self.set_active(False)
                    
    def set_all_mode(self, w=None, do_apply=True):
        
        if self.get_active():
            if do_apply and self.field.parent_row:
                tag = self.field.parent_row.tag
                multi_id = self.field.parent_row.multi_id
                if self.field.all_func != None:
                    self.field.all_func(tag, multi_id, self.field.get_value, self.id_num)                
            im = gtk.Image()
            im.set_from_stock(gtk.STOCK_DND_MULTIPLE, gtk.ICON_SIZE_BUTTON)
            self.set_image(im)
        else:
            im = gtk.Image()
            im.set_from_stock(gtk.STOCK_DND, gtk.ICON_SIZE_BUTTON)
            self.set_image(im)

# vim: et sts=4 sw=4
