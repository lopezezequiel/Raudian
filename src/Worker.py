#!/usr/bin/env python
# -*- coding: utf-8 -*-
import threading

class Worker(threading.Thread):
    def __init__(self):
        threading.Thread.__init__(self)
        self._state = threading.Condition()
        self._paused = False
        self._stopped = False

    def run(self):
        self.on_start()
        
        while True:
            with self._state:
                if self._paused:
                    self._state.wait()
            
            if(self._stopped):
                break

            self.loop()

        self.on_stop()


    def on_start(self):
        pass

    def on_stop(self):
        pass
            
    def isPaused(self):
        return self._paused
            
    def isStopped(self):
        return self._stopped

    def resume(self):
        with self._state:
            self._paused = False
            self._state.notify()  # unblock self if waiting

    def pause(self):
        with self.state:
            self._paused = True

    def stop(self):
        self._stopped = True

    def loop(self):
        raise NotImplementedError("Please Implement this method")
