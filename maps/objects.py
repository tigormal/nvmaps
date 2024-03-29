from dataclasses import KW_ONLY, dataclass, field, asdict
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
    anchors: Any | dict | None =    json_field("ANC", all=True, default=None)
    heading: Any | int | None =     json_field("HEAD", all=True, default=None)
    icon: Any | str | None =        json_field("ICON", all=True, default=None)
    mods: Any | list | None =       json_field("MODS", all=True, default=None)
    amps: Any | list | None =       json_field("AMPS", all=True, default=None)

    def __post_init__(self):
        self._parent = None
        self._objectID = 0
        self.ref = None
        self._path = Path()
        self._hpath = Path()
        self._lastSaved = None
        self.geometry = {dt.fromisoformat(key): sh.from_wkt(val) for key, val in self.geometry.items()}
        # for key, val in self.geometry:
            # self.geometry[key] = sh.from_wkt(val)

    def to_dict(self):
        # TODO: check if timezone is correct when loading from multiple data sources in different timezones
        g = {key.astimezone().isoformat(): sh.to_wkt(val) for key, val in self.geometry.items()}
        dic = {k: v for k, v in asdict(self, ).items() if v is not None}
        # dic = asdict(self, dict_factory=lambda x: {k: v for (k, v) in x if v is not None})
        dic["geometry"] = g
        return dic

    def _encoder(self, dic, **kwargs):
        return yaml.dump({k: v for k, v in dic.items() if v is not None}, **kwargs)

    # def to_yaml(self, encoder, **encoder_kwargs):
    #     if encoder is None:
    #         encoder = yaml.dump
    #     return encoder(self._to_dict(), **encoder_kwargs)

    @property
    def last(self) -> sh.Geometry:
        return self.geometry[max(list(self.geometry))]

    def setParent(self, parent):
        self._parent = parent
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
                if isinstance(obj.geometry, sh.Point):
                    if self.anchors is None:
                        self.anchors = {}
                    self.anchors[i] = obj.name
                    res.append(obj.geometry)
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
                if isinstance(obj.geometry, sh.Point):
                    if self.anchors is None: self.anchors = {}
                    self.anchors[i] = obj.name
                    res.append(obj.geometry)
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

    def reload(self):
        if self._path.exists():
            new = MapObject.from_yaml_file(str(self._path))
            if isinstance(new, list): new = new[0]
            print(f"{self._objectID} RELOAD \n{asdict(new)}")
            self.update(asdict(new))
            # self.from_yaml_file(str(self._path))
            # dic = yaml.safe_load(self._path.read_text())
            # self.update(dic, skipGeometry=True)
            # self.geometry = {key.fromisoformat(): sh.from_wkt(val) for key, val in dic.geometry.items()}

    def save(self):
        print(f"Called save {self._path = }")
        if self._path != Path():
            self.to_yaml_file(str(self._path),
                encoder=self._encoder) # type: ignore

    def deleteFromDisk(self):
        if self._path != Path():
            print(f"Deleting object file: {self._path}")
            os.unlink(self._path)

    def update(self, dic: dict[str, Any], modifyGeometry=False, skipGeometry=False):
        for key, val in dic.items():
            if key == 'geometry':
                if skipGeometry: continue
                if modifyGeometry:
                    latestTime = max(list(self.geometry))
                    self.geometry[latestTime] = val
                else:
                    self.geometry[dt.now(dt.now().astimezone().tzinfo)] = val
                continue
            if hasattr(self, key):
                print(f"{self._objectID} Updating {key = } {val =}")
                self.__setattr__(key, val)
        dispatcher.send(mapObjectUpdatedEvent, sender=self, event={"change": dic})
