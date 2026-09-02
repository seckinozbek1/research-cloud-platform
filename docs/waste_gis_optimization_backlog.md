# Karşıyaka Waste GIS — Deferred Operations & Optimization Work

This document records the current decision-system architecture and the
operations-research work deliberately deferred until after the first MLOps pass.

## Current architecture checkpoint

The municipal waste case is a brownfield optimization problem.

The system does not design a waste network from scratch. It starts from an
existing synthetic municipal infrastructure anchored to real Karşıyaka spatial
data.

Current substrate:

- 100 m demand grid
- real Karşıyaka administrative boundary
- real OSM road network
- WorldPop 2025 population
- OSM activity / POI context
- 1,200 fixed physical bins
- 858 collection points
- 3 fixed hubs
- 12 trucks
  - 6 small trucks
  - 6 large trucks
- explicit bin types and capacities
- explicit pickup service times
- vehicle-specific operational speed limits
- human shift constraints
- lunch and short breaks
- preparation and closeout time
- crew sickness / leave / late starts
- scheduled maintenance
- minor vehicle faults
- route-time vehicle breakdowns
- normal, rush-hour, and disrupted traffic states
- synthetic roadworks, temporary closures, event congestion, and rain effects

All permanent collection points and hubs are snapped to the largest strongly
connected component of the driving network.

Normal and rush scenarios currently have zero permanently unreachable
collection points. A temporary road closure can still make a point unreachable
during a disrupted scenario.

## Demand model role

The ML model is a demand-forecast component of a larger decision system.

It should forecast exogenous waste generation rather than directly decide:

- pickup frequency
- bin capacity
- bin relocation
- routes

These operational variables belong to the downstream optimization layer.

Conceptually:

data + spatial context
→ waste-demand forecast
→ utility scheduler / optimizer
→ municipal operational plan

## Utility-service principle

Waste collection is treated as a public utility obligation, not as an optional
set of jobs from which the optimizer may choose only the profitable ones.

Current synthetic service policy:

- priority points: maximum 24-hour service interval
- standard points: maximum 48-hour service interval
- imminent overflow: same-day mandatory priority
- temporary physical inaccessibility: explicit service exception
- reachable mandatory points must not be silently dropped for route efficiency

Human working conditions remain hard constraints. Utility compliance must not be
achieved by removing breaks or extending workers beyond safe scheduled hours.

If the available fleet and crews cannot satisfy the service obligation, the
correct result is that resource capacity is insufficient.

## Current simulation checkpoint

Original heuristic baseline over 30 days:

- generated waste: about 10,381 tonnes
- collected waste: about 9,893 tonnes
- final backlog: about 488.5 tonnes
- final overflow: about 158.9 tonnes
- 11,998 pickup events
- 1,378 unload events
- 6 encountered breakdowns

Utility-service scheduler over 30 days:

- generated waste: about 10,382 tonnes
- collected waste: about 10,161 tonnes
- final backlog: about 220.8 tonnes
- final overflow: about 42.0 tonnes
- 11,645 pickup events
- 1,225 unload events
- 6 encountered breakdowns

The utility scheduler therefore improved service while performing fewer pickup
and unload events, but detailed utility-compliance diagnostics are intentionally
deferred.

## Deferred scheduled analyses

Do not run these during the first MLOps pass.

Later analyses should include:

1. Utility SLA compliance
   - mean and worst daily compliance
   - mandatory services missed
   - temporary reachability exceptions
   - 24-hour vs 48-hour service-class compliance

2. Service fairness
   - points never or rarely serviced
   - maximum consecutive missed-service days
   - geographic inequity
   - neighborhood/service-class disparities

3. Overflow diagnostics
   - persistent overflow points
   - overflow concentration
   - capacity-pressure hotspots
   - demand vs installed capacity

4. Resource diagnostics
   - driving time
   - pickup/service time
   - unloading time
   - break and shift constraints
   - vehicle downtime
   - crew unavailability
   - breakdown impact

5. Brownfield bin optimization
   - fixed total bin stock
   - small/medium/large bin composition
   - limited relocation
   - resident/activity access distance
   - overflow reduction
   - relocation cost

6. Pickup-frequency optimization
   - service-class requirements
   - predicted fill rates
   - utility deadlines
   - adaptive frequency

7. Hub and fleet assignment
   - vehicle type suitability
   - payload capacity
   - hub allocation
   - workload balancing

8. Traffic-aware routing / VRP
   - hub → point → point → ... → hub
   - capacity-triggered unload trips
   - time-dependent road costs
   - road closures
   - roadworks
   - events
   - weather

9. Dynamic re-optimization
   - vehicle breakdown during route
   - unexpected crew loss
   - new road closure
   - abnormal waste generation
   - emergency reassignment

10. Possible later RL research extension
    - only after deterministic constrained optimization
    - utility and worker-safety obligations remain hard constraints
    - RL must not learn to violate public-service guarantees for reward

## Scope decision

The first MLOps pass now returns to the ML lifecycle:

data
→ training
→ evaluation
→ registry
→ deployment
→ monitoring
→ retraining

Do not expand the operations-research layer further until this MLOps lifecycle
has been completed.
