import unittest
from optimizer import WarehouseGraph, shortest_path, optimize_pick_route, pack_orders, assign_vehicles, forecast_demand

class OptimizerTests(unittest.TestCase):
    def setUp(self):
        self.graph = WarehouseGraph()

    def test_dijkstra_path(self):
        path, distance = shortest_path(self.graph, "PACK", "A1")
        self.assertEqual(path[0], "PACK")
        self.assertEqual(path[-1], "A1")
        self.assertAlmostEqual(distance, 4.0)

    def test_pick_route_ends_at_packing(self):
        route, distance = optimize_pick_route(self.graph, "PACK", ["A1", "B2"], "PACK")
        self.assertEqual(route[0], "PACK")
        self.assertEqual(route[-1], "PACK")
        self.assertGreater(distance, 0)

    def test_knapsack_respects_capacity(self):
        items = [
            {"name": "A", "weight": 5, "value": 100},
            {"name": "B", "weight": 8, "value": 150},
            {"name": "C", "weight": 3, "value": 80},
        ]
        chosen, weight, value = pack_orders(items, 8)
        self.assertLessEqual(weight, 8)
        self.assertGreater(value, 0)

    def test_vehicle_assignment(self):
        result = assign_vehicles([15, 20, 10], [30, 20])
        self.assertEqual(sum(len(v["customers"]) for v in result), 3)

    def test_forecast(self):
        self.assertEqual(forecast_demand([10, 20, 30], 2), [20.0, 23.333333333333332])

if __name__ == "__main__":
    unittest.main()
