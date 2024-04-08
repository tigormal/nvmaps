from dataclasses import KW_ONLY, dataclass, field, asdict
# from lockfile import Lock
from threading import Lock
from addict import Dict
from dataclass_wizard import json_field, YAMLWizard, JSONWizard
import shapely as sh
from pathlib import Path
from typing import Iterable, List, DefaultDict, Any, Optional
from pydispatch import dispatcher
from datetime import datetime as dt, timezone as tz
from glob import glob
import os, yaml
from .defs import *


@dataclass
class MapObject(YAMLWizard):

    name: Any | str =               json_field("NAME", all=True, default="")
    geometry: Any | dict =          json_field("GEOM", all=True, default_factory=dict)
    color: Any | int =              json_field("COL", all=True, default=0)
    highlight: Any | bool | None =  json_field("HL", all=True, default=None)
    showtext: Any | bool | None =   json_field("ST", all=True, default=None)
    anchors: Any | dict[int, int] | None = json_field("ANC", all=True, default=None) # {<INDEX>: <OBJECT ID>} object should be in the same layer
    heading: Any | int | float | None =     json_field("HEAD", all=True, default=None)
    icon: Any | str | None =        json_field("ICON", all=True, default=None)
    mods: Any | list | None =       json_field("MODS", all=True, default=None)
    amps: Any | list | None =       json_field("AMPS", all=True, default=None)

    def __post_init__(self):
        self._parent = None
        self._objectID = -1
        self.ref: Any = None
        self._path = Path()
        self._hpath = Path()
        self._lastSaved = None
        self._needsSave = False
        self._needsReload = True
        self._h = None
        self.geometry = {dt.fromisoformat(key): sh.from_wkt(val) for key, val in self.geometry.copy().items()}
        # for key, val in self.geometry:
            # self.geometry[key] = sh.from_wkt(val)

    def to_dict(self):
        # g = {key.astimezone().isoformat(): sh.to_wkt(val) for key, val in self.geometry.copy().items()}
        g = {}
        for key, val in self.geometry.copy().items():
            # print(f"TO_DICT: {type(key), key}: {type(val), val}")
            g[key.astimezone().isoformat()] = sh.to_wkt(val)
        dic = {
            "NAME": self.name,
            "GEOM": self.geometry,
            "COL": self.color,
            "HL": self.showtext,
            "ANC": self.anchors,
            "HEAD": self.heading,
            "ICON": self.icon,
            "MODS": self.mods,
            "AMPS": self.amps
        }
        dic = {k: v for k, v in dic.items() if v is not None}
        # dic = {k: v for k, v in asdict(self).copy().items() if v is not None}
        # dic = asdict(self, dict_factory=lambda x: {k: v for (k, v) in x if v is not None})
        # dic["geometry"] = g
        dic["GEOM"] = g
        return dic

    def _encoder(self, dic: dict, **kwargs):
        return yaml.dump({k: v for k, v in dic.copy().items() if v is not None}, **kwargs)

    def to_yaml(self, encoder, **encoder_kwargs):
        if encoder is None:
            encoder = self._encoder#yaml.dump
        return encoder(self.to_dict(), **encoder_kwargs)

    @property
    def last(self) -> sh.Geometry | None:
        g = list(self.geometry)
        if len(g) == 0: return None
        return self.geometry[max(g)]

    def setParent(self, parent):
        self._parent = parent
        self._h = parent._h
        self._calculatePath()

    def makePoint(self, coords: Iterable[int | float], time=None):
        if time is None:
            time = dt.now(dt.now().astimezone().tzinfo)
        self.geometry[time] = sh.Point(coords)
        dispatcher.send(mapObjectUpdatedEvent, sender=self, event={"object": self})

    def makeLine(self, points: Iterable[Iterable[int | float]], time=None):
        res = []
        for i, obj in enumerate(points):
            if isinstance(obj, MapObject):
                if isinstance(obj.last, sh.Point):
                    if self.anchors is None:
                        self.anchors = {}
                    self.anchors[i] = obj.name
                    res.append(obj.last)
            else:
                res.append(obj)
        if time is None:
            time = dt.now(dt.now().astimezone().tzinfo)
        self.geometry[time] = sh.LineString(res)
        dispatcher.send(mapObjectUpdatedEvent, sender=self, event={"object": self})

    def makePolygon(self, shell: Iterable[Iterable[int | float]], time=None):
        res = []
        for i, obj in enumerate(shell):
            if isinstance(obj, MapObject):
                if isinstance(obj.last, sh.Point):
                    if self.anchors is None: self.anchors = {}
                    self.anchors[i] = obj.name
                    res.append(obj.last)
            else:
                res.append(obj)
        # if res[0] != res[-1]:
        #     res.append(res[0])
        if time is None:
            time = dt.now(dt.now().astimezone().tzinfo)
        self.geometry[time] = sh.Polygon(res)
        dispatcher.send(mapObjectUpdatedEvent, sender=self, event={"object": self})

    def addHole(self, hole: list, time = None):
        if isinstance(self.geometry, sh.Polygon):
            # TODO: Add hole to existing polygon
            ...

    # def __hash__(self):
    #     return self._objectID

    # def __eq__(self, other):
    #     return self._objectID == other._objectID

    def _calculatePath(self):
        if self._parent:
            base: Path = self._parent._path
            if base == Path(): self._path = Path(); return
            self._path = base / (str(self._objectID) + DEFAULT_EXT)
        else:
            self._path = Path()

    def lazyReload(self):
        self._needsReload = True

    def lazySave(self):
        self._needsSave = True

    def reload(self, force=False):
        def procReload():
            try:
                new = MapObject.from_yaml_file(str(self._path))
            except Exception as e:
                print(f"Reload failed. Reason: {e}")
                return
            if isinstance(new, list): new = new[0]
            print(f"{self._objectID} RELOAD \n{asdict(new)}")
            self.update(asdict(new))
            self._needsReload = False
            # self.from_yaml_file(str(self._path))
            # dic = yaml.safe_load(self._path.read_text())
            # self.update(dic, skipGeometry=True)
            # self.geometry = {key.fromisoformat(): sh.from_wkt(val) for key, val in dic.geometry.items()}
        if (self._needsReload or force) and self._path.exists():
            if self._h: self._h.put((procReload, []))


    def save(self, force=False):

        def procSave():
            # with Lock():
            self.to_yaml_file(str(self._path), encoder=self._encoder) # type: ignore
            self._needsSave = False

        print(f"Called save {self._path = }")
        if (self._needsSave or force) and self._path != Path():
            if self._h: self._h.put((procSave, []))

    def deleteFromDisk(self):
        if self._path != Path():
            print(f"Deleting object file: {self._path}")
            os.unlink(self._path)

    def update(self, dic: dict[str, Any], *, modifyGeometry=False, skipGeometry=False):
        for key, val in dic.items():
            if key == 'geometry':
                if skipGeometry: continue
                if isinstance(val, dict):
                    for k, v in val.items():
                        if type(k) is str: k = dt.fromisoformat(k)
                        if type(v) is str: v = sh.from_wkt(v)
                        self.geometry[k] = v
                    continue
                if isinstance(val, str):
                    val = sh.from_wkt(val)
                if not isinstance(val, sh.Geometry):
                    raise Exception(f"Update geometry value is not Geometry type, not {type(val)}")
                if modifyGeometry:
                    if len(list(self.geometry)) == 0:
                        latestTime = dt.now(dt.now().astimezone().tzinfo)
                    else:
                        latestTime = max(list(self.geometry))
                    self.geometry[latestTime] = val
                else:
                    self.geometry[dt.now(dt.now().astimezone().tzinfo)] = val
                continue
            if hasattr(self, key):
                # print(f"{self._objectID} Updating {key = } {val =}")
                self.__setattr__(key, val)
        dispatcher.send(mapObjectUpdatedEvent, sender=self, event={"change": dic})
        self._needsSave = True
