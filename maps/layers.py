from dataclasses import KW_ONLY, dataclass, field, asdict
from math import trunc
from addict import Dict
from dataclass_wizard import json_field, YAMLWizard
import shapely as sh
from pathlib import Path
from typing import Iterable, List, DefaultDict, Any, Optional
from PIL import Image
import os, yaml, shutil
import  numpy as np
from pydispatch import dispatcher
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from lockfile import Lock
import threading
from glob import glob
from .defs import *
from .objects import MapObject


@dataclass
class MapLayer(YAMLWizard):
    _: KW_ONLY
    kind: Any | int = json_field("TYPE", all=True, default=LayerKind.default.value)
    name: Any | str = json_field("NAME", all=True, default="")
    size: Any | float | int = json_field("SIZE", all=True, default=10.0)
    origin: Any | list[int] = json_field("ORIG", all=True, default_factory=list)
    source: Any | int = json_field("SRC", all=True, default=LayerDataSource.user.value)

    def __post_init__(self):
        self.objects: list[MapObject] = []
        if self.origin == []:
            self.origin = [0, 0, 0]
        self._im: dict[str, Image.Image] = dict()
        self._pixels = None
        self._parent: Any = None
        self._chunksToSave: set[str] = set()
        self._path = Path()
        self._hpath = Path()
        self._layerID = -1
        self._lastSaved = None
        self._needsSave = False
        self._needsReload = True
        self._h = None
        self._images = {}
        self.size = float(self.size)
        self.ref = None

    # def to_dict(self):
    #     return asdict(self, dict_factory=lambda x: {k: v for (k, v) in x if v is not None})

    def _encoder(self, dic: dict, **kwargs):
        return yaml.dump({k: v for k, v in dic.copy().items() if v is not None}, **kwargs)

    def object(self, num: int) -> MapObject | None:
        return next((x for x in self.objects if x._objectID == num), None)

    def objectNamed(self, name: str, *, create = False) -> MapObject | None:
        res = next((x for x in self.objects if x.name == name), None)
        if create and res is None:
            res = MapObject(name=name)
            self.addObject(res)
        return res

    def addObject(self, obj: MapObject, *, reload=False, silent=False):
        if obj._objectID < 0:
            existingIDs = set([x._objectID for x in self.objects])
            obj._objectID = max(existingIDs)+1 if len(existingIDs)>0 else 0
        obj.setParent(self)
        if reload: obj.reload(force=True)
        self.objects.append(obj)
        if not silent: dispatcher.send(mapObjectCreatedEvent, sender=self, event={"object": obj})

    def deleteObject(self, obj: MapObject | None, *, fromdisk=True):
        print(f"Delete object called for ID {obj._objectID} in layer {self._layerID}")
        if obj:
            print("Deleting...")
            # try:
            #     if obj.ref is not None:
            #         obj.ref.delete()
            # except:
            #     pass
            dispatcher.send(mapObjectDeletedEvent, sender=self, event={"object": obj})
            if fromdisk: obj.deleteFromDisk()
            self.objects.remove(obj)

    def deleteChunk(self, chunk: str | None, *, fromdisk=True):
        if chunk and (chunkpath := self._images.get(chunk)):
            dispatcher.send(mapObjectDeletedEvent, sender=self, event={"chunk": chunk, "path": chunkpath})
            if fromdisk: os.unlink(chunkpath)
            self._images.pop(chunk)
            dispatcher.send(mapLayerChunkDeletedEvent, sender=self, event={"chunk": chunk})

    def PILImageHandle(self, chunk: str):
        if self._im != {} and (img_path := self._images.get(chunk)):
            if img := self._im.get(chunk): return img
            full_path = self._path / str(img_path)
            if full_path.exists() and full_path.is_file():
                return Image.open(full_path)

    _propNames = {
        "TYPE" : "kind",
        "NAME" : "name",
        "SIZE": "size",
        "ORIG": "origin",
        "SRC": "source"
    }

    def update(self, dic: dict[str, Any]):
        for key, val in dic.items():
            if key.startswith('_'): continue  # skip private
            key = self._propNames[key]
            print(f"L{self._layerID} Updating {key = } {val = }")
            if hasattr(self, key):
                self.__setattr__(key, val)
        dispatcher.send(mapLayerUpdatedEvent, sender=self, event={"change": dic})

    def imageBytes(self, chunk: str) -> np.ndarray:
        """dtype=np.uint8"""
        return np.array(self._im[chunk])

    def setChunkImageBytes(self, chunk: str, bytes):
        """dtype=np.uint8"""
        bytes = np.asarray(bytes, dtype=np.uint8)
        img = Image.fromarray(bytes)
        self._im[chunk] = img
        self._chunksToSave.add(chunk)
        dispatcher.send(mapLayerChunkUpdatedEvent, sender=self, event={"chunk": chunk})

    @classmethod
    def xyzForChunkName(cls, chunk: str):
        # NW.0.0.0 - example
        pcs = chunk.split('.')
        x = int(pcs[1]) * (-1 if pcs[0][1] == 'W' else 1)
        y = int(pcs[2]) * (-1 if pcs[0][0] == 'S' else 1)
        z = int(pcs[3])
        return x, y, z

    def chunkForPoint(self, point: list[int | float] | tuple[int | float, ...] | MapObject) -> tuple[str, int, int, int]:
        if isinstance(point, MapObject):
            point = point.last
            if not isinstance(point, sh.Point): raise Exception("Given MapObject is not a point")
            coords = (point.x, point.y, point.z) if point.has_z else (point.x, point.y)
        else:
            coords = point
        x = trunc((coords[0] + self.origin[0]) / self.size)
        y = trunc((coords[1] + self.origin[1]) / self.size)
        z = trunc((coords[2] + self.origin[2]) / self.size) if len(coords) >= 3 else 0  # type: ignore
        dir1 = 'N' if x >= 0 else 'S'
        dir2 = 'E' if x >= 0 else 'W'
        name = f"{dir1+dir2}.{str(x)}.{str(y)}.{str(z)}"
        return name, x, y, z

    def toChunkCoordinates(self, chunk:str, point: list[int | float] | tuple[int | float, ...] | MapObject) -> tuple:
        if isinstance(point, MapObject):
            point = point.last
            if not isinstance(point, sh.Point): raise Exception("Given MapObject is not a point")
            coords = (point.x, point.y, point.z) if point.has_z else (point.x, point.y)
        else:
            coords = point
        x, y, z = self.xyzForChunkName(chunk)
        res = (point[0]-x, point[1]-y, point[2]-z)
        return res

    def __getitem__(self, item: str | int):
        if isinstance(item, str): return self.objectNamed(item)
        if isinstance(item, int): return self.object(item)

    def _calculatePath(self):
        if self._parent:
            base: Path = self._parent._path
            self._path = base / ('L' + str(self._layerID))
            self._hpath = self._path / DEFAULT_HEADER_NAME
        else:
            self._path = Path()
            self._hpath = Path()

    def setParent(self, parent):
        self._parent = parent
        self._h = parent._h
        self._calculatePath()
        for obj in self.objects: obj.setParent(self)

    def lazyReload(self):
        self._needsReload = True

    def lazySave(self):
        self._needsSave = True

    def reload(self, force=False):
        def procReload():
            self._reloadInfo(force)
            self._reloadObjects(force)
            self._reloadImages(force)
            self._needsReload = False

        if force:
            procReload()
            return
        if self._needsReload:
            if self._h: self._h.put((procReload, []))

    def _reloadInfo(self, force=False):
        if self._hpath != Path():
            with open(self._hpath, 'r') as f:
                with threading.Lock():
                    # s = f.read()
                    dic = yaml.safe_load(f)
                print(f"Reloading layer info, read dict from file: {dic}")
                # new = MapLayer.from_yaml_file(str(self._hpath))
                # new = MapLayer.from_yaml(s)
            # if isinstance(new, list): new = new[0]
            # self.update(yaml.safe_load(self._hpath.read_text()))
            # self.update(asdict(new))
            self.update(dic)

    def _reloadObjects(self, force=False):

        def getObjectID(path: Path): return int(path.stem)

        objfiles = list([Path(p) for p in glob(str(self._path/OBJECT_PATTERN))])
        print(f"L{self._layerID} Reloading object files: {list(objfiles)}")
        newObjectIDs = list([getObjectID(o) for o in objfiles])
        objTup = zip(objfiles, newObjectIDs)
        # print(objTup)
        print(f"L{self._layerID} Existing objects: {self.objects}")
        oldObjectIDs = set([o._objectID for o in self.objects])
        newObjectIDs = set(newObjectIDs)
        objtocreate = newObjectIDs - oldObjectIDs
        objtodelete = oldObjectIDs - newObjectIDs
        print(f"Objects to be created: {objtocreate} \nObjects to be deleted: {objtodelete}")
        for file, num in objTup:
            if num in objtocreate:
                # new = MapObject.from_yaml_file(str(file))
                new = MapObject()
                # if isinstance(new, list): new = new[0]
                if len(oldObjectIDs) == 0: new._objectID = 0
                else: new._objectID = max(oldObjectIDs)+1
                new.setParent(self)
                new.reload(force)
                self.objects.append(new)
                dispatcher.send(mapObjectCreatedEvent, sender=self, event={"object": new})
        for x in self.objects:
            if x._objectID in objtodelete: self.deleteObject(x)

    def _reloadImages(self, force=False):
        def getChunkName(path: Path): return path.stem
        imgfiles = list([Path(p) for p in glob(str(self._path/CHUNK_PATTERN))])
        for file in imgfiles:
            self._images[getChunkName(file)] = file

    def addChunk(self, chunk, file):
        self._images[chunk] = file
        dispatcher.send(mapLayerChunkCreatedEvent, sender=self, event={"chunk": chunk, "path":file})

    def chunksAvailable(self):
        return self._images

    def save(self, img=False, force=False):

        def procSave():
            if self._path == Path():
                print("Attempting to save with empty path")
                return
            if not self._path.exists():
                print(f"Creating directory for layer at path: {self._path}")
                self._path.mkdir(parents=True)
            if self._hpath != Path():
                with threading.Lock():
                    self.to_yaml_file(str(self._hpath), encoder=self._encoder) # type: ignore
            self._needsSave = False

        def procSaveImg():
            for chunk in self._chunksToSave: self.saveChunk(chunk)

        if self._needsSave or force:
            print(f"Called save {self._path = }")
            if self._h: self._h.put((procSave, []))

        if img:
            if self._h: self._h.put((procSaveImg, []))


    def saveChunk(self, chunk):
        if img := self._im.get(chunk):
            path = self._path / (chunk + '.tiff')
            print(f"Saving chunk image at path: {path}")
            with threading.Lock():
                img.save(path, format="TIFF", save_all=True)
            self._im.pop(chunk)

    def saveAllChunks(self):
        for chunk in list(self._im): self.saveChunk(chunk)

    def reloadAll(self, force=False):
        self.reload(force=force)
        for obj in self.objects: obj.reload(force=force)

    def saveAll(self, force=False):
        self.save(force=force)
        for obj in self.objects: obj.save(force=force)

    def deleteFromDisk(self):
        self.objects.clear()
        if self._path != Path():
            if Path(self._path) in [Path('/'), Path('~'), Path('~').expanduser()]: return # Avoid accidents
            shutil.rmtree(str(self._path))
