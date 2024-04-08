from enum import Enum

DEFAULT_EXT = '.yml'
DEFAULT_HEADER_NAME = 'info' + DEFAULT_EXT
LAYER_PATTERN = 'L[0-9]*'
OBJECT_PATTERN = '[0-9]*' + DEFAULT_EXT
CHUNK_PATTERN = '[NS][WE].[0-9]*.[0-9]*.*[0-9]*.*'

# Events
mapUpdatedEvent = 'mapUpdatedEvent'
mapSavedEvent = 'mapSavedEvent'
mapReloadedEvent = 'mapReloadedEvent'
mapObjectCreatedEvent = 'mapObjectCreatedEvent'
mapObjectDeletedEvent = 'mapObjectDeletedEvent'
mapLayerCreatedEvent = 'mapLayerCreatedEvent'
mapLayerDeletedEvent = 'mapLayerDeletedEvent'
mapObjectUpdatedEvent = 'mapObjectUpdatedEvent'
mapLayerUpdatedEvent = 'mapLayerUpdatedEvent'
mapLayerChunkUpdatedEvent = 'mapLayerChunkUpdatedEvent'
mapLayerChunkCreatedEvent = 'mapLayerChunkCreatedEvent'
mapLayerChunkDeletedEvent = 'mapLayerChunkDeletedEvent'
mapFileCreatedEvent = 'mapFileCreatedEvent'
mapFileUpdatedEvent = 'mapFileUpdatedEvent'
mapFileDeletedEvent = 'mapFileDeletedEvent'

# Enums
class LayerKind(Enum):
    default = 0
    base = 1
    topography = 2
    navigation = 3
    occupancy2D = 4
    occupancy3D = 5
    markup = 6

class LayerDataSource(Enum):
    machine = 0
    user = 1

class ObjectColor(Enum):
    yellow = 0
    blue = 1
    green = 2
    red = 3
    orange = 4
    purple = 5
    white = 6
    black = 7

class ObjectAffiliation(Enum):
    unknown = 0
    ally = 1
    friendly = 2
    hostile = 3
    me = 4
    other = 5

class GlobalCoordinateKind(Enum):
    xyz = 0
    lla = 1
    nvec = 2



# class MapFileHandler(FileSystemEventHandler):
# class MapFileHandler(watchdog.events.PatternMatchingEventHandler):
#     def __init__(self, parent):
#         self.parent = parent
#         watchdog.events.PatternMatchingEventHandler.__init__(self,
#             patterns=[
#                 # str(parent._path) + '/' + DEFAULT_HEADER_NAME,
#                 # str(parent._path) + '/' + OBJECT_PATTERN,
#                 str(parent._path) + '/' + "*" + '/' + DEFAULT_HEADER_NAME,
#                 str(parent._path) + '/' + "*" + '/' + OBJECT_PATTERN,
#             ],
#             ignore_directories=True,
#             case_sensitive=False
#         )

#     def identifyElementsFromPath(self, path) -> tuple[MapLayer | None, MapObject | None, str | None]:

#         def getObjectID(path: Path): return int(path.stem)
#         def getChunkName(path: Path): return path.stem
#         def getObjectLayerID(path: Path):
#             ldir = path.parent
#             if ldir == self.parent._path:
#                 print(f"{ldir = } == {self.parent._path = }")
#                 res = None
#             else:
#                 res = int(ldir.name.strip('L'))
#             return res

#         resLayer = resObject = resChunk = None
#         # glob_list = [path]
#         # print(f"{glob_list = }")
#         path = Path(path).resolve()
#         lnum = getObjectLayerID(path)
#         if lnum: self.resLayer = self.parent.layer(lnum)
#         if path.name == DEFAULT_HEADER_NAME:
#             print('header')
#         print("path glob:", list(path.glob("*"+OBJECT_PATTERN)))
#         # if any(path.glob(CHUNK_PATTERN)): print('chunk')
#         # if any(path.glob(OBJECT_PATTERN)): print('object')
#         # for pattern in [CHUNK_PATTERN, OBJECT_PATTERN, DEFAULT_HEADER_NAME]:
#         #     res = glob("*/"+pattern)
#         #     print(f"{res = }")
#         #     if len(res)>0:
#         #         lnum = getObjectLayerID(path)
#         #         if lnum: self.resLayer = self.parent.layer(lnum)
#         #         # Updated layer or map info
#         #         if pattern == DEFAULT_HEADER_NAME:
#         #             print("header")
#         #             ...
#         #             break
#         #         # Updated chunk image file
#         #         elif pattern == CHUNK_PATTERN:
#         #             print("chunk")
#         #             resChunk = getChunkName(path)
#         #             break
#         #         # Updated object file in layer or map
#         #         elif pattern == OBJECT_PATTERN:
#         #             print("object")
#         #             onum = getObjectID(path)
#         #             if resLayer: resObject = resLayer.object(onum)
#         #             break
#         return resLayer, resObject, resChunk


#     def on_modified(self, event):
#         if event:
#             match event.event_type:
#                 case 'modified':
#                     # Invoke reload
#                     print(f"FILE MODIFIED {event.src_path}")
#                     print(self.identifyElementsFromPath(event.src_path))
#                 case 'created':
#                     # Invoke layer or object creation
#                     print(f"FILE CREATED {event.src_path}")
#                     print(self.identifyElementsFromPath(event.src_path))
#                 case 'deleted':
#                     # Invoke layer or object deletion
#                     print(f"FILE DELETED {event.src_path}")
#                     print(self.identifyElementsFromPath(event.src_path))
#                 case 'moved':
#                     # Invoke move of mapobject to layer
#                     print(f"FILE MOVED {event.src_path}")
#                     print(self.identifyElementsFromPath(event.src_path))
#                 case _: pass
#             # print(event.src_path)
#             # self.parent.reload()

#     # def on_modified(self, event):
#     #     if event:
#     #         print(f"FILE MODIFIED {event.src_path}\n {self.identifyElementsFromPath(event.src_path)}")

#     def on_deleted(self, event):
#         if event:
#             print(f"FILE DELETED {event.src_path}\n {self.identifyElementsFromPath(event.src_path)}")

#     def on_created(self, event):
#         if event:
#             # Invoke layer or object creation
#             print(f"FILE CREATED {event.src_path}\n {self.identifyElementsFromPath(event.src_path)}")
#             print()
#             # print(event.src_path)
#             # self.parent.reload()
