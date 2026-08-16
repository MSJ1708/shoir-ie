import simpy
import random
import pandas as pd

class SupplyChainEnv:
    def __init__(self, env, num_warehouses=2, initial_stock=100):
        self.env = env
        self.warehouses = {f"WH_{i+1}": initial_stock for i in range(num_warehouses)}
        self.unfulfilled_demand = 0
        self.total_fulfilled = 0
        self.logs = []

    def log_event(self, event_type, details):
        self.logs.append({
            "Time": self.env.now,
            "Event": event_type,
            "Details": str(details),
            "Stock_WH1": self.warehouses.get("WH_1", 0),
            "Stock_WH2": self.warehouses.get("WH_2", 0),
            "Unfulfilled": self.unfulfilled_demand
        })

    def demand_generator(self, warehouse_id, arrival_rate=2):
        while True:
            # Stochastic inter-arrival times
            yield self.env.timeout(random.expovariate(1.0 / arrival_rate))
            order_qty = random.randint(5, 25)
            
            if self.warehouses[warehouse_id] >= order_qty:
                self.warehouses[warehouse_id] -= order_qty
                self.total_fulfilled += order_qty
                self.log_event("ORDER_FULFILLED", f"{order_qty} units from {warehouse_id}")
            else:
                shortage = order_qty - self.warehouses[warehouse_id]
                self.total_fulfilled += self.warehouses[warehouse_id]
                self.warehouses[warehouse_id] = 0
                self.unfulfilled_demand += shortage
                self.log_event("STOCKOUT_DISRUPTION", f"Shortage of {shortage} units at {warehouse_id}")

    def replenish_process(self, warehouse_id, qty, lead_time_mean=5):
        # Simulated variable supply chain lead time
        actual_lead_time = max(1, random.normalvariate(lead_time_mean, 1.5))
        yield self.env.timeout(actual_lead_time)
        self.warehouses[warehouse_id] += qty
        self.log_event("REPLENISHMENT_ARRIVED", f"{qty} units added to {warehouse_id}")


def run_simulation(simulation_time=50, wh1_stock=100, wh2_stock=100):
    env = simpy.Environment()
    sc = SupplyChainEnv(env, initial_stock=100)
    sc.warehouses["WH_1"] = wh1_stock
    sc.warehouses["WH_2"] = wh2_stock

    env.process(sc.demand_generator("WH_1", arrival_rate=3))
    env.process(sc.demand_generator("WH_2", arrival_rate=2))
    
    env.run(until=simulation_time)
    return pd.DataFrame(sc.logs), sc