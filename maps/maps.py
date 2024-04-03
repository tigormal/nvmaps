from dataclasses import KW_ONLY, dataclass, field, asdict
from addict import Dict
from dataclass_wizard import json_field, YAMLWizard
import shapely as sh
from pathlib import Path
from typing import List, DefaultDict, Any, Optional
from PIL import Image
import os, threading
import  numpy as np
from pydispatch import dispatcher
from watchdog.observers import Observer
import watchdog.events
# from watchdog.events import FileSystemEventHandler
from lockfile import Lock
from glob import glob, iglob

import yaml

from .defs import *
from .layers import MapLayer
from .objects import MapObject

class MapFileHandler(watchdog.events.PatternMatchingEventHandler):
    def __init__(self, parent):
        self.parent = parent
        print("mpfh init")
        watchdog.events.PatternMatchingEventHandler.__init__(self,
            patterns=[
                str(self.parent._path) + "/" + DEFAULT_HEADER_NAME,
                str(self.parent._path) + "/" + OBJECT_PATTERN,
            ],
            ignore_directories=True,
            case_sensitive=False
        )


    def on_modified(self, event):
        if event:
            print(f"FILE MODIFIED {event.src_path}")
            path = Path(event.src_path)
            if path.name == DEFAULT_HEADER_NAME:
                self.parent._reloadInfo()
                return
            if path.stem[0].isdigit():
                # Thats object file
                onum = int(path.stem)
                if o := self.parent.object(onum): o.reload()

    def on_deleted(self, event):
        if event:
            print(f"FILE DELETED {event.src_path}")
            path = Path(event.src_path)
            if path.name == DEFAULT_HEADER_NAME:
                print("WARNING! Map header file was deleted")
                return
            if path.stem[0].isdigit():
                # Thats object file
                onum = int(path.stem)
                self.parent.deleteObject(self.parent.object(onum), fromdisk=False)


    def on_created(self, event):
        if event:
            print(f"FILE CREATED {event.src_path}")
            path = Path(event.src_path)
            if path.name == DEFAULT_HEADER_NAME:
                return
            if path.stem[0].isdigit():
                # Thats object file
                onum = int(path.stem)
                if o := self.parent.object(onum):
                    o.reload()
                else:
                    new = MapObject()
                    new._objectID = onum
                    self.parent.addObject(new, reload=True)



class MapLayerFileHandler(watchdog.events.PatternMatchingEventHandler):
    def __init__(self, parent):
        self.parent = parent
        print("mpfh init")
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
        if event:
            print(f"FILE MODIFIED {event.src_path}")
            path = Path(event.src_path)
            lname = path.parent.name
            lnum = int(lname.strip('L'))
            if path.name == DEFAULT_HEADER_NAME:
                if l := self.parent.layer(lnum):
                    l._reloadInfo()
                return
            if path.stem[0].isdigit():
                # Thats object file
                onum = int(path.stem)
                if l := self.parent.layer(lnum):
                    if o := l.object(onum): o.reload()
                    # l._reloadObjects()
            else:
                # that's chunk image
                chunk = path.stem
                if l := self.parent.layer(lnum): dispatcher.send(mapLayerChunkUpdatedEvent, sender=l, event={"chunk": chunk})

    def on_deleted(self, event):
        if event:
            print(f"FILE DELETED {event.src_path}")
            path = Path(event.src_path)
            lname = path.parent.name
            lnum = int(lname.strip('L'))
            if path.name == DEFAULT_HEADER_NAME:
                self.parent.deleteLayer(lnum)
                return
            if path.stem[0].isdigit():
                # Thats object file
                onum = int(path.stem)
                print(f"Delete object {onum} in layer {lnum}")
                if l := self.parent.layer(lnum): l.deleteObject(l.object(onum), fromdisk=False)
            else:
                # that's chunk image
                chunk = path.stem
                if l := self.parent.layer(lnum): l.deleteChunk(chunk, fromdisk=False)

    def on_created(self, event):
        if event:
            print(f"FILE CREATED {event.src_path}")
            path = Path(event.src_path)
            lname = path.parent.name
            lnum = int(lname.strip('L'))
            if path.name == DEFAULT_HEADER_NAME:
                print("header")
                print(f"{lnum = }")
                return
            if path.stem[0].isdigit():
                # Thats object file
                print("object")
                onum = int(path.stem)
                if l := self.parent.layer(lnum):
                    # l._reloadObjects()
                    if o:=l.object(onum):
                        o.reload()
                    else:
                        new = MapObject()
                        new._objectID = onum
                        l.addObject(new, reload=True)
            else:
                # that's chunk image
                chunk = path.stem
                if l := self.parent.layer(lnum): l.addChunk(chunk, event.src_path)


