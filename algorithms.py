"""Core DSA implementations used by the Smart Warehouse project."""
import heapq

def dijkstra(graph, start, destination):
    """Return (shortest_distance, path) using Dijkstra's algorithm."""
    if start not in graph or destination not in graph:
        return float("inf"), []
    distances = {node: float("inf") for node in graph}
    previous = {}
    distances[start] = 0
    heap = [(0, start)]
    while heap:
        current_distance, node = heapq.heappop(heap)
        if current_distance != distances[node]:
            continue
        if node == destination:
            break
        for neighbor, weight in graph[node].items():
            candidate = current_distance + weight
            if candidate < distances[neighbor]:
                distances[neighbor] = candidate
                previous[neighbor] = node
                heapq.heappush(heap, (candidate, neighbor))
    if distances[destination] == float("inf"):
        return float("inf"), []
    path = []
    node = destination
    while node != start:
        path.append(node)
        node = previous[node]
    path.append(start)
    return distances[destination], list(reversed(path))

def priority_order_key(order):
    """Lower numeric priority is more urgent; older orders break ties."""
    return (int(order["priority"]), int(order["id"]))

def prioritize_orders(orders):
    """Return orders in priority order using a min-heap."""
    heap = []
    for order in orders:
        heapq.heappush(heap, (priority_order_key(order), order))
    return [heapq.heappop(heap)[1] for _ in range(len(heap))]

def greedy_pick_plan(items):
    """Sort requested products by warehouse aisle/location to reduce movement."""
    return sorted(items, key=lambda item: (item["location"], item["name"].lower()))

def greedy_vehicle_assignment(deliveries, vehicle_capacity):
    """First-Fit Decreasing assignment based on package weight."""
    remaining = []
    assignments = []
    for delivery in sorted(deliveries, key=lambda d: d["weight"], reverse=True):
        placed = False
        for index, used in enumerate(remaining):
            if used + delivery["weight"] <= vehicle_capacity:
                remaining[index] += delivery["weight"]
                assignments[index].append(delivery)
                placed = True
                break
        if not placed:
            remaining.append(delivery["weight"])
            assignments.append([delivery])
    return assignments


def smart_delivery_assignment(orders, vehicle_count, capacity_units, route_distance_fn):
    """Priority-aware First-Fit Decreasing assignment with route estimates.

    Each ordered product quantity is treated as one capacity unit because the
    prototype does not yet store physical package dimensions or weights.
    """
    eligible = [o for o in orders if o.get("status") != "Delivered" and not o.get("assigned_vehicle")]
    # Priority first, then larger loads first, then oldest/smallest order ID.
    eligible.sort(key=lambda o: (int(o["priority"]), -int(o["quantity"]), int(o["id"])))
    vehicles = [{"vehicle": f"V-{i+1:02d}", "used": 0, "orders": [], "destinations": set(), "route_km": 0.0}
                for i in range(max(1, int(vehicle_count)))]
    unassigned = []
    for order in eligible:
        load = int(order["quantity"])
        if load > capacity_units:
            unassigned.append({**order, "reason": f"Order load ({load}) exceeds vehicle capacity ({capacity_units})."})
            continue
        target = next((v for v in vehicles if v["used"] + load <= capacity_units), None)
        if target is None:
            unassigned.append({**order, "reason": "No remaining vehicle capacity."})
            continue
        distance = route_distance_fn(order["destination"])
        enriched = {**order, "route_km": distance}
        target["orders"].append(enriched)
        target["used"] += load
        target["destinations"].add(order["destination"])
    result = {}
    for vehicle in vehicles:
        if vehicle["orders"]:
            # A simple conservative estimate: sum of each assigned order's warehouse-to-zone route.
            vehicle["route_km"] = sum(o["route_km"] for o in vehicle["orders"])
            result[vehicle["vehicle"]] = vehicle
    return result, unassigned
