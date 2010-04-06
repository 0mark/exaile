import gtk, time, gobject, thread
from gettext import gettext as _
from xl import player
from xl.plugins import PluginsManager
import acprefs
from xl import settings
ALARM=None
RANG = dict()

def enable(exaile):
    """
        Starts the timer
    """
    global ALARM
    ALARM=Alarmclock(exaile)
    ALARM.enable_alarm()

def disable(exaile):
    """
        Stops the timer for this plugin
    """
    if ALARM: ALARM.disable_alarm()

def get_preferences_pane():
    if ALARM: ALARM.enable_alarm()
    return acprefs

class VolumeControl:
    def __init__(self,exaile):
        self.exaile=exaile
        self.thread = thread

    def print_debug( self ):
        print self.min_volume
        print self.max_volume
        print self.increment
        print self.time_per_inc

    def fade_in( self ):
        temp_volume = self.min_volume
        while temp_volume <= self.max_volume:
            #print "set volume to %s" % str(temp_volume / 100.0)
            self.exaile.player.set_volume( ( temp_volume / 100.0 ) )
            temp_volume += self.increment
            time.sleep( self.time_per_inc )
            if self.exaile.player.is_paused() or not self.exaile.player.is_playing():
                self.stop_fading()


    def fade_out( self):
        temp_volume = self.max_volume
        while temp_volume >= self.min_volume:
            #print "set volume to %d" % (temp_volume / 100.0)
            self.exaile.player.set_volume( ( temp_volume / 100.0) )
            temp_volume -= self.increment
            time.sleep( self.time_per_inc )
            if self.exaile.player.is_paused() or not self.exaile.player.is_playing():
                self.stop_fading()

    def fade_in_thread( self ):
        if self.use_fading == "True":
            self.thread.start_new( self.fade_in, ())

    def stop_fading( self ):
        self.thread.exit()

    def load_settings( self ):
        prefix = "plugin/alarmclock/"
        # Setting name, property to save to, default value
        setting_values = (
            ('alarm_use_fading', 'use_fading', False),
            ('alarm_min_volume', 'min_volume', 0),
            ('alarm_max_volume', 'max_volume', 100),
            ('alarm_increment', 'increment', 1),
            ('alarm_time_per_inc', 'time_per_inc', 1),
        )
        for name, prop, default in setting_values:
            setattr(self, prop,
                    settings.get_option(prefix + name, default))


class Alarmclock(object):

    def __init__(self,exaile):
        self.timer_id=None
        self.exaile=exaile
        self.volume_control=VolumeControl(exaile)

    def timout_alarm(self):
        """
        Called every two seconds.  If the plugin is not enabled, it does
        nothing.  If the current time matches the time specified, it starts
        playing
        """
        self.hour=int(settings.get_option('plugin/alarmclock/hour', 15))
        self.minuts=int(settings.get_option('plugin/alarmclock/minuts', 20))
        self.volume_control.load_settings()
        active_days_dict = [
            settings.get_option('plugin/alarmclock/sunday', False),
            settings.get_option('plugin/alarmclock/monday', False),
            settings.get_option('plugin/alarmclock/tuesday', False),
            settings.get_option('plugin/alarmclock/thursday', False),
            settings.get_option('plugin/alarmclock/wednesday', False),
            settings.get_option('plugin/alarmclock/friday', False),
            settings.get_option('plugin/alarmclock/saturday', False)
        ]

        if not self.hour and self.minuts: return True
        if not active_days_dict: return True

        current = time.strftime("%H:%M", time.localtime())
        curhour = int(current.split(":")[0])
        curminuts = int(current.split(":")[1])
        currentDay = int(time.strftime("%w", time.localtime()))
        if curhour==self.hour and curminuts==self.minuts and active_days_dict[currentDay]==True:
            check = time.strftime("%m %d %Y %H:%M")
            if RANG.has_key(check): return True
            track = self.exaile.player.current
            if track and (self.exaile.player.is_playing() or self.exaile.player.is_paused()): return True
            self.exaile.queue.play()
            self.volume_control.fade_in_thread()

            RANG[check] = True

        return True

    def enable_alarm(self):
        if self.timer_id !=  None :
            gobject.source_remove(self.timer_id)
        self.timer_id = gobject.timeout_add_seconds(5, self.timout_alarm)

    def disable_alarm(self):
        gobject.source_remove(self.timer_id)