@dataclass
class Map(YAMLWizard):
    name: str = "No name"
    datum: str = ""
    sys: int = GlobalCoordinateKind.xyz.value
    # path: str = json_field("path", dump=False, default="")  # type: ignore
    # layers: DefaultDict[str, MapLayer] = field(default_factory=DefaultDict)

    def __post_init__(self):
        self._observer = None
        self._started = False
        self._path = Path() #str(Path(self.path).expanduser().resolve())
        self._hpath = Path()
        self._lastSaved = None
        self.layers: list[MapLayer] = []
        self.objects: list[MapObject] = []

        # for l in self.layers:
        #     self.layers[l]._parent = self
        # if observe: self.start()

    # TODO: implement event casting for map updates

    def start(self):
        print("obs")
        if self._started:
            return
        self._observer = Observer()
        # self._fshandler = MapFileHandler(self)
        self._layerfh = MapLayerFileHandler(self)
        self._mapfh = MapFileHandler(self)
        if self._path and self._path != Path():
            try:
                print("start")
                # self._observer.schedule(self._fshandler, path=self._path, recursive=True)
                self._observer.schedule(self._layerfh, path=self._path, recursive=True)
                self._observer.schedule(self._mapfh, path=self._path, recursive=True)
                self._observer.start()
            except Exception as e:
                print(f"WARNING: Map file is not observed. Reason: {e}")

    def stop(self):
        if self._observer:
            print("stopping obs")
            self._observer.stop()
            self._observer.join()

    def addObject(self, obj: MapObject, reload=False, silent=False):
        if obj._objectID < 0:
            existingIDs = set([x._objectID for x in self.objects])
            obj._objectID = max(existingIDs)+1 if len(existingIDs)>0 else 0
        obj.setParent(self)
        if reload: obj.reload()
        self.objects.append(obj)
        if not silent: dispatcher.send(mapObjectCreatedEvent, sender=self, event={"object": obj})

    def addLayer(self, l: MapLayer, silent=False):
        if l._layerID < 0:
            existingIDs = set([x._layerID for x in self.layers])
            l._layerID = max(existingIDs)+1 if len(existingIDs)>0 else 0
        l.setParent(self)
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

    def deleteObject(self, obj: MapObject | None, fromdisk=False):
        if obj:
            print(f"Delete object called for ID {obj._objectID} in map")
            # try:
            #     if obj.ref is not None:
            #         obj.ref.delete()
            # except:
            #     pass
            if fromdisk: obj.deleteFromDisk()
            dispatcher.send(mapObjectDeletedEvent, sender=self, event={"object": obj})
            self.objects.remove(obj)

    def save(self):
        print(f"Called save {self._path = }")
        if self._path:
            if not self._path.exists():
                os.mkdir(str(self._path))
            # with Lock(self._path):
            self.to_yaml_file(str(self._path / Path(DEFAULT_HEADER_NAME)))
            dispatcher.send(mapSavedEvent, sender=self)

    def saveAll(self):
        with Lock(self._path):
            self.save()
            for l in self.layers: l.saveAll()
            for o in self.objects: o.save()

    def layer(self, num: int) -> MapLayer | None:
        return next((x for x in self.layers if x._layerID == num), None)

    def layerNamed(self, name: str, create=False) -> MapLayer | None:
        res = next((x for x in self.layers if x.name == name), None)
        if create and res is None:
            res = MapLayer(name=name)
            self.addLayer(res)
        return res

    def _reloadObjects(self):
        def getObjectID(path: Path): return int(path.stem)

        files = iglob(str(self._path / OBJECT_PATTERN))
        oldIDs = set([o._objectID for o in self.objects])
        newIDs = set()
        for file in files:
            path = Path(file)
            id = getObjectID(path)
            newIDs.add(id)
            if id in oldIDs:
                ## Exists, ~~reload~~ do nothing
                ...
            elif not id in oldIDs:
                ## Load file and add to this map
                print(f"Creating object with ID {id}:")
                new = MapObject()
                if isinstance(new, list): new = new[0]
                new._objectID = id
                new.setParent(self)
                new.reload()
                print(new)
                self.objects.append(new)
                dispatcher.send(mapObjectCreatedEvent, sender=self, event={"object": new})
        todelete = oldIDs - newIDs
        print(f"Object IDs to delete:{todelete}")
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
                print(f"Creating layer with ID {id}:")
                new = MapLayer()
                new._layerID = id
                new.setParent(self)
                new.reload()
                print(new)
                self.layers.append(new)
        todelete = oldIDs - newIDs
        print(f"Layer IDs to delete:{todelete}")
        for x in self.layers:
            if x._layerID in todelete: self.deleteLayer(x)


    def reload(self):
        print("Called reload on map")
        if not self._path.exists(): self._path.mkdir(parents=True)
        self._reloadInfo()
        self._reloadObjects()
        self._reloadLayers()
        dispatcher.send(mapReloadedEvent, sender=self)

    def _reloadInfo(self):
        if self._hpath.exists() and self._hpath.is_file():
            with open(self._hpath, 'r') as f:
                with threading.Lock():
                    dic = yaml.safe_load(f)
                    if val:=dic.get("name"): self.name = val
                    if val:=dic.get("datum"): self.datum = val
                    if val:=dic.get("sys"): self.sys = int(val)

    def reloadAll(self):
        self.reload() # We create and delete layers and objects here
        for x in self.layers: x.reloadAll()
        for x in self.objects: x.reload()

    def _calculatePath(self):
        self._hpath = self._path / DEFAULT_HEADER_NAME

    @classmethod
    def load(cls, path: str | os.PathLike, observe=True):
        full_path = Path(path).expanduser().resolve()
        print(f"Load: {full_path}")
        # with Lock(full_path):
        #     header = str(full_path / Path(DEFAULT_HEADER_NAME))
        #     with open(header, "r") as f:
        #         h = f.read()
        #         # print(h)
        #         _map = Map.from_yaml(h)
        # if isinstance(_map, list):
        #     _map = _map[0]
        # if isinstance(_map, Map):
        #     _map._path = str(full_path)
        # for layerObject in _map.layers:
        #     layerObject.name = layerName
        #     for obj in layerObject.objects:
        #         obj.layer = layerName
        instance = cls()
        instance._path = full_path
        instance._calculatePath()
        instance.reloadAll()

        if observe:
            instance.start()
        return instance

    def __getitem__(self, item: str | int):
        if isinstance(item, str): return self.layerNamed(item)
        if isinstance(item, int): return self.layer(item)

    def __del__(self):
        self.stop()
