#!/usr/bin/env python
# -*- coding: utf-8 -*-
import wave
import struct
import tempfile

from collections import namedtuple
from Worker import Worker

try:
    import pyaudio
except:
    pass


########################################################################
# Exceptions
########################################################################
class BaseException(Exception):
    pass


class SampleWidthException(BaseException):
    pass


########################################################################
# Utilities
########################################################################
def chunklist_to_file(output_path, chunklist, cache_size=1024):
    """Exports all chunks to a wav file
    """

    #output wav
    output = wave.open(output_path, 'w')
    first = True

    for c in chunklist:

        #get audio params from first chunk
        if(first):                
            output.setnchannels(c.channels)
            output.setsampwidth(c.sample_width)
            output.setframerate(c.frame_rate)
            first = False

        #wav corresponding to the current chunk
        audio = wave.open(c.path, 'r')

        #last frame
        end = c.offset + c.size

        #Reads the frames from the file corresponding to the current 
        #chunk and write them in the output file
        for o in range(c.offset, end, cache_size):
            cs = cache_size if o + cache_size <= end else end - o
            audio.setpos(o)
            output.writeframes(audio.readframes(cs))

        audio.close()

    output.close()


########################################################################
# Classes
########################################################################
Chunk = namedtuple('Chunk', 'offset size under over path channels sample_width frame_rate')

class AudioWorker(Worker):
    
    def __init__(self):
        Worker.__init__(self)

    def _make_unpack(self, sample_width, channels):
        """Build and returns the unpack function according to the sample 
        width and number of channels. The function takes a frame and
        returns a tuple of integers with as many elements as channels have
        """

        if(sample_width == 1):
            fmt = '<{}b'.format(channels)
            return lambda frame: struct.unpack(fmt, frame)
        elif(sample_width == 2):
            fmt = '<{}h'.format(channels)
            return lambda frame: struct.unpack(fmt, frame)
        elif(sample_width == 3):
            """The struct module has no option to read 3-byte integers, so 
            it is read as 4-byte integers, but it is necessary to add the 
            fourth byte
            """
            fmt = '<{}l'.format(channels)
            return lambda frame: struct.unpack(fmt, ''.join(
                [frame[i:i+3] + b'\x00' for i in range(0, len(frame), 3)]))
        elif(sample_width == 4):
            fmt = '<{}l'.format(channels)
            return lambda frame: struct.unpack(fmt, frame)
        else:
            raise SampleWidthException('Invalid sample width')


    def _make_compare(self, sample_width, channels, threshold):
        """This function returns a function that reads a frame and 
        return True, False or None according to the following rules:
            - None: if frame is empty(if it's the last frame)
            - True: if the frame is less than or equal to the threshold
            - False: if the frame is greater than a threshold    
        """

        #build unpack function
        unpack = self._make_unpack(sample_width, channels)

        def compare(frame):

            #If it's the last frame
            if(frame == ''):
                return None
            else:
                #The samples from each channel must be less than the corresponding threshold
                return all([(abs(f) <= t) for f, t in zip(unpack(frame), threshold)])
        
        return compare    


