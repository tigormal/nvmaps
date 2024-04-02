from dataclasses import KW_ONLY, dataclass, field, asdict
from addict import Dict
from dataclass_wizard import json_field, YAMLWizard
import shapely as sh
from pathlib import Path
from typing import List, DefaultDict, Any, Optional
from PIL import Image
import os
import  numpy as np
from pydispatch import dispatcher
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from lockfile import Lock
from glob import glob, iglob

from .defs import *
from .layers import MapLayer
from .objects import MapObject


class MapFileHandler(FileSystemEventHandler):
    def __init__(self, parent):
        self.parent = parent

    def on_modified(self, event):
        if event:
            match event.event_type:
                case 'modified':
                    # Invoke reload
                    ...
                case 'created':
                    # Invoke layer or object creation
                    ...
                case 'deleted':
                    # Invoke layer or object deletion
                    ...
                case 'moved':
                    # Invoke move of mapobject to layer
                    ...
                case _: pass
            # print(event.src_path)
            # self.parent.reload()


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
        self._fshandler = MapFileHandler(self)
        if self._path and self._path != Path():
            try:
                print("start")
                self._observer.schedule(self._fshandler, path=self._path, recursive=True)
                self._observer.start()
            except Exception as e:
                print(f"WARNING: Map file is not observed. Reason: {e}")

    def stop(self):
        if self._observer:
            print("stopping obs")
            self._observer.stop()
            self._observer.join()

    def addObject(self, obj: MapObject):
        obj.setParent(self)
        self.objects.append(obj)
        dispatcher.send(mapObjectCreatedEvent, sender=self, event={"object": obj})

    def addLayer(self, l: MapLayer):
        l.setParent(self)
        self.layers.append(l)
        dispatcher.send(mapLayerCreatedEvent, sender=self, event={"layer": l})

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

    def deleteObject(self, obj: MapObject | None):
        if obj:
            try:
                if obj.ref is not None:
                    obj.ref.delete()
            except:
                pass
            obj.deleteFromDisk()
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
        self._reloadObjects()
        self._reloadLayers()
        dispatcher.send(mapReloadedEvent, sender=self)

    def reloadAll(self):
        self.reload() # We create and delete layers and objects here
        for x in self.layers: x.reloadAll()
        for x in self.objects: x.reload()

    def _calculatePath(self):
        self._hpath = self._path / DEFAULT_EXT

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
