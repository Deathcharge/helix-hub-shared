"""
Entanglement Service
Implements entanglement visualization with proper animation transforms.
"""

import logging
import math
from datetime import UTC, datetime

from ..models.system import EntanglementVisualization

logger = logging.getLogger(__name__)


class EntanglementService:
    """Service for generating entanglement visualizations with proper animation transforms"""

    def __init__(self) -> None:
        """
        Initialize the EntanglementService's internal cache and timing configuration.

        Attributes:
            _visualization_cache (Dict[str, EntanglementVisualization]): In-memory cache mapping cache keys to generated visualizations.
            _cache_ttl (int): Time-to-live for cache entries in seconds.
            _last_cache_update (float): Timestamp of the last cache update (epoch seconds).
        """
        self._visualization_cache: dict[str, EntanglementVisualization] = {}
        self._cache_ttl = 60  # 60 seconds cache TTL
        self._last_cache_update = 0

    async def generate_visualization(self, visualization_type: str = "matrix") -> EntanglementVisualization:
        """
        Generate an entanglement visualization for the requested type and return its data and animation transforms.

        The method uses an internal time-bucketed cache and may return a cached visualization for the same type if requested within the service's cache TTL. Unknown visualization types fall back to the "matrix" visualization.

        Parameters:
            visualization_type (str): Visualization type to generate; one of "matrix", "graph", or "field". Defaults to "matrix".

        Returns:
            EntanglementVisualization: Visualization object containing data points and configuration including animation transforms for the requested type.
        """
        cache_key = f"{visualization_type}_{int(datetime.now(UTC).timestamp() // self._cache_ttl)}"

        # Check cache
        if cache_key in self._visualization_cache:
            logger.debug("Returning cached visualization: %s", visualization_type)
            return self._visualization_cache[cache_key]

        # Generate new visualization
        visualization = await self._generate_visualization_data(visualization_type)

        # Update cache
        self._visualization_cache[cache_key] = visualization
        self._last_cache_update = datetime.now(UTC).timestamp()

        return visualization

    async def _generate_visualization_data(self, visualization_type: str) -> EntanglementVisualization:
        """
        Selects and produces an entanglement visualization for the given type.

        Parameters:
            visualization_type (str): Desired visualization kind. Accepted values are "matrix", "graph", and "field"; any other value falls back to "matrix".

        Returns:
            EntanglementVisualization: A visualization object matching the requested type (or a matrix visualization if the type is unrecognized).
        """

        if visualization_type == "matrix":
            return await self._generate_matrix_visualization()
        elif visualization_type == "graph":
            return await self._generate_graph_visualization()
        elif visualization_type == "field":
            return await self._generate_field_visualization()
        else:
            # Default to matrix
            return await self._generate_matrix_visualization()

    async def _generate_matrix_visualization(self) -> EntanglementVisualization:
        """
        Produce a matrix-style entanglement visualization.

        Creates a 10x10 grid excluding diagonal entries; each data point is a mapping with keys:
        - `x` (int): row index,
        - `y` (int): column index,
        - `value` (float): entanglement value between 0.1 and 0.9 (rounded to three decimals),
        - `intensity` (float): derived display intensity (rounded).

        Returns:
            EntanglementVisualization: Visualization with type `"matrix"`, a list of data points as described above, and a `config` dictionary containing dimensions, color scheme, and animation settings.
        """
        data_points = []

        # Load actual UCF state for deterministic values
        try:
            from apps.backend.coordination_engine import load_ucf_state

            ucf = load_ucf_state()
            base = ucf.get("harmony", 0.5)
        except (ImportError, ModuleNotFoundError) as e:
            logger.debug("UCF state module not available: %s", e)
            base = 0.5
        except (KeyError, TypeError) as e:
            logger.debug("UCF state missing harmony value: %s", e)
            base = 0.5
        except Exception as e:
            logger.warning("Failed to load UCF state for entanglement matrix: %s", e)
            base = 0.5

        # Generate 10x10 matrix with values derived from UCF harmony
        for i in range(10):
            for j in range(10):
                if i != j:
                    distance = abs(i - j) / 9.0
                    entanglement = base * (1.0 - distance * 0.6)
                    data_points.append(
                        {
                            "x": i,
                            "y": j,
                            "value": round(entanglement, 3),
                            "intensity": round(entanglement * 100, 1),
                        }
                    )

        config = {
            "type": "matrix",
            "dimensions": [10, 10],
            "colorScheme": "plasma",
            "animation": {"enabled": True, "duration": 2000, "easing": "easeInOut"},
        }

        return EntanglementVisualization(type="matrix", data=data_points, config=config)

    async def _generate_graph_visualization(self) -> EntanglementVisualization:
        """
        Create a graph-style entanglement visualization.

        The returned visualization contains particle nodes with position and size attributes and edges representing entanglement connections with strength and display width. Nodes serve as graph vertices and edges encode pairwise entanglement relationships suitable for force/physics-based rendering.

        Returns:
            EntanglementVisualization: Visualization object with `type` set to "graph", `data` containing node and edge entries, and `config` for physics and interaction settings.
        """
        nodes = []
        edges = []

        # Load UCF state for deterministic layout
        try:
            from apps.backend.coordination_engine import load_ucf_state

            ucf = load_ucf_state()
            coherence = ucf.get("resilience", 0.5)
            harmony = ucf.get("harmony", 0.5)
        except (ImportError, ModuleNotFoundError) as e:
            logger.debug("UCF state module not available: %s", e)
            coherence = 0.5
            harmony = 0.5
        except (KeyError, TypeError) as e:
            logger.debug("UCF state missing required values: %s", e)
            coherence = 0.5
            harmony = 0.5
        except Exception as e:
            logger.warning("Failed to load UCF state for network nodes: %s", e)
            coherence = 0.5
            harmony = 0.5

        # Generate nodes with deterministic positions
        num_nodes = 8
        for i in range(num_nodes):
            angle = (2 * math.pi * i) / num_nodes
            radius = 60 * coherence
            nodes.append(
                {
                    "id": f"particle_{i}",
                    "label": f"P{i}",
                    "x": round(radius * math.cos(angle), 2),
                    "y": round(radius * math.sin(angle), 2),
                    "size": round(10 + harmony * 20, 1),
                }
            )

        # Generate edges based on coherence threshold
        for i in range(num_nodes):
            for j in range(i + 1, num_nodes):
                entanglement = harmony * (1.0 - abs(i - j) / num_nodes)
                if entanglement > 0.3:  # Only show meaningful connections
                    edges.append(
                        {
                            "source": f"particle_{i}",
                            "target": f"particle_{j}",
                            "strength": round(entanglement, 3),
                            "width": max(1, int(entanglement * 5)),
                        }
                    )

        data_points = nodes + edges

        config = {
            "type": "graph",
            "physics": {"enabled": True, "stabilization": {"iterations": 100}},
            "interaction": {"hover": True, "select": True},
        }

        return EntanglementVisualization(type="graph", data=data_points, config=config)

    async def _generate_field_visualization(self) -> EntanglementVisualization:
        """
        Create a field-style entanglement visualization sampled on a regular 11x11 grid.

        Each data point contains spatial coordinates and system properties: `x`, `y` (grid coordinates), `intensity` (clamped to the range 0 to 1 and rounded to three decimals), and `phase` (radians in [0, 2π)). The returned visualization also includes a `config` dict describing interpolation, colormap, and contour settings.

        Returns:
            EntanglementVisualization: A visualization object with type "field", `data` as a list of point dictionaries, and `config` for rendering.
        """
        data_points = []

        # Load UCF state for field intensity
        try:
            from apps.backend.coordination_engine import load_ucf_state

            ucf = load_ucf_state()
            throughput = ucf.get("throughput", 0.5)
            focus = ucf.get("focus", 0.5)
        except (ImportError, ModuleNotFoundError) as e:
            logger.debug("UCF state module not available: %s", e)
            throughput = 0.5
            focus = 0.5
        except (KeyError, TypeError) as e:
            logger.debug("UCF state missing required values: %s", e)
            throughput = 0.5
            focus = 0.5
        except Exception as e:
            logger.warning("Failed to load UCF state for field visualization: %s", e)
            throughput = 0.5
            focus = 0.5

        # Generate field data points based on UCF throughput/focus
        for x in range(-50, 51, 10):
            for y in range(-50, 51, 10):
                distance = math.sqrt(x * x + y * y)
                intensity = max(0, throughput * (1.0 - (distance / 70)))
                intensity = max(0, min(1, intensity))

                # Phase derived from position and focus
                phase = math.atan2(y, x + 0.001) + focus * math.pi

                data_points.append(
                    {
                        "x": x,
                        "y": y,
                        "intensity": round(intensity, 3),
                        "phase": round(phase % (2 * math.pi), 3),
                    }
                )

        config = {
            "type": "field",
            "interpolation": "bilinear",
            "colormap": "viridis",
            "contour": {"enabled": True, "levels": 10},
        }

        return EntanglementVisualization(type="field", data=data_points, config=config)

    async def get_visualization_types(self) -> list[str]:
        """Get available visualization types"""
        return ["matrix", "graph", "field"]

    async def clear_cache(self) -> int:
        """
        Clear all cached entanglement visualizations and reset the cache timestamp.

        Removes every entry from the in-memory visualization cache and sets the last cache update timestamp to zero.

        Returns:
                int: The number of cache entries that were removed.
        """
        cleared_count = len(self._visualization_cache)
        self._visualization_cache.clear()
        self._last_cache_update = 0
        logger.info("Cleared %s cached visualizations", cleared_count)
        return cleared_count
