import math
import platform
import re
import subprocess
import time
from typing import Dict, List, Optional, Tuple

import httpx
import matplotlib.pyplot as plt
from loguru import logger

# --- Constants ---
R_EARTH_KM: float = 6371.0  # Radius of the Earth in kilometers
DEFAULT_LATENCY_BASE_MS: float = 100.0
DEFAULT_PING_COUNT: int = 4
DEFAULT_PING_TIMEOUT: int = 5
FALLBACK_LATENCY_MS: float = 999.0


class Node:
    """
    Represents a connected entity (e.g., a server or BBS) in the Net with
    real-world data.

    Args:
        name: Human-readable name for the node
        lat: Latitude in decimal degrees
        lon: Longitude in decimal degrees
        elevation_floor: Conceptual height (e.g., floor number), used for
            visualization in the Y-axis
        ip_address: IP address for latency measurement (optional)
    """

    def __init__(
        self,
        name: str,
        lat: float,
        lon: float,
        elevation_floor: float,
        ip_address: str = "",
    ):
        self.name = name
        self.lat = lat
        self.lon = lon
        self.elevation = elevation_floor
        self.ip_address = ip_address
        self.latency: Optional[float] = None


class IharaGrubbTransform:
    """
    Main class for Ihara-Grubb Net Transformation visualization.

    This class handles network latency measurement, distance calculations,
    and visualization of the virtual network topology.

    Args:
        latency_base_ms: Base latency value for normalization. A latency
            greater than this will significantly increase the virtual effort
            (IG Distance). Defaults to 100.0ms
        ping_count: Number of ping packets to send for latency measurement
        ping_timeout: Timeout in seconds for ping operations
        fallback_latency_ms: Latency value to use when ping fails
    """

    def __init__(
        self,
        latency_base_ms: float = DEFAULT_LATENCY_BASE_MS,
        ping_count: int = DEFAULT_PING_COUNT,
        ping_timeout: int = DEFAULT_PING_TIMEOUT,
        fallback_latency_ms: float = FALLBACK_LATENCY_MS,
    ):
        self.latency_base_ms = latency_base_ms
        self.ping_count = ping_count
        self.ping_timeout = ping_timeout
        self.fallback_latency_ms = fallback_latency_ms
        self.nodes: List[Node] = []
        self.user_node: Optional[Node] = None

    def add_node(
        self,
        name: str,
        lat: float,
        lon: float,
        elevation_floor: float,
        ip_address: str = "",
        is_user_node: bool = False,
    ) -> Node:
        """
        Add a node to the network.

        Args:
            name: Human-readable name for the node
            lat: Latitude in decimal degrees
            lon: Longitude in decimal degrees
            elevation_floor: Conceptual height (e.g., floor number)
            ip_address: IP address for latency measurement (optional)
            is_user_node: Whether this is the user's node

        Returns:
            The created Node object
        """
        node = Node(name, lat, lon, elevation_floor, ip_address)
        self.nodes.append(node)

        if is_user_node:
            self.user_node = node

        logger.debug(f"Added node: {name} at ({lat}, {lon})")
        return node

    def _parse_ipapi_response(
        self, data: Dict
    ) -> Tuple[float, float, str]:
        """
        Parse response from ip-api.com.

        Args:
            data: JSON response data

        Returns:
            Tuple of (latitude, longitude, ip_address)
        """
        return (
            float(data.get("lat", 0)),
            float(data.get("lon", 0)),
            data.get("query", ""),
        )

    def _parse_ipinfo_response(
        self, data: Dict
    ) -> Tuple[float, float, str]:
        """
        Parse response from ipinfo.io.

        Args:
            data: JSON response data

        Returns:
            Tuple of (latitude, longitude, ip_address)
        """
        loc_str = data.get("loc", "0,0")
        coords = loc_str.split(",")
        if len(coords) == 2:
            try:
                lat = float(coords[0])
                lon = float(coords[1])
                return lat, lon, data.get("ip", "")
            except ValueError:
                return 0.0, 0.0, data.get("ip", "")
        return 0.0, 0.0, data.get("ip", "")

    def fetch_user_location(self) -> Tuple[float, float, str]:
        """
        Automatically fetch user's location using Geo-IP API.

        Tries multiple free Geo-IP services as fallbacks:
        1. ip-api.com (primary)
        2. ipinfo.io (fallback)

        Returns:
            Tuple of (latitude, longitude, ip_address)

        Raises:
            RuntimeError: If all Geo-IP services fail
        """
        services = [
            {
                "name": "ip-api.com",
                "url": "http://ip-api.com/json/",
                "parse": self._parse_ipapi_response,
            },
            {
                "name": "ipinfo.io",
                "url": "https://ipinfo.io/json",
                "parse": self._parse_ipinfo_response,
            },
        ]

        for service in services:
            try:
                logger.info(
                    f"Attempting to fetch location from {service['name']}..."
                )
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(service["url"])
                    response.raise_for_status()
                    data = response.json()

                    lat, lon, ip = service["parse"](data)

                    if lat != 0.0 or lon != 0.0:
                        logger.info(
                            f"Successfully fetched location: "
                            f"({lat:.4f}, {lon:.4f}) from {service['name']}"
                        )
                        if ip:
                            logger.info(f"Detected IP address: {ip}")
                        return lat, lon, ip
                    else:
                        logger.warning(
                            f"{service['name']} returned invalid coordinates"
                        )

            except httpx.RequestError as e:
                logger.warning(
                    f"Failed to connect to {service['name']}: {e}. "
                    f"Trying next service..."
                )
                continue
            except httpx.HTTPStatusError as e:
                logger.warning(
                    f"{service['name']} returned error {e.response.status_code}. "
                    f"Trying next service..."
                )
                continue
            except (KeyError, ValueError, TypeError) as e:
                logger.warning(
                    f"Failed to parse response from {service['name']}: {e}. "
                    f"Trying next service..."
                )
                continue
            except Exception as e:
                logger.warning(
                    f"Unexpected error with {service['name']}: {e}. "
                    f"Trying next service..."
                )
                continue

        raise RuntimeError(
            "Failed to fetch user location from all Geo-IP services. "
            "Please provide location manually."
        )

    def add_user_node_auto(
        self,
        name: str = "My Console (User)",
        elevation_floor: float = 15.0,
    ) -> Node:
        """
        Automatically detect and add the user's node using Geo-IP location.

        Args:
            name: Name for the user node
            elevation_floor: Estimated floor level/elevation

        Returns:
            The created user Node object

        Raises:
            RuntimeError: If location detection fails
        """
        try:
            lat, lon, ip = self.fetch_user_location()
            logger.info(
                f"Auto-detected user location: "
                f"Lat={lat:.4f}, Lon={lon:.4f}, IP={ip if ip else 'N/A'}"
            )
        except RuntimeError as e:
            logger.error(str(e))
            raise

        return self.add_node(
            name=name,
            lat=lat,
            lon=lon,
            elevation_floor=elevation_floor,
            ip_address=ip if ip else "0.0.0.0",
            is_user_node=True,
        )

    def get_live_latency(self, ip_address: str) -> float:
        """
        Measures average round-trip latency to a target IP using the system's
        ping command.

        Args:
            ip_address: Target IP address to ping

        Returns:
            Latency in milliseconds, or fallback value if ping fails
        """
        if not ip_address or ip_address == "0.0.0.0":
            logger.debug(
                "Invalid IP address, returning 0.0ms latency"
            )
            return 0.0

        # Configure ping command based on OS
        system = platform.system()
        if system == "Windows":
            command = ["ping", "-n", str(self.ping_count), ip_address]
            regex = r"Average = (\d+)ms"
        elif system in ("Linux", "Darwin"):  # Linux or macOS
            command = [
                "ping",
                "-c",
                str(self.ping_count),
                "-W",
                "1",
                ip_address,
            ]
            regex = r"min/avg/max/[^\s]+ = [\d.]+/([\d.]+)/"
        else:
            logger.warning(
                f"Unsupported OS: {system}, using fallback latency"
            )
            return self.fallback_latency_ms

        try:
            start_time = time.time()
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=self.ping_timeout,
                check=False,  # Don't raise on non-zero exit
            )
            end_time = time.time()

            if result.returncode != 0:
                logger.warning(
                    f"Ping to {ip_address} failed with return code "
                    f"{result.returncode}"
                )
                return self.fallback_latency_ms

            match = re.search(regex, result.stdout)
            if match:
                avg_latency = float(match.group(1))
                logger.debug(
                    f"Measured latency to {ip_address}: {avg_latency}ms"
                )
                return avg_latency

            # Fallback if regex fails
            estimated_latency = (end_time - start_time) * 1000 / 2
            logger.warning(
                f"Could not parse ping output for {ip_address}, "
                f"using estimated latency: {estimated_latency:.1f}ms"
            )
            return estimated_latency

        except subprocess.TimeoutExpired:
            logger.error(
                f"Ping to {ip_address} timed out after {self.ping_timeout}s"
            )
            return self.fallback_latency_ms
        except Exception as e:
            logger.error(
                f"Error pinging {ip_address}: {e}. "
                f"Using fallback latency ({self.fallback_latency_ms}ms)"
            )
            return self.fallback_latency_ms

    def haversine(
        self, lat1: float, lon1: float, lat2: float, lon2: float
    ) -> float:
        """
        Calculates the great-circle distance between two points on the Earth
        using the Haversine formula.

        Args:
            lat1: Latitude of first point in decimal degrees
            lon1: Longitude of first point in decimal degrees
            lat2: Latitude of second point in decimal degrees
            lon2: Longitude of second point in decimal degrees

        Returns:
            Distance in kilometers
        """
        # Validate input coordinates
        if not (-90 <= lat1 <= 90) or not (-90 <= lat2 <= 90):
            raise ValueError(
                "Latitude must be between -90 and 90 degrees"
            )
        if not (-180 <= lon1 <= 180) or not (-180 <= lon2 <= 180):
            raise ValueError(
                "Longitude must be between -180 and 180 degrees"
            )

        # Convert degrees to radians
        lat1, lon1, lat2, lon2 = map(
            math.radians, [lat1, lon1, lat2, lon2]
        )

        dlon = lon2 - lon1
        dlat = lat2 - lat1

        # Haversine formula
        a = (
            math.sin(dlat / 2) ** 2
            + math.cos(lat1)
            * math.cos(lat2)
            * math.sin(dlon / 2) ** 2
        )
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

        distance_km = R_EARTH_KM * c
        return distance_km

    def calculate_ig_distance(
        self, node1: Node, node2: Node
    ) -> Tuple[float, float, float, float]:
        """
        Calculates the Ihara-Grubb Virtual Distance (IG Effort).

        Formula: IG_Distance = Physical_Distance_KM *
                 (1 + (Worst_Latency / Latency_Base))

        Args:
            node1: First node
            node2: Second node

        Returns:
            Tuple of (physical_distance_km, worst_latency, ig_distance,
            ig_factor)

        Raises:
            ValueError: If node latencies have not been measured
        """
        # Validate that latencies have been measured
        if node1.latency is None or node2.latency is None:
            raise ValueError(
                "Latency must be fetched before calculating IG distance. "
                "Call measure_latencies() first."
            )

        # Calculate physical distance
        physical_distance_km = self.haversine(
            node1.lat, node1.lon, node2.lat, node2.lon
        )

        # Determine network resistance (worst latency)
        worst_latency = max(node1.latency, node2.latency)

        # Calculate IG transformation factor
        ig_factor = 1.0 + (worst_latency / self.latency_base_ms)

        # Calculate IG virtual distance
        ig_distance = physical_distance_km * ig_factor

        return (
            physical_distance_km,
            worst_latency,
            ig_distance,
            ig_factor,
        )

    def measure_latencies(self) -> None:
        """
        Measure latencies for all nodes that have IP addresses.
        """
        logger.info("Measuring live network latency for all nodes...")

        for node in self.nodes:
            if node.ip_address:
                node.latency = self.get_live_latency(node.ip_address)
                logger.info(
                    f"Latency to {node.name} ({node.ip_address}): "
                    f"{node.latency:.1f}ms"
                )
            else:
                # Self or node without IP
                if node == self.user_node:
                    node.latency = 0.0
                else:
                    node.latency = 5.0  # Default small latency
                logger.debug(
                    f"Node {node.name} has no IP, using default latency: "
                    f"{node.latency}ms"
                )

    def plot_net(self, connections: List[Tuple[str, str]]) -> None:
        """
        Renders the Net Visualization using Matplotlib.

        Args:
            connections: List of tuples containing node name pairs to connect
        """
        if not self.nodes:
            raise ValueError(
                "No nodes added. Use add_node() to add nodes first."
            )

        # Measure latencies if not already done
        if any(node.latency is None for node in self.nodes):
            self.measure_latencies()

        logger.info("Starting IG Transformation Analysis...")

        # Setup figure and axis
        fig, ax = plt.subplots(figsize=(12, 8))
        ax.set_title(
            "Ihara-Grubb (IG) Net Transformation Visualization (Real Data)",
            fontsize=16,
            fontweight="bold",
        )
        ax.set_xlabel("Real-World Longitude (East/West)", fontsize=12)
        ax.set_ylabel(
            "Real-World Elevation / Floors (Y)", fontsize=12
        )
        ax.grid(True, linestyle="--", alpha=0.6)
        ax.set_axisbelow(True)

        # Create node map
        node_map: Dict[str, Node] = {n.name: n for n in self.nodes}

        # Calculate IG distances for all connections
        all_ig_distances = []
        calculated_connections = []

        for n1_name, n2_name in connections:
            n1 = node_map.get(n1_name)
            n2 = node_map.get(n2_name)

            if not n1:
                logger.warning(
                    f"Node '{n1_name}' not found, skipping connection"
                )
                continue
            if not n2:
                logger.warning(
                    f"Node '{n2_name}' not found, skipping connection"
                )
                continue

            try:
                (physical_dist, worst_latency, ig_dist, ig_factor) = (
                    self.calculate_ig_distance(n1, n2)
                )

                all_ig_distances.append(ig_dist)
                calculated_connections.append(
                    {
                        "n1": n1,
                        "n2": n2,
                        "physical_dist": physical_dist,
                        "worst_latency": worst_latency,
                        "ig_distance": ig_dist,
                        "ig_factor": ig_factor,
                    }
                )

                logger.info(f"Path: {n1.name} <-> {n2.name}")
                logger.info(
                    f"  > Physical Dist (KM): {physical_dist:.2f} km"
                )
                logger.info(
                    f"  > Worst Latency: {worst_latency:.1f}ms"
                )
                logger.info(
                    f"  > IG Factor (Terrain Multiplier): {ig_factor:.2f}x"
                )
                logger.info(
                    f"  > IG Virtual Effort (Distance): {ig_dist:.2f} units"
                )

            except ValueError as e:
                logger.error(f"Error calculating IG distance: {e}")
                continue

        if not calculated_connections:
            logger.error("No valid connections to plot")
            return

        max_ig_dist = (
            max(all_ig_distances) if all_ig_distances else 1.0
        )

        # Plot nodes and labels
        for name, node in node_map.items():
            is_user = node == self.user_node
            color = "#ff7f0e" if is_user else "#1f77b4"
            size = 200 if is_user else 150

            # Use Longitude (Lon) for X-axis and Elevation for Y-axis
            ax.scatter(
                node.lon,
                node.elevation,
                s=size,
                c=color,
                zorder=5,
                edgecolors="black",
            )

            latency_str = (
                f"{node.latency:.1f}ms"
                if node.latency is not None
                else "N/A"
            )
            ax.annotate(
                f"{node.name}\n({node.elevation}F | {latency_str})",
                (node.lon, node.elevation),
                textcoords="offset points",
                xytext=(0, 10),
                ha="center",
                fontsize=9,
                fontweight="bold" if is_user else "normal",
            )

        # Plot connections (IG Virtual Effort)
        for conn in calculated_connections:
            n1 = conn["n1"]
            n2 = conn["n2"]
            ig_distance = conn["ig_distance"]

            # Map IG Distance to line properties
            line_thickness = 2 + 10 * (ig_distance / max_ig_dist)

            # Line Color: Redder = Higher effort/resistance
            effort_ratio = ig_distance / max_ig_dist
            r = min(1.0, 0.5 + effort_ratio * 0.5)
            g = max(0.0, 1.0 - effort_ratio * 1.0)
            line_color = (r, g, 0.2)

            # Draw the line representing the virtual path
            ax.plot(
                [n1.lon, n2.lon],
                [n1.elevation, n2.elevation],
                color=line_color,
                linewidth=line_thickness,
                linestyle="-",
                alpha=0.8,
                zorder=3,
            )

            # Add label in the middle of the line segment
            mid_lon = (n1.lon + n2.lon) / 2
            mid_y = (n1.elevation + n2.elevation) / 2
            ax.text(
                mid_lon,
                mid_y,
                f"IG Effort: {ig_distance:.2f}",
                color="black",
                fontsize=8,
                bbox=dict(
                    facecolor="white",
                    alpha=0.7,
                    edgecolor="none",
                    boxstyle="round,pad=0.3",
                ),
                ha="center",
                va="center",
            )

        # Final plot settings
        plt.tight_layout()
        logger.info("Visualization complete. Displaying plot...")
        plt.show()

        logger.info(
            "Line thickness and color represent the IG Virtual Effort "
            "(terrain complexity and movement cost)."
        )


