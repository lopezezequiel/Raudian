#!/usr/bin/env python
# -*- coding: utf-8 -*-

########################################################################
# IMPORTS
########################################################################

#standard library
import os
import sys
import thread
import time

#third party
import acoustid
import wx

#local application
from Raudio import FromFile, FromSystem, chunklist_to_file


########################################################################
# CONSTANTS
########################################################################
ACOUSTID_API_KEY = 'nWyxUmvFI1'
FRAME_RATE = 44100          #CD sampling rate
THRESHOLD = (10, 10)        #if sample it is under the threshold for both channels is considered silence
CHANNELS = 2                #stereo
SAMPLE_WIDTH = 2            #bytes
MIN_SONG_LENGTH = 1         #1 second. Sounds of shorter length will be discarded
MAX_SILENCE_LENGTH = 0.2    #0.2 seconds. The max time of silence tolerated within a song


def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for PyInstaller """
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)


class RaudianFrame(wx.Frame):

    ####################################################################
    # CLASS CONSTANTS
    ####################################################################
    SYSTEM = 1
    FILE = 2


    ####################################################################
    # INIT
    ####################################################################
    def __init__(self, title):
        wx.Frame.__init__(self, None, title=title, size=(350,300))
        self.init_gui()


    def init_gui(self):
 
        main_sizer = wx.BoxSizer(wx.VERTICAL)
        
        #source type
        source_sizer = wx.BoxSizer(wx.HORIZONTAL)
        main_sizer.Add(source_sizer, 0, wx.ALL|wx.EXPAND, 5)
        
        source_label = wx.StaticText(self, label="Input Source")
        source_sizer.Add(source_label, 0, wx.ALL, 0)
        
        self.system_radio_button = wx.RadioButton(self, label='System')
        source_sizer.Add(self.system_radio_button, 0, wx.ALL, 0)
        
        self.file_radio_button = wx.RadioButton(self, label='File')
        source_sizer.Add(self.file_radio_button, 0, wx.ALL, 0)

        self.Bind(wx.EVT_RADIOBUTTON, self.on_change_source)

        #source file
        self.source_file_picker =  wx.FilePickerCtrl(self, wx.ID_ANY,
            message='Please select the wav file', wildcard='*.wav', 
            size=(500, 30))
        self.source_file_picker.Disable()
        main_sizer.Add(self.source_file_picker, 0, wx.ALL, 5)

        #separator
        line = wx.StaticLine(self, wx.ID_ANY, style=wx.LI_HORIZONTAL)
        main_sizer.Add(line, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        #output directory
        output_label = wx.StaticText(self, label="Output Directory")
        main_sizer.Add(output_label, 0, wx.ALL, 5)
        
        self.output_dir_picker =  wx.DirPickerCtrl(self, wx.ID_ANY,
            message='Please select the output directory', size=(500, 30))
        main_sizer.Add(self.output_dir_picker, 0, wx.ALL, 5)

        #separator
        line = wx.StaticLine(self, wx.ID_ANY, style=wx.LI_HORIZONTAL)
        main_sizer.Add(line, 0, wx.GROW|wx.ALIGN_CENTER_VERTICAL|wx.ALL, 5)

        #button
        self.record_bitmap = wx.Bitmap(resource_path("record32x32.png"), wx.BITMAP_TYPE_PNG)
        self.stop_bitmap = wx.Bitmap(resource_path("stop32x32.png"), wx.BITMAP_TYPE_PNG)
        self.button = wx.BitmapButton(self, bitmap = self.record_bitmap)
        self.button.Bind(wx.EVT_BUTTON, self.on_click_button)
        main_sizer.Add(self.button, 0, wx.ALL, 5)

        self.message_box = wx.StaticText(self, label='')
        main_sizer.Add(self.message_box, 0, wx.ALL|wx.EXPAND, 5)
        self.message_box.SetLabel('Hi!')


        #init frame
        icon = wx.IconFromBitmap(wx.Bitmap(resource_path("icon.ico"), wx.BITMAP_TYPE_ANY))
        self.SetIcon(icon)
        self.Bind(wx.EVT_CLOSE, self.on_close)
        self.SetMinSize(self.GetSize())
        self.SetSizer(main_sizer) 
        self.Centre() 
        self.Show()
        

    
    ####################################################################
    # EVENTS
    ####################################################################
    def on_click_button(self, event):
        self.button.Disable()

        if(self.button.GetBitmap() == self.record_bitmap):
            if(self.start()):
                self.disable_controls()
                self.set_stop_button()
        else:
            if(self.stop()):
                self.enable_controls()
                self.set_start_button()

        self.button.Enable()


    def on_change_source(self, event):
        if(self.get_source_type() == self.SYSTEM):
            self.source_file_picker.Disable()
        else:
            self.source_file_picker.Enable()


    def on_update(self, chunk, progress=None):

        #if found a music
        #Chunk under threshold and size less than 0.2s (because the song 
        #ends with silence but may have short moments of silence),
        #Check that chunks are not empty(to dismiss the initial silence)
        if(chunk.under and chunk.size > FRAME_RATE * MAX_SILENCE_LENGTH and self.chunks):

            #save song if it is greater than a second
            if(sum([c.size for c in self.chunks]) > FRAME_RATE * MIN_SONG_LENGTH):
                thread.start_new_thread(self.save, (list(self.chunks), ))

            #reset chunks
            self.chunks = []

        else:
            self.chunks.append(chunk)


    def on_close(self, event):
        self.stop()
        sys.exit(0)


    ####################################################################
    # UTILS
    ####################################################################
    def start(self):
        
        self.chunks = []

        #check that the output directory is selected
        if(not self.get_output_directory()):
            self.alert('Select the output directory', 'Error')
            return False
        
        if(self.get_source_type() == self.SYSTEM):
            return self.extract_from_system()
        else:
            return self.extract_from_file()


    def stop(self):
        try:
            self.raudio.stop()
        except:
            return False

        return True


    def extract_from_system(self):
        
        #start extraction
        try:
            self.raudio = FromSystem(channels=CHANNELS, 
                sample_width=SAMPLE_WIDTH, frame_rate=FRAME_RATE, 
                threshold=THRESHOLD, update_callback=self.on_update)
            self.raudio.start()
            self.print_message('Recording...')
        except:
            return False
            
        return True


    def extract_from_file(self):

        #check that the wav file is selected
        if(not self.get_source_file()):
            self.alert('Select wav source file', 'Error')
            return False

        #start extraction
        try:
            self.raudio = FromFile(self.get_source_file(), 
                threshold=(10, 10), update_callback=self.on_update, 
                stop_callback=self.set_start_button)
            self.raudio.start()
            self.print_message('Processing...')
        except:
            return False
            
        return True


    def save(self, chunks):

        #save song
        try:
            #get output path
            directory = self.get_output_directory()
            filename = 'unknown_{}.wav'.format(time.time())
            path = os.path.join(directory, filename)

            #save as wav file
            chunklist_to_file(path, chunks)
        except:
            wx.CallAfter(self.print_message, u'Can not save {}'.format(path))
            return

        #try to identify and rename song
        try:
            score, rid, title, artist = acoustid.match(ACOUSTID_API_KEY, path).next()
            filename = u'{0} - {1}.wav'.format(artist, title).replace('/', '')
            new_path = os.path.join(directory, filename)
            os.rename(path, new_path)
        except:
            pass
        
        wx.CallAfter(self.print_message, u'New Song: {}'.format(filename))


    def get_source_type(self):
        system = self.system_radio_button.GetValue()
        return self.SYSTEM if(system) else self.FILE


    def get_source_file(self):
        return self.source_file_picker.GetPath()


    def get_output_directory(self):
        return self.output_dir_picker.GetPath()


    def print_message(self, message):
        self.message_box.SetLabel(message)


    def alert(self, message, caption):
        alert = wx.MessageDialog(self, message, caption, wx.OK | wx.ICON_WARNING)
        alert.ShowModal()
        alert.Destroy()

    def set_stop_button(self):
        self.button.SetBitmap(self.stop_bitmap)

    def set_start_button(self):
        self.button.SetBitmap(self.record_bitmap)

    def disable_controls(self):
        self.system_radio_button.Disable()
        self.file_radio_button.Disable()
        self.source_file_picker.Disable()
        self.output_dir_picker.Disable()

    def enable_controls(self):
        self.system_radio_button.Enable()
        self.file_radio_button.Enable()
        if(self.get_source_type() == self.FILE):
            self.source_file_picker.Enable()
        self.output_dir_picker.Enable()


app = wx.App(redirect=True)
RaudianFrame(title="Raudian")
app.MainLoop()
