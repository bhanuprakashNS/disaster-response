# app/skills.py

import random

# --- 1. Generic & Reusable Skill: WeatherService ---

class WeatherService:
    """A generic, reusable service for looking up weather and atmospheric conditions."""
    
    def __init__(self):
        self.mock_conditions = ["Rainy", "Stormy", "Clear", "Overcast", "Windy"]

    def get_weather(self, location: str) -> dict:
        """Fetches the weather conditions, wind speed, and temperature for a location."""
        loc_lower = location.lower()
        if "sector" in loc_lower or "zone" in loc_lower:
            # Deterministic mock weather based on name length for demo stability
            idx = len(location) % len(self.mock_conditions)
            condition = self.mock_conditions[idx]
            temp = 15 + (len(location) % 15)
            wind = 10 + (len(location) % 30)
        else:
            condition = "Stormy"
            temp = 12
            wind = 45
            
        return {
            "location": location,
            "condition": condition,
            "temperature_c": temp,
            "wind_speed_kmh": wind,
            "warnings": ["Severe Storm Warning"] if condition == "Stormy" or wind > 30 else []
        }


# --- 2. Project-Specific Skill: InventoryManager ---

class InventoryManager:
    """Specific database manager to handle emergency relief inventory stock levels."""
    
    def __init__(self):
        # Simulated database of available relief items in warehouses
        self.inventory = {
            "water": 5000,          # liters
            "food": 3000,           # meals
            "medical_kits": 250,    # units
            "tents": 120,           # units
            "blankets": 1500,       # units
        }

    def check_stock(self, item_name: str) -> dict:
        """Checks the current stock levels of a specific relief resource."""
        normalized_name = item_name.strip().lower().replace(" ", "_")
        # Handle plurals
        if normalized_name.endswith("s") and normalized_name not in self.inventory:
            singular = normalized_name[:-1]
            if singular in self.inventory:
                normalized_name = singular

        if normalized_name in self.inventory:
            return {
                "item": item_name,
                "available": self.inventory[normalized_name],
                "status": "IN_STOCK" if self.inventory[normalized_name] > 50 else "LOW_STOCK"
            }
        return {
            "item": item_name,
            "available": 0,
            "status": "OUT_OF_STOCK"
        }

    def reserve_items(self, item_name: str, quantity: int) -> dict:
        """Deducts stock for dispatch if available."""
        normalized_name = item_name.strip().lower().replace(" ", "_")
        if normalized_name.endswith("s") and normalized_name not in self.inventory:
            singular = normalized_name[:-1]
            if singular in self.inventory:
                normalized_name = singular

        if normalized_name in self.inventory:
            current_stock = self.inventory[normalized_name]
            if current_stock >= quantity:
                self.inventory[normalized_name] -= quantity
                return {
                    "item": item_name,
                    "allocated": quantity,
                    "remaining": self.inventory[normalized_name],
                    "success": True
                }
            else:
                return {
                    "item": item_name,
                    "allocated": 0,
                    "remaining": current_stock,
                    "success": False,
                    "message": f"Insufficient stock. Requested {quantity}, only {current_stock} available."
                }
        return {
            "item": item_name,
            "allocated": 0,
            "remaining": 0,
            "success": False,
            "message": "Item not found in inventory registry."
        }


# --- 3. Project-Specific Skill: RoadStatusService ---

class RoadStatusService:
    """Specific logistics service for tracking road blockages and transport route safety."""
    
    def __init__(self):
        # Simulated road status database mapping areas to accessibility conditions
        self.routes = {
            "sector 7-b": {"status": "OPEN", "condition": "Wet roads, clear flow"},
            "sector 9": {"status": "BLOCKED", "condition": "Landslide at main bridge"},
            "downtown": {"status": "OPEN", "condition": "Heavy traffic, accessible"},
            "coastal road": {"status": "RESTRICTED", "condition": "Flooded lanes, high-clearance vehicles only"}
        }

    def get_route_status(self, destination: str) -> dict:
        """Determines if the routes to a disaster area are open or obstructed."""
        dest_lower = destination.strip().lower()
        
        # Match substring
        matched_key = None
        for key in self.routes:
            if key in dest_lower:
                matched_key = key
                break
                
        if matched_key:
            route_info = self.routes[matched_key]
            return {
                "destination": destination,
                "status": route_info["status"],
                "details": route_info["condition"]
            }
        
        # Default fallback: assume restricted if unrecognized sector name is used
        return {
            "destination": destination,
            "status": "RESTRICTED",
            "details": "Unverified route conditions. Caution recommended."
        }