if __name__ == "__main__":
    # Create transformer instance
    transformer = IharaGrubbTransform(latency_base_ms=100.0)

    # Automatically detect and add user node
    try:
        user_node = transformer.add_user_node_auto(
            name="My Console (User)",
            elevation_floor=15.0,  # Estimated Floor Level
        )
        logger.info("User location automatically detected!")
    except RuntimeError:
        # Fallback to manual location if auto-detection fails
        logger.warning(
            "Auto-detection failed. Using fallback location. "
            "You may want to manually set your location."
        )
        user_node = transformer.add_node(
            name="My Console (User)",
            lat=37.7749,  # Fallback: San Francisco Latitude
            lon=-122.4194,  # Fallback: San Francisco Longitude
            elevation_floor=15,  # Estimated Floor Level
            ip_address="0.0.0.0",  # Not needed for ping
            is_user_node=True,
        )

    # Add target nodes
    transformer.add_node(
        "Cloudflare DNS (Global)",
        lat=37.7749,
        lon=-122.3941,
        elevation_floor=5,
        ip_address="1.1.1.1",
    )
    transformer.add_node(
        "Google DNS (NYC Area)",
        lat=40.7128,
        lon=-74.0060,
        elevation_floor=30,
        ip_address="8.8.8.8",
    )
    transformer.add_node(
        "OpenDNS (UK/Europe)",
        lat=51.5074,
        lon=0.1278,
        elevation_floor=10,
        ip_address="208.67.222.222",
    )

    # Define connections to test
    connections = [
        ("My Console (User)", "Cloudflare DNS (Global)"),
        ("My Console (User)", "Google DNS (NYC Area)"),
        ("My Console (User)", "OpenDNS (UK/Europe)"),
        ("Cloudflare DNS (Global)", "Google DNS (NYC Area)"),
    ]

    # Generate visualization
    transformer.plot_net(connections)

    logger.info("Visualization complete!")
