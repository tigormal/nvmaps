from dataclasses import KW_ONLY, dataclass, field, asdict
from addict import Dict
from dataclass_wizard import json_field, YAMLWizard
import shapely as sh
from pathlib import Path
from typing import List, DefaultDict, Any, Optional
from PIL import Image
import os, threading, logging
import  numpy as np
from pydispatch import dispatcher
from watchdog.observers import Observer
import watchdog.events
from glob import glob, iglob
from queue import Queue
from datetime import datetime as dt

import yaml

from .defs import *
from .layers import MapLayer
from .objects import MapObject

class DelayedHandler():

    def __init__(self, parent) -> None:
        self.interval = 0.1 # [s]
        self.parent = parent
        self.queue = Queue()
        self.th = threading.Thread(target=self.main)
        self._stop = False
        self._lastCheck = dt.now()
        self._log = logging.getLogger("Maps.DelayedHandler")

    def main(self):
        while True:
            if self._stop: break
            func, args = self.queue.get()
            try:
                func(*args)
                self._log.debug(f"Task done: {func.__name__}")
            except Exception as e:
                self._log.error(f"Task failed: {func.__name__}. Reason: {e}")
            self.queue.task_done()
            if self._stop: break

    def put(self, *args):
        self.queue.put(*args)

    def checkSaveReload(self):
        while True:
            if self._stop: break
            if (dt.now() - self._lastCheck).total_seconds() >= self.interval:
                self._lastCheck = dt.now()
                self.parent.saveAll()

    def stop(self):
        self._stop = True
        self.queue.join()
        self.queue.put((print, [""]))

    def start(self):
        self.th.start()



class MapFileHandler(watchdog.events.PatternMatchingEventHandler):
    def __init__(self, parent, handler: DelayedHandler):
        self.parent = parent
        self.h = handler
        self._log = logging.getLogger("Maps.MapFileHandler")
        watchdog.events.PatternMatchingEventHandler.__init__(self,
            patterns=[
                str(self.parent._path) + "/" + DEFAULT_HEADER_NAME,
                str(self.parent._path) + "/" + OBJECT_PATTERN,
            ],
            ignore_directories=True,
            case_sensitive=False
        )

    def on_modified(self, event):
        self.h.queue.put((self.on_modified_handler, [event.src_path]))
    def on_deleted(self, event):
        self.h.queue.put((self.on_deleted_handler, [event.src_path]))
    def on_created(self, event):
        self.h.queue.put((self.on_created_handler, [event.src_path]))

    def on_modified_handler(self, src_path):
        if src_path:
            self._log.debug(f"FILE MODIFIED {src_path}")
            path = Path(src_path)
            if path.name == DEFAULT_HEADER_NAME:
                with threading.Lock():
                    self.parent._reloadInfo(force=True)
                self._log.debug(f"UPDATED MAP INFO")
                return
            if path.stem[0].isdigit():
                # Thats object file
                onum = int(path.stem)
                if o := self.parent.object(onum):
                    # with threading.Lock():
                    # o.lazyReload()
                    o.reload(force=True)
                    self._log.debug(f"UPDATED OBJECT {onum} in map")

    def on_deleted_handler(self, src_path):
        if src_path:
            self._log.debug(f"FILE DELETED {src_path}")
            path = Path(src_path)
            if path.name == DEFAULT_HEADER_NAME:
                self._log.warn("Map header file was deleted")
                return
            if path.stem[0].isdigit():
                # Thats object file
                onum = int(path.stem)
                self.parent.deleteObject(self.parent.object(onum), fromdisk=False)
                self._log.debug(f"DELETED OBJECT {onum} in map")


    def on_created_handler(self, src_path):
        if src_path:
            self._log.debug(f"FILE CREATED {src_path}")
            path = Path(src_path)
            if path.name == DEFAULT_HEADER_NAME:
                return
            if path.stem[0].isdigit():
                # Thats object file
                onum = int(path.stem)
                if o := self.parent.object(onum):
                    o.reload(force=True)
                else:
                    new = MapObject()
                    new._objectID = onum
                    self.parent.addObject(new, reload=True)
                self._log.debug(f"CREATED OBJECT {onum} in map")



