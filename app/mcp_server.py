# app/mcp_server.py

from mcp.server.fastmcp import FastMCP
from app.skills import WeatherService, InventoryManager, RoadStatusService

# Initialize the FastMCP server
mcp = FastMCP("DisasterResponseTools")

# Instantiate our Skills services
weather_service = WeatherService()
inventory_manager = InventoryManager()
road_status_service = RoadStatusService()

@mcp.tool()
def get_weather_conditions(location: str) -> str:
    """Fetches the current weather conditions, wind speed, and temperature for a given disaster area.
    
    Args:
        location: The name or coordinates of the disaster area.
    """
    result = weather_service.get_weather(location)
    warnings = f" Warnings: {', '.join(result['warnings'])}" if result["warnings"] else ""
    return (
        f"Weather for {result['location']}: {result['condition']}. "
        f"Temp: {result['temperature_c']}C. Wind: {result['wind_speed_kmh']} km/h.{warnings}"
    )

@mcp.tool()
def check_relief_inventory(item_name: str) -> str:
    """Checks the current stock levels of a specific relief resource (water, food, medical_kits, tents, blankets).
    
    Args:
        item_name: The name of the item to check.
    """
    result = inventory_manager.check_stock(item_name)
    return f"Inventory Check: {result['item']} is {result['status']} (Available: {result['available']})."

@mcp.tool()
def check_route_status(destination: str) -> str:
    """Checks if the roads and transport routes to a disaster area are open, restricted, or blocked.
    
    Args:
        destination: The name or coordinates of the disaster area.
    """
    result = road_status_service.get_route_status(destination)
    return f"Route Status for {result['destination']}: {result['status']}. Details: {result['details']}."

if __name__ == "__main__":
    mcp.run()