class FromFile(AudioWorker):

    def __init__(self, input_path, threshold=None, update_callback=None, stop_callback=None):
        AudioWorker.__init__(self)

        self.input_path = input_path
        self.threshold = threshold
        self.update_callback = update_callback
        self.stop_callback = stop_callback
        self.ProgressInfo = namedtuple('ProgressInfo', 'currentFrame totalFrames currentTime totalTime percent')

    def on_start(self):

        self.audio = wave.open(self.input_path, 'r')

        #default threshold is absolute silence
        if(not self.threshold):
            self.threshold = (0,) * self.audio.getnchannels()

        #build compare function
        self.compare = self._make_compare(
            self.audio.getsampwidth(), 
            self.audio.getnchannels(), 
            self.threshold
        )


    def loop(self):

        offset = self.audio.tell()

        #it's inclusive. means frame <= threshold
        under = self.compare(self.audio.readframes(1)) == True

        """all frames in a chunk must be less than or equal the threshold.
        or all frames in a chunk must be greater than the threshold.
        also it's necessary to check if the thread stopped to stop the 
        reading immediately.
        """
        while(self.compare(self.audio.readframes(1)) == under and not self.isStopped()):
            pass

        #because current frame does not belong to the current chunk but next
        self.audio.setpos(self.audio.tell() - 1)

        chunk = Chunk(offset, self.audio.tell() - offset, 
            under, not under, self.input_path, self.audio.getnchannels(),
            self.audio.getsampwidth(), self.audio.getframerate())


        #call progress function if exists
        if(callable(self.update_callback)):

            self.update_callback(chunk, self.ProgressInfo(
                self.audio.tell(),
                self.audio.getnframes(),
                self.audio.tell() * self.audio.getframerate(),
                self.audio.getnframes() * self.audio.getframerate(),
                #the +1 is for the last frame(the empty frame)
                (self.audio.tell() + 1) * 100 / self.audio.getnframes()
            ))

        #means if end of wav because last frame is empty
        if(self.audio.tell() == self.audio.getnframes() - 1):
            self.stop()

    def on_stop(self):

        self.audio.close()
        
        #call the callback if exists
        if(callable(self.stop_callback)):
            self.stop_callback()

class FromSystem(AudioWorker):

    def __init__(self, channels=1, sample_width=2, frame_rate=44100, 
        threshold=None, update_callback=None, stop_callback=None):

        if(not pyaudio):
            raise ImportError("You need to install pyaudio")

        AudioWorker.__init__(self)

        self.channels = channels
        self.sample_width = sample_width
        self.frame_rate = frame_rate
        self.threshold = threshold
        self.update_callback = update_callback
        self.stop_callback = stop_callback


    def loop(self): 
        
        #create new temp wav file
        f = tempfile.NamedTemporaryFile(delete=False)
        f.close()
        output_path = f.name
        audio = wave.open(output_path, 'wb')
        audio.setnchannels(self.channels)
        audio.setframerate(self.frame_rate)
        audio.setsampwidth(self.sample_width)

        #offset is always 0 because in each loop a new file is created
        offset = 0

        #first read and write
        frame = self.stream.read(1)
        audio.writeframes(frame)

        #it's inclusive. means frame <= threshold
        under = self.compare(frame) == True

        """all frames in a chunk must be less than or equal the threshold.
        or all frames in a chunk must be greater than the threshold.
        also it's necessary to check if the thread stopped to stop the 
        reading immediately.
        """
        while(self.compare(frame) == under and not self.isStopped()):
            frame = self.stream.read(1)
            audio.writeframes(frame)

        chunk = Chunk(0, audio.getnframes(), under, not under, 
            output_path, self.channels, self.sample_width, self.frame_rate)

        audio.close()

        #execute callback if it exists
        if(callable(self.update_callback)):
            self.update_callback(chunk)
    
    def on_stop(self):
        #close all
        self.stream.close()
        self.pyaudio.terminate()
        
        #call the callback if it exists
        if(callable(self.stop_callback)):
            self.stop_callback()

    def on_start(self):
        
        #open stream
        self.pyaudio = pyaudio.PyAudio()
        self.stream = self.pyaudio.open(
            format = self._get_format(),
            channels = self.channels,
            rate = self.frame_rate,
            input = True,
            frames_per_buffer = 1024
        )

        #default threshold is absolute silence
        if(not self.threshold):
            self.threshold = (0,) * self.channels

        #build compare function
        self.compare = self._make_compare(
            self.sample_width, 
            self.channels, 
            self.threshold
        )


    def _get_format(self):
        """converts sample_width from the wave format to pyaudio format
        """

        if(self.sample_width == 1):
            return pyaudio.paInt8
        elif(self.sample_width == 2):
            return pyaudio.paInt16
        elif(self.sample_width == 3):
            return pyaudio.paInt24
        elif(self.sample_width == 4):
            return pyaudio.paInt32
            
        raise SampleWidthException('Invalid sample width')