class MapLayerFileHandler(watchdog.events.PatternMatchingEventHandler):
    def __init__(self, parent, handler: DelayedHandler):
        self.parent = parent
        self.h = handler
        self._log = logging.getLogger("Maps.MapLayerFileHandler")
        watchdog.events.PatternMatchingEventHandler.__init__(self,
            patterns=[
                "*/L[0-9]*/" + DEFAULT_HEADER_NAME,
                "*/L[0-9]*/" + OBJECT_PATTERN,
                "*/L[0-9]*/" + CHUNK_PATTERN,
            ],
            ignore_directories=True,
            case_sensitive=False
        )

    def on_modified(self, event):
        self.h.queue.put((self.on_modified_handler, [event]))
    def on_deleted(self, event):
        self.h.queue.put((self.on_deleted_handler, [event]))
    def on_created(self, event):
        self.h.queue.put((self.on_created_handler, [event]))

    def on_modified_handler(self, event):
        if event:
            self._log.debug(f"FILE MODIFIED {event.src_path}")
            path = Path(event.src_path)
            lname = path.parent.name
            lnum = int(lname.strip('L'))
            if path.name == DEFAULT_HEADER_NAME:
                if l := self.parent.layer(lnum):
                    l._reloadInfo(force=True)
                    self._log.debug(f"UPDATED LAYER {lnum} INFO")
                return
            if path.stem[0].isdigit():
                # Thats object file
                onum = int(path.stem)
                if l := self.parent.layer(lnum):
                    if o := l.object(onum):
                        o.reload(force=True)
                        self._log.debug(f"UPDATED OBJECT {onum} in layer {lnum}")
            else:
                # that's chunk image
                chunk = path.stem
                if l := self.parent.layer(lnum):
                    dispatcher.send(mapLayerChunkUpdatedEvent, sender=l, event={"chunk": chunk})
                    self._log.debug(f"UPDATED CHUNK {chunk} in layer {lnum}")

    def on_deleted_handler(self, event):
        if event:
            self._log.debug(f"FILE DELETED {event.src_path}")
            path = Path(event.src_path)
            lname = path.parent.name
            lnum = int(lname.strip('L'))
            if path.name == DEFAULT_HEADER_NAME:
                self.parent.deleteLayer(lnum)
                return
            if path.stem[0].isdigit():
                # Thats object file
                onum = int(path.stem)
                self._log.debug(f"Delete object {onum} in layer {lnum}")
                if l := self.parent.layer(lnum): l.deleteObject(l.object(onum), fromdisk=False)
            else:
                # that's chunk image
                chunk = path.stem
                if l := self.parent.layer(lnum): l.deleteChunk(chunk, fromdisk=False)

    def on_created_handler(self, event):
        if event:
            self._log.debug(f"FILE CREATED {event.src_path}")
            path = Path(event.src_path)
            lname = path.parent.name
            lnum = int(lname.strip('L'))
            if path.name == DEFAULT_HEADER_NAME:
                self._log.debug("header")
                if l:=self.parent.layer(lnum):
                    # with threading.Lock():
                    l._reloadInfo(force=True)
                else:
                    new = MapLayer()
                    new._layerID = lnum
                    new.reload(force=True)
                    self.parent.addLayer(new)
                    self._log.debug(f"CREATED LAYER {lnum} in map")
                return
            if path.stem[0].isdigit():
                # Thats object file
                self._log.debug("object")
                onum = int(path.stem)
                if l := self.parent.layer(lnum):
                    if o:=l.object(onum):
                        o.reload(force=True)
                    else:
                        new = MapObject()
                        new._objectID = onum
                        l.addObject(new, reload=True)
                        self._log.debug(f"CREATED OBJECT {onum} in layer {lnum}")
            else:
                # that's chunk image
                chunk = path.stem
                if l := self.parent.layer(lnum):
                    l.addChunk(chunk, event.src_path)
                    self._log.debug(f"CREATED CHUNK {chunk} in layer {lnum}")


