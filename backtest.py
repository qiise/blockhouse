'''
Smart Order Router Backtest
Implementation of Cont-Kukanov allocator with parameter tuning and a comparison with three baselines
'''
import pandas as pd
import numpy as np
import json


'''
DATA PREPROCESSING

Process the raw market data into venue snapshots

Args:
    file_name (str): Path to the CSV file containing market data

Returns:
    dict: Snapshots of best ask prices/sizes per venue, keyed by timestamp (ts_event)

'''
def process_data(file_name):
    df = pd.read_csv(file_name)
    df = df.sort_values('ts_event') #sort by ts_event
    df = df.groupby(['ts_event', 'publisher_id']).first().reset_index()
    snapshot = {}
    for event, group in df.groupby('ts_event'):
        venues = []
        for _, row in group.iterrows():
            venue={
                'ask_size' : row['ask_sz_00'],
                'display_size': row['ask_px_00'],
                'fee' : 0.003, #use a fixed fee/rebate for simplicity
                'rebate': 0.002
            }
            venues.append(venue)
        snapshot[event] = venues
    return snapshot

'''
CONT-KUKANOV ALLOCATOR

Computes optimal order to split across venues using the Cont-Kukanov model

Args:
    order_size (int): total shares to execute
    venues (list): list of venue dictionaries
    lambda_over (float): penalty for overfilling
    lambda_under (float): penality for underfilling
    queue_risk (float): queue risk penality coefficient

Returns:
    tuple (best_split, best_cost):
        best_split: list of shares to route to each venue
        best_cost: estimated total cost of allocation
'''
def allocate(order_size, venues, lambda_over, lambda_under, queue_risk):
    step = 100
    splits = [[]]
    for v in range(len(venues)):
        new_splits = []
        for alloc in splits:
            used = sum(alloc)
            
            max_v = min(order_size-used, venues[v]['ask_size'])
            for q in range(0,max_v+step, step):
                new_splits.append(alloc + [q] )
        splits = new_splits

    best_cost = float('inf')
    best_split = []
    for alloc in splits:
        if sum(alloc) != order_size:
            continue
        cost = compute_cost(alloc, venues, order_size, lambda_over, lambda_under, queue_risk)
        if cost < best_cost:
            best_cost = cost
            best_split = alloc
    return best_split, best_cost
"""
    Calculate total execution cost for a given order split.
    
    Args:
        split (list): Shares allocated to each venue.
        venues (list): Venue dictionaries with market data.
        order_size (int): Target execution size.
        lambda_o (float): Overfill penalty.
        lambda_u (float): Underfill penalty.
        theta (float): Queue risk penalty.
    
    Returns:
        float: Total cost including fees, rebates, and penalties.
"""
def compute_cost(split, venues, order_size, lambda_o, lambda_u, theta):
    executed = 0
    cash_spent = 0
    for i in range(len(venues)):
        exe = min(split[i], venues[i]['ask_size'])
        executed += exe
        cash_spent += exe*venues([i]['display_size'])
        maker_rebate = max(split[i] - exe, 0)*venues[i]['rebate']
        cash_spent -= maker_rebate
    
    underfill = max(order_size - executed, 0)
    overfill = max(executed-order_size, 0)
    risk_pen = theta*(underfill + overfill)
    cost_pen = lambda_u * underfill + lambda_o*overfill
    return cash_spent + risk_pen + cost_pen

"""
BACKTEST

    Simulate order execution over time using the allocator.
    
    Args:
        snapshots (dict): Preprocessed market data.
        lambda_over (float): Overfill penalty.
        lambda_under (float): Underfill penalty.
        queue_risk (float): Queue risk penalty.
    
    Returns:
        tuple: (total_cash, average_price) where:
               - total_cash: Total money spent.
               - avg_price: Average execution price (or None if unfilled).
"""
def backtest(snapshots, lambda_over, lambda_under, queue_risk):
    snapshots = sorted(snapshots.items())
    remaining = 5000
    total_cash = 0
    for event, venues in snapshots:
        if remaining <=0:
            break
        alloc, _ = allocate(remaining, venues, lambda_over, lambda_under, queue_risk) #Determine splits at each timestamp
        executed = 0
        cash = 0
        for i in range(0, len(venues)): #identify the best performing set
            exe = min(alloc[i], venues[i]['ask_size'])
            cash += exe*(venues[i]['display_size'] + venues[i]['fee'])
            cash -= max(alloc[i] - exe, 0)* venues[i]['rebate']
            executed += exe
        total_cash += cash
        remaining -= executed
    if remaining <= 0:
        average_price = total_cash/5000
    else:
        average_price = None
    return total_cash, average_price

