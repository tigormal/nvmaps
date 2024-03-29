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