@dataclass
class Map(YAMLWizard):
    name: str = "No name"
    datum: str = ""
    sys: int = GlobalCoordinateKind.xyz.value

    def __post_init__(self):
        self._observer = None
        self._started = False
        self._path = Path()
        self._hpath = Path()
        self._lastSaved = None
        self._needsSave = False
        self._needsReload = True
        self._h = DelayedHandler(self)
        self.layers: list[MapLayer] = []
        self.objects: list[MapObject] = []
        self._log = logging.getLogger("Maps.Map")

        dispatcher.connect(self.on_file_updated, sender=dispatcher.Any, signal=mapFileUpdatedEvent)

    # TODO: implement event casting for map updates

    def start(self):
        self._log.debug("obs")
        if self._started:
            return
        self._observer = Observer()
        self._layerfh = MapLayerFileHandler(self, self._h)
        self._mapfh = MapFileHandler(self, self._h)
        if self._path and self._path != Path():
            try:
                self._log.debug("start")
                self._observer.schedule(self._layerfh, path=self._path, recursive=True)
                self._observer.schedule(self._mapfh, path=self._path, recursive=True)
                self._h.start()
                self._observer.start()
                self._started = True
            except Exception as e:
                self._log.warn(f"Map file is not observed. Reason: {e}")

    def stop(self):
        if self._observer:
            self._log.debug("stopping obs")
            self._observer.stop()
            self._h.stop()
            self._observer.join()

    def addObject(self, obj: MapObject, *, reload=False, silent=False):
        if obj._objectID < 0:
            existingIDs = set([x._objectID for x in self.objects])
            obj._objectID = max(existingIDs)+1 if len(existingIDs)>0 else 0
        obj.setParent(self)
        if reload: obj.reload(force=True)
        self.objects.append(obj)
        if not silent: dispatcher.send(mapObjectCreatedEvent, sender=self, event={"object": obj})

    def addLayer(self, l: MapLayer, *, reload=False, silent=False):
        if l._layerID < 0:
            existingIDs = set([x._layerID for x in self.layers])
            l._layerID = max(existingIDs)+1 if len(existingIDs)>0 else 0
        l.setParent(self)
        if reload: l.reload()
        self.layers.append(l)
        if not silent: dispatcher.send(mapLayerCreatedEvent, sender=self, event={"layer": l})

    def moveObjectToLayerNamed(self, obj: MapObject, layername: str):
        l = self.layerNamed(layername)
        if l: self.moveObjectToLayer(obj, l)

    def moveObjectToLayer(self, obj: MapObject, layer: MapLayer):
        l1: MapLayer | None = obj._parent; l2 = layer
        oldpath = str(obj._path)[:]
        obj.setParent(l2) # update obj path
        newpath = str(obj._path)
        if oldpath != Path(): os.rename(oldpath, newpath) # move file
        if l1: l1.objects.remove() # move from one list
        l2.objects.append(obj) # to another
        obj.save() # write obj file to a new location

    def deleteLayer(self, layer: MapLayer):
        try:
            layer.deleteFromDisk()
            self.layers.remove(layer)
            dispatcher.send(mapLayerDeletedEvent, sender=self, event={"name": layer})
        except:
            pass

    def object(self, num: int) -> MapObject | None:
        return next((x for x in self.objects if x._objectID == num), None)

    def objectNamed(self, name: str, create=False) -> MapObject | None:
        res = next((x for x in self.objects if x.name == name), None)
        if create and res is None:
            res = MapObject(name=name)
            self.addObject(res)
        return res

    def deleteObject(self, obj: MapObject | None, *, fromdisk=False):
        if obj:
            self._log.debug(f"Delete object called for ID {obj._objectID} in map")
            if fromdisk: obj.deleteFromDisk()
            dispatcher.send(mapObjectDeletedEvent, sender=self, event={"object": obj})
            self.objects.remove(obj)

    def lazyReload(self):
        self._needsReload = True

    def lazySave(self):
        self._needsSave = True

    def save(self, force=False):

        def procSave():
            if not self._path.exists():
                os.mkdir(str(self._path))
            self.to_yaml_file(str(self._path / Path(DEFAULT_HEADER_NAME)))
            dispatcher.send(mapSavedEvent, sender=self)

        self._log.debug(f"Called save {self._path = }")
        if (self._needsSave or force) and self._path:
            self._h.put((procSave, []))

    def saveAll(self, force=False):
        self.save(force)
        for l in self.layers: l.saveAll(force)
        for o in self.objects: o.save(force)

    def layer(self, num: int) -> MapLayer | None:
        return next((x for x in self.layers if x._layerID == num), None)

    def layerNamed(self, name: str, *, create=False) -> MapLayer | None:
        res = next((x for x in self.layers if x.name == name), None)
        if create and res is None:
            res = MapLayer(name=name)
            self.addLayer(res)
        return res

    def _reloadObjects(self, force=False):
        def getObjectID(path: Path): return int(path.stem)

        files = iglob(str(self._path / OBJECT_PATTERN))
        oldIDs = set([o._objectID for o in self.objects])
        newIDs = set()
        self._log.debug(f"Map Existing objects: {oldIDs}")
        for file in files:
            self._log.debug(f"Map Reloading object file: {file}")
            path = Path(file)
            id = getObjectID(path)
            newIDs.add(id)
            if not (id in oldIDs):
                ## Load file and add to this map
                self._log.debug(f"Creating object with ID {id}:")
                new = MapObject()
                if isinstance(new, list): new = new[0]
                new._objectID = id
                new.setParent(self)
                new.reload(force)
                self.objects.append(new)
                dispatcher.send(mapObjectCreatedEvent, sender=self, event={"object": new})
        todelete = oldIDs - newIDs
        self._log.debug(f"Object IDs to delete:{todelete}")
        for x in self.objects:
            if x._objectID in todelete:
                self.deleteObject(x)

    def _reloadLayers(self):
        def getLayerID(path: Path): return int(path.stem.strip('L'))

        files = iglob(str(self._path / LAYER_PATTERN))
        oldIDs = set([o._layerID for o in self.layers])
        newIDs = set()
        for file in files:
            path = Path(file)
            id = getLayerID(path)
            newIDs.add(id)
            if id in oldIDs:
                ## Exists, ~~reload~~ do nothing
                ...
            elif not id in oldIDs:
                ## Load file and add to this map
                self._log.debug(f"Creating layer with ID {id}:")
                new = MapLayer()
                new._layerID = id
                new.setParent(self)
                new.reload()
                self._log.debug(new)
                self.layers.append(new)
        todelete = oldIDs - newIDs
        self._log.debug(f"Layer IDs to delete:{todelete}")
        for x in self.layers:
            if x._layerID in todelete: self.deleteLayer(x)


    def reload(self, force=False):
        self._log.debug("Called reload on map")
        flag = self._needsReload or force
        if not self._path.exists():
            self._path.mkdir(parents=True)

        def procReload():
            if not self._hpath.exists():
                self.save(force=True)
            else:
                self._reloadInfo()
            self._reloadObjects()
            self._reloadLayers()
            dispatcher.send(mapReloadedEvent, sender=self)
            self._needsReload = False

        if force:
            procReload()
            return
        if self._needsReload:
            self._h.put((procReload, []))
            return


    def _reloadInfo(self, force=False):
        if self._hpath.exists() and self._hpath.is_file():
            with open(self._hpath, 'r') as f:
                with threading.Lock():
                    dic = yaml.safe_load(f)
                if dic is None:
                    self._log.error(f"Failed to read file, or file is empty")
                    return
                self._log.debug(f"Reloading map info, read dict from file: {dic}")
                if val:=dic.get("name"): self.name = val
                if val:=dic.get("datum"): self.datum = val
                if val:=dic.get("sys"): self.sys = int(val)

    def reloadAll(self, force=False):
        self._log.debug("Map: Called reloadAll")
        self.reload(force) # We create and delete layers and objects here
        for x in self.layers: x.reloadAll(force)
        for x in self.objects: x.reload(force)

    def _calculatePath(self):
        self._hpath = self._path / DEFAULT_HEADER_NAME

    @classmethod
    def load(cls, path: str | os.PathLike, *, observe=True):
        full_path = Path(path).expanduser().resolve()
        logger = logging.getLogger("Maps")
        logger.info(f"Loading map at path: {str(full_path)}")
        instance = cls()
        instance._path = full_path
        instance._calculatePath()
        instance.reloadAll(force=True)

        if observe:
            instance.start()
        return instance

    def __getitem__(self, item: str | int):
        if isinstance(item, str): return self.layerNamed(item)
        if isinstance(item, int): return self.layer(item)

    def __del__(self):
        self.stop()


    ### FILE CHANGE HANDLERS

    def _defineLayerFromPath(self, path: Path) -> int | None:
        if path.is_relative_to(self._path):
            if path.parent.name == self._path.name:
                return -1
            if path.parent.name.startswith('L'):
                return int(path.parent.name.strip('L'))

    def _defineObjectFromPath(self, path: Path) -> int | str | None:
        if path.name == DEFAULT_HEADER_NAME:
            return "info"
        elif path.suffix == DEFAULT_EXT:
            return int(path.stem)
        elif path.stem[0] in ["N", "S"]:
            return path.stem

    def on_file_updated(self, event={}):
        path = event.get("file")
        if path: self.procUpdateForPath(Path(path).expanduser().resolve())

    def procUpdateForPath(self, path: Path):

        lnum = self._defineLayerFromPath(path)
        if lnum is None:
            self._log.debug(f"Invalid layer given in path for update")
            return
        if lnum >= 0:
            layer_str = f"layer ID {lnum}"
            layer = self.layer(lnum)
        else:
            layer_str = "global map layer"
            layer = self

        o = self._defineObjectFromPath(path)
        if o is None:
            print("Invalid object or image in path for update")
            return
        if isinstance(o, str):
            if o == "info":
                what_str = f"info"
                if layer: layer._reloadInfo()
            else:
                what_str = f"chunk image {o}"
                if isinstance(layer, MapLayer): layer._reloadImages()

        else:
            what_str = f"object ID {o}"
            if layer:
                if object := layer.object(o): object.reload()

        self._log.info(f"Called file update for {what_str} in {layer_str}")
