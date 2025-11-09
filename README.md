# Ihara-Grubb Net Transformation

A Python implementation of the Ihara-Grubb (IG) Net Transformation algorithm for visualizing network topology by transforming physical distances into virtual distances that account for network latency and resistance.

The Ihara-Grubb transformation is a mathematical approach to network visualization that maps physical geographic distances between network nodes onto a virtual space where distances are modulated by network performance characteristics. This transformation provides insights into the "virtual effort" required to traverse network paths, accounting for both physical separation and network latency.

## Mathematical Foundation

### Core Formula

The Ihara-Grubb Virtual Distance (IG Distance) is calculated using the following formula:

```
IG_Distance = Physical_Distance_KM × (1 + (Worst_Latency / Latency_Base))
```

Where:
- **Physical_Distance_KM**: The great-circle distance between two nodes on Earth (calculated using the Haversine formula)
- **Worst_Latency**: The maximum network latency between the two nodes (in milliseconds)
- **Latency_Base**: A normalization constant representing the baseline acceptable latency (default: 100ms)
- **IG Factor**: The multiplier `(1 + (Worst_Latency / Latency_Base))` that represents the "terrain complexity" or network resistance

### Interpretation

- **IG Factor = 1.0**: No network resistance (latency equals or is below the base threshold)
- **IG Factor > 1.0**: Network resistance increases virtual distance proportionally
- **IG Factor = 2.0**: Network latency doubles the effective distance (e.g., 1000km physical distance becomes 2000km virtual distance)

The transformation effectively creates a "virtual terrain" where high-latency connections appear as longer distances, making it easier to identify network bottlenecks and understand the true cost of network traversal.

## Installation

### Requirements

- Python 3.7 or higher
- Network connectivity for latency measurements and Geo-IP services

### Dependencies

```bash
pip install httpx matplotlib loguru
```

Or install from requirements:

```bash
pip install -r requirements.txt
```

## Usage

### Basic Example

```python
from iharra_transform import IharaGrubbTransform

# Create transformer instance
transformer = IharaGrubbTransform(latency_base_ms=100.0)

# Automatically detect and add user node
user_node = transformer.add_user_node_auto(
    name="My Console (User)",
    elevation_floor=15.0
)

# Add network nodes
transformer.add_node(
    "Cloudflare DNS",
    lat=37.7749,
    lon=-122.3941,
    elevation_floor=5,
    ip_address="1.1.1.1"
)

transformer.add_node(
    "Google DNS",
    lat=40.7128,
    lon=-74.0060,
    elevation_floor=30,
    ip_address="8.8.8.8"
)

# Define connections to analyze
connections = [
    ("My Console (User)", "Cloudflare DNS"),
    ("My Console (User)", "Google DNS"),
]

# Generate visualization
transformer.plot_net(connections)
```

### Manual Location Specification

If automatic location detection fails or you want to specify coordinates manually:

```python
transformer.add_node(
    name="My Console (User)",
    lat=37.7749,  # San Francisco
    lon=-122.4194,
    elevation_floor=15.0,
    ip_address="0.0.0.0",
    is_user_node=True
)
```

### Advanced Configuration

```python
transformer = IharaGrubbTransform(
    latency_base_ms=150.0,      # Higher base latency threshold
    ping_count=8,               # More ping packets for accuracy
    ping_timeout=10,            # Longer timeout
    fallback_latency_ms=500.0   # Custom fallback latency
)
```

## API Reference

### `IharaGrubbTransform`

Main class for performing IG transformations.

#### Parameters

- `latency_base_ms` (float): Base latency for normalization (default: 100.0)
- `ping_count` (int): Number of ping packets to send (default: 4)
- `ping_timeout` (int): Ping timeout in seconds (default: 5)
- `fallback_latency_ms` (float): Latency value when ping fails (default: 999.0)

#### Methods

##### `add_node(name, lat, lon, elevation_floor, ip_address="", is_user_node=False)`

Add a node to the network.

**Parameters:**
- `name` (str): Human-readable node name
- `lat` (float): Latitude in decimal degrees
- `lon` (float): Longitude in decimal degrees
- `elevation_floor` (float): Elevation/floor level for visualization
- `ip_address` (str): IP address for latency measurement (optional)
- `is_user_node` (bool): Whether this is the user's node

