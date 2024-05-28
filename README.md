*nvmaps* is a simple library for working with map information. It's intended for use in robotic applications where the user has to input data that would be then processed by the robot in real-time, and acts a map data storage.

Features:
- Geometry change history
- Human-editable format
- Global and local coordinates
- Event hooks (pydispatcher)

Planned:
- Support for n-vector and longtitude-latitude coordinates
- Geofencing

### Format
nvmaps uses YAML and Well-Known Text to store data and achieve high readability. The data is also stored in separate files to be able to easily edit layer structure if required.

Example:
```
My Map.map/
  info.yml <- Global layer info
  0.yml <- Global layer object
  L0/
    info.yml <- Local layer info
    0.yml <- Local layer object
    1.yml
    2.yml
    SW.0.0.0.png <- Image chunk
    NW.1.2.0.png
  L1/
    info.yml
    0.yml
```

### Usage example

```python
from nvmaps import Map, MapObject, MapLayer, LayerKind
import shapely as sh

my_map = Map.load("~/My Map.map")

# Creating an object, approach 1
my_point = MapObject("Point 1")
my_point.update({"geometry": sh.Point(25.0, 30.0)})
my_map.addObject(my_point)

# Creating a layer, approach 2
lay = my_map.layerNamed("Occupancy Grid", create=True)
lay.kind = LayerKind.occupancy2D.value # this layer will contain occupancy map images
other_point = lay.objectNamed("Point 2", create=True)
other_point.makePoint([21.0, 29.0])

```