#-------------------------------
# BASELINE STRATEGIES
#-------------------------------

#best ask strategy
def baseline1(snapshots):
    snapshots = sorted(snapshots.items())
    remaining = 5000
    total_cash = 0
    for event, venues in snapshots:
        if remaining <=0:
            break
        best_venue = min(venues, key=lambda v: v['display_size'])
        exe = min(remaining, best_venue['ask_size'])
        total_cash += exe*(best_venue['display_size'] + best_venue['fee'])
        remaining -= exe
    average_price = total_cash/5000
    return total_cash, average_price

#twap baseline strategy
def baseline2(snapshots):
    snapshots = sorted(snapshots.items())
    total_time = 540
    interval=60
    num_buckets = total_time//interval
    buckets = [[] for _ in range(num_buckets)]
    for event, venues in snapshots:
        bucket = (event - min(snapshots, key = lambda x: x[0])[0]) //interval
        if bucket < num_buckets:
            buckets[bucket].append((event, venues))
    total_cash = 0
    remaining = 5000
    per_bucket = 5000/num_buckets
    for bucket in buckets:
        if not bucket:
            continue
        shares_per_step = per_bucket /len(bucket)

        for event, venues in bucket:
            if remaining <= 0:
                break
            exe = min(shares_per_step, remaining)
            best_venue = min(venues, key=lambda v: v['display_size'])
            exe_venue = min(exe, best_venue['ask_size'])
            total_cash += exe_venue * (best_venue['display_size'] + best_venue['fee'])
            remaining -= exe_venue
        
    avg_price = total_cash/5000
    return total_cash, avg_price

#vwap baseline strategy
def baseline3(snapshots):
    snapshots = sorted(snapshots.items())
    remaining = 5000
    total_cash = 0

    for event, venues in snapshots:
        if remaining <= 0:
            break
        total_size = sum(v['ask_size'] for v in venues)
        if total_size ==0:
            continue

        alloc = [remaining *v['ask_size']/total_size for v in venues]
        executed = 0
        cash = 0
        for i in range(0, len(venues)):
            exe = min(alloc[i], venues[i]['ask_size'])
            cash += exe*(venues[i]['display_size'] + venues[i]['fee'])
            executed +=exe
        total_cash +=cash
        remaining -=executed
    
    average_price = total_cash/5000
    return total_cash, average_price


#-------------------------------
# MAIN
#-------------------------------


def main():
    snapshots = process_data('LL_day.csv')

    #parameter grid
    lambda_over = [0.0, 0.01, 0.05]
    lambda_under = [0.01, 0.05, 0.1]
    queue_risk = [0.0, 0.001, 0.005]

    #grid search to find optimal parameters
    best_cost = float('inf')
    best_params = {}

    for i in lambda_over:
        for j in lambda_under:
            for theta in queue_risk:
                total_cash, average_price = backtest(snapshots, lambda_over, lambda_under, queue_risk)
                if average_price is not None and total_cash < best_cost:
                    best_cost = total_cash

                    best_params = {
                        'lambda_over': i,
                        'lambda_under': j,
                        'queue_risk': theta,
                        'cash_spent': total_cash,
                        "average_price": average_price

                    }
    
    #comparing to output from the three baselines

    cash1, avg1 = baseline1(snapshots)
    cash2, avg2 = baseline2(snapshots)
    cash3, avg3 = baseline3(snapshots)


    #calculating savings of my method vs baseline in basis points (bp = 0.01%)

    savings1 = (avg1 - best_params['avg_price'])/avg1 * 10000 if avg1 != 0 else 0
    savings2 = (avg2 - best_params['avg_price'])/avg2 * 10000 if avg2 != 0 else 0
    savings3 = (avg3 - best_params['avg_price'])/avg3 * 10000 if avg3 != 0 else 0

    #output for json file
    output = {
        'best_params': {
            'lambda_over': best_params['lambda_over'],
            'lambda_under': best_params['lambda_under'],
            'theta_queue': best_params['theta_queue'],
            'cash_spent': best_params['cash_spent'],
            'avg_price': best_params['avg_price']
        },
        'baselines': {
            'best_ask': {'cash_spent': cash1, 'avg_price': avg1},
            'twap': {'cash_spent': cash2, 'avg_price': avg2},
            'vwap': {'cash_spent': cash3, 'avg_price': avg3}
        },
        'savings_bps': {
            'vs_best_ask': savings1,
            'vs_twap': savings2,
            'vs_vwap': savings3
        }
    }


    print(json.dumps(output, indent =2))


if __name__ == '__main__':
    main()



                      
                  