**Returns:** `Node` object

##### `add_user_node_auto(name="My Console (User)", elevation_floor=15.0)`

Automatically detect and add the user's node using Geo-IP.

**Parameters:**
- `name` (str): Name for the user node
- `elevation_floor` (float): Estimated floor level

**Returns:** `Node` object

**Raises:** `RuntimeError` if location detection fails

##### `measure_latencies()`

Measure network latency for all nodes with IP addresses.

##### `calculate_ig_distance(node1, node2)`

Calculate the IG Virtual Distance between two nodes.

**Parameters:**
- `node1` (Node): First node
- `node2` (Node): Second node

**Returns:** Tuple of `(physical_distance_km, worst_latency, ig_distance, ig_factor)`

**Raises:** `ValueError` if latencies haven't been measured

##### `haversine(lat1, lon1, lat2, lon2)`

Calculate great-circle distance between two points using the Haversine formula.

**Parameters:**
- `lat1`, `lon1` (float): Coordinates of first point
- `lat2`, `lon2` (float): Coordinates of second point

**Returns:** Distance in kilometers

##### `plot_net(connections)`

Generate and display network visualization.

**Parameters:**
- `connections` (List[Tuple[str, str]]): List of node name pairs to connect

## Visualization

The generated visualization displays:

- **Nodes**: Represented as colored circles
  - Orange: User node
  - Blue: Other network nodes
  - Size: Larger for user node
  - Labels: Show node name, elevation, and latency

- **Connections**: Lines between nodes
  - **Thickness**: Proportional to IG Virtual Distance (thicker = higher effort)
  - **Color**: Gradient from green (low effort) to red (high effort)
  - **Labels**: Display IG Effort value at midpoint

- **Axes**:
  - X-axis: Longitude (East/West)
  - Y-axis: Elevation/Floors

## Algorithm Details

### Distance Calculation

Physical distances are calculated using the Haversine formula, which accounts for the Earth's curvature:

```
a = sin²(Δlat/2) + cos(lat1) × cos(lat2) × sin²(Δlon/2)
c = 2 × atan2(√a, √(1-a))
distance = R × c
```

Where R = 6371 km (Earth's radius)

### Latency Measurement

The implementation uses the system's native `ping` command to measure round-trip latency:
- **Windows**: `ping -n <count> <ip>`
- **Linux/macOS**: `ping -c <count> -W 1 <ip>`

Average latency is extracted from ping output using regex patterns.

### IG Transformation

The transformation process:

1. Calculate physical distance using Haversine formula
2. Measure latency to both nodes (if IP addresses provided)
3. Determine worst latency (maximum of the two)
4. Calculate IG factor: `1 + (worst_latency / latency_base_ms)`
5. Apply transformation: `ig_distance = physical_distance × ig_factor`

## Limitations and Considerations

### Network Latency Variability

Network latency can vary significantly based on:
- Time of day and network congestion
- Routing changes
- Network conditions

The implementation measures latency at a single point in time. For production use, consider averaging multiple measurements over time.

### Geo-IP Accuracy

Automatic location detection via Geo-IP services provides approximate locations, typically accurate to city-level. For precise measurements, manually specify coordinates.

### Ping Limitations

- Some networks block ICMP (ping) packets
- Firewalls may prevent latency measurements
- VPN usage may affect location detection and latency measurements

### Elevation Parameter

The `elevation_floor` parameter is conceptual and used only for visualization purposes. It does not affect distance or latency calculations.

## Error Handling

The implementation includes robust error handling:

- **Geo-IP Failures**: Falls back to alternative services
- **Ping Failures**: Uses fallback latency value
- **Invalid Coordinates**: Validates latitude/longitude ranges
- **Missing Latencies**: Raises clear error messages

## Contributing

When contributing to this implementation:

1. Maintain the mathematical accuracy of the IG transformation
2. Add comprehensive docstrings to all functions
3. Include error handling for edge cases
4. Update this README with new features or changes

## References

The Ihara-Grubb transformation is based on concepts from:
- Network topology analysis
- Graph theory applications to network science
- Geographic information systems (GIS) for network visualization

**Note:** The name "Ihara" is a reference to Cyberpunk (Cyberpunk 2077).

## License

See the main project LICENSE file for license information.
