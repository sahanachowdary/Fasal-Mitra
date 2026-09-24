"""Fasal Mitra: offline teaching prototype. Python standard library only."""
import csv
import math
import sqlite3
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent
# Fictional listings. Distances are scenario inputs, not GPS measurements.
BUYERS = [
    ('Local vegetable shop', 'Tomato', 2, 0.5, 12, 300, 60),
    ('Demo FPO', 'Tomato', 8, 2, 17, 1000, 200),
    ('City wholesale buyer', 'Tomato', 14, 5, 20, 2000, 350),
    ('Leafy vegetables shop', 'Spinach', 3, 0.5, 18, 150, 70),
    ('Demo greens collective', 'Spinach', 9, 2, 24, 600, 200),
    ('Onion trader', 'Onion', 5, 1, 22, 2000, 120),
    ('Onion wholesale buyer', 'Onion', 12, 4, 26, 3000, 300),
]
STORES = [('Demo Cool Room A', 6, 1, 800, 2, 150),
          ('Demo Cool Room B', 12, 2, 1500, 1.5, 250)]


def connect(path=None):
    db = sqlite3.connect(path or ROOT / 'sales.db')
    db.execute('''CREATE TABLE IF NOT EXISTS sales
        (id INTEGER PRIMARY KEY, created TEXT, farmer TEXT, crop TEXT,
         kg REAL, buyer TEXT, gross REAL, transport REAL, net REAL)''')
    db.commit()
    return db


def number(value, label, low, high):
    try:
        value = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label}: enter a number.')
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f'{label}: use a value from {low} to {high}.')
    return value


def match(crop, kg, temperature, age, radius, baseline):
    """Filter capacity/distance; rank on deadline feasibility then net income.

    Time budgets are deliberately invented for demo scenarios. They are NOT
    shelf life, food safety advice, or an agricultural prediction model.
    """
    if crop not in ('Tomato', 'Spinach', 'Onion'):
        raise ValueError('Select Tomato, Spinach or Onion.')
    kg = number(kg, 'Quantity (kg)', 1, 10000)
    temperature = number(temperature, 'Temperature', 0, 50)
    age = number(age, 'Hours since harvest', 0, 240)
    radius = number(radius, 'Radius (km)', 1, 50)
    baseline = number(baseline, 'Local offer per kg', 0, 1000)
    budget = {'Tomato': 8, 'Spinach': 4, 'Onion': 48}[crop]
    factor = 1.5 if temperature >= 35 else 1.2 if temperature >= 30 else 1
    remaining = max(0, budget / factor - age)
    urgency = 'HIGH' if remaining <= 2 else 'MEDIUM' if remaining <= 5 else 'LOW'
    results = []
    for name, item, distance, eta, price, capacity, transport in BUYERS:
        if item == crop and distance <= radius and capacity >= kg:
            gross = round(kg * price, 2)
            net = round(gross - transport, 2)
            results.append(dict(name=name, distance=distance, eta=eta, price=price,
                                gross=gross, transport=transport, net=net,
                                gain=round(net - kg * baseline, 2),
                                eligible=eta < remaining))
    results.sort(key=lambda r: (not r['eligible'], -r['net'], r['eta']))
    stores = []
    for name, distance, eta, capacity, rate, transport in STORES:
        if distance <= radius and capacity >= kg:
            stores.append(dict(name=name, distance=distance, eta=eta,
                               cost=round(kg * rate + transport, 2),
                               eligible=eta < remaining))
    stores.sort(key=lambda s: (not s['eligible'], s['cost']))
    return dict(crop=crop, kg=kg, remaining=remaining, urgency=urgency,
                baseline=round(kg * baseline, 2), buyers=results, stores=stores)


def save_sale(db, farmer, result, buyer):
    if not farmer.strip():
        raise ValueError('Enter the farmer name.')
    if not buyer['eligible']:
        raise ValueError('This buyer misses the demo time window. Choose another.')
    with db:
        cursor = db.execute('INSERT INTO sales VALUES(NULL,?,?,?,?,?,?,?,?)',
            (datetime.now().isoformat(timespec='seconds'), farmer.strip(), result['crop'],
             result['kg'], buyer['name'], buyer['gross'], buyer['transport'], buyer['net']))
    return cursor.lastrowid


