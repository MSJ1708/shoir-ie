import pulp

def optimize_supply_flow(demand_dict, capacity_dict, cost_matrix, penalty_cost=50):
    """
    MILP Model to find minimum cost fulfillment under real-time disruption constraints.
    """
    warehouses = list(capacity_dict.keys())
    demand_zones = list(demand_dict.keys())

    # Decision variables: Shipment quantities
    prob = pulp.LpProblem("AEGIS_Dynamic_ReRouting", pulp.LpMinimize)
    
    ship = pulp.LpVariable.dicts("Ship", ((w, d) for w in warehouses for d in demand_zones), lowBound=0, cat='Integer')
    unmet = pulp.LpVariable.dicts("Unmet", demand_zones, lowBound=0, cat='Integer')

    # Objective: Minimize sum of shipping costs + stockout penalty costs
    prob += (
        pulp.lpSum(ship[w, d] * cost_matrix[w][d] for w in warehouses for d in demand_zones) +
        pulp.lpSum(unmet[d] * penalty_cost for d in demand_zones)
    )

    # Supply Constraints
    for w in warehouses:
        prob += pulp.lpSum(ship[w, d] for d in demand_zones) <= capacity_dict[w]

    # Demand Constraints
    for d in demand_zones:
        prob += pulp.lpSum(ship[w, d] for w in warehouses) + unmet[d] == demand_dict[d]

    prob.solve(pulp.PULP_CBC_CMD(msg=False))

    results = {
        "status": pulp.LpStatus[prob.status],
        "total_cost": pulp.value(prob.objective),
        "allocations": {(w, d): ship[w, d].varValue for w in warehouses for d in demand_zones},
        "unmet_demand": {d: unmet[d].varValue for d in demand_zones}
    }
    return results