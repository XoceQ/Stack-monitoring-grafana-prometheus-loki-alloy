#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fake log generator.

Emits realistic-looking structured logs from several simulated business
components (auth, orders, payments, ...) so there is always something to
explore in Grafana/Loki. Every few minutes it simulates a short incident
(a burst of errors in one component) to make the log panels more interesting.
"""

import logging
import random
import threading
import time
import uuid

COMPONENTS = ['auth', 'orders', 'payments', 'inventory', 'notifications', 'search']
METHODS = ['GET', 'POST', 'PUT', 'DELETE']
REGIONS = ['us-east-1', 'eu-west-1', 'sa-east-1']
PRODUCTS = ['laptop', 'keyboard', 'monitor', 'headphones', 'mouse', 'webcam']


def _user_id():
    return f"user_{random.randint(1000, 9999)}"


def _ip_address():
    return f"10.0.{random.randint(0, 255)}.{random.randint(1, 254)}"


def _request_fields(component, endpoint, method=None, status_code=200, duration=None):
    return {
        'component': component,
        'request_id': f"req_{uuid.uuid4().hex[:12]}",
        'user_id': _user_id(),
        'ip_address': _ip_address(),
        'method': method or random.choice(METHODS),
        'endpoint': endpoint,
        'status_code': status_code,
        'duration': duration if duration is not None else round(random.uniform(0.01, 0.4), 3),
        'region': random.choice(REGIONS),
        'operation': 'fake_log',
    }


# Each scenario returns (level, message, extra_fields)
def _user_login():
    return logging.INFO, "User logged in", _request_fields('auth', '/api/login', 'POST')


def _user_logout():
    return logging.INFO, "User logged out", _request_fields('auth', '/api/logout', 'POST')


def _failed_login():
    fields = _request_fields('auth', '/api/login', 'POST', status_code=401)
    fields['reason'] = random.choice(['invalid_password', 'unknown_user', 'expired_token'])
    return logging.WARNING, "Failed login attempt", fields


def _order_created():
    fields = _request_fields('orders', '/api/orders', 'POST', status_code=201)
    fields.update({
        'order_id': f"ord_{random.randint(100000, 999999)}",
        'product': random.choice(PRODUCTS),
        'quantity': random.randint(1, 5),
        'amount': round(random.uniform(15, 1500), 2),
    })
    return logging.INFO, "Order created", fields


def _payment_processed():
    fields = _request_fields('payments', '/api/payments', 'POST')
    fields.update({
        'payment_id': f"pay_{uuid.uuid4().hex[:10]}",
        'amount': round(random.uniform(15, 1500), 2),
        'currency': random.choice(['USD', 'EUR']),
    })
    return logging.INFO, "Payment processed", fields


def _payment_declined():
    fields = _request_fields('payments', '/api/payments', 'POST', status_code=402)
    fields['reason'] = random.choice(['insufficient_funds', 'card_expired', 'fraud_suspected'])
    return logging.WARNING, "Payment declined", fields


def _payment_gateway_timeout():
    fields = _request_fields('payments', '/api/payments', 'POST', status_code=504,
                             duration=round(random.uniform(5, 30), 3))
    fields['error'] = 'Upstream payment gateway timed out'
    return logging.ERROR, "Payment gateway timeout", fields


def _low_stock():
    fields = _request_fields('inventory', '/api/inventory', 'GET')
    fields.update({'product': random.choice(PRODUCTS), 'stock_left': random.randint(0, 5)})
    return logging.WARNING, "Low stock level", fields


def _slow_query():
    fields = _request_fields('inventory', '/api/inventory', 'GET',
                             duration=round(random.uniform(1.5, 6), 3))
    fields['query'] = 'SELECT * FROM stock WHERE warehouse_id = ?'
    return logging.WARNING, "Slow database query", fields


def _db_connection_error():
    fields = _request_fields(random.choice(['orders', 'inventory']), '/api/orders', status_code=500)
    fields['error'] = 'could not connect to database: connection refused'
    return logging.ERROR, "Database connection error", fields


def _email_sent():
    fields = _request_fields('notifications', '/api/notify', 'POST', status_code=202)
    fields['channel'] = random.choice(['email', 'sms', 'push'])
    return logging.INFO, "Notification sent", fields


def _notification_failed():
    fields = _request_fields('notifications', '/api/notify', 'POST', status_code=502)
    fields.update({'channel': random.choice(['email', 'sms', 'push']),
                   'error': 'Provider returned 502 Bad Gateway'})
    return logging.ERROR, "Notification delivery failed", fields


def _search_performed():
    fields = _request_fields('search', '/api/search', 'GET')
    fields.update({'query': random.choice(PRODUCTS), 'results': random.randint(0, 120)})
    return logging.INFO, "Search performed", fields


def _cache_miss():
    fields = _request_fields('search', '/api/search', 'GET')
    fields['cache_key'] = f"search:{random.choice(PRODUCTS)}"
    return logging.INFO, "Cache miss", fields


def _out_of_memory():
    fields = _request_fields(random.choice(COMPONENTS), '/api/internal', status_code=503)
    fields['error'] = 'Worker killed: out of memory'
    return logging.CRITICAL, "Worker crashed", fields


# (scenario, weight) - weights shape the level distribution (~70% INFO)
SCENARIOS = [
    (_user_login, 14), (_user_logout, 8), (_order_created, 12), (_payment_processed, 12),
    (_email_sent, 10), (_search_performed, 12), (_cache_miss, 6),
    (_failed_login, 6), (_payment_declined, 4), (_low_stock, 4), (_slow_query, 4),
    (_payment_gateway_timeout, 3), (_db_connection_error, 2), (_notification_failed, 2),
    (_out_of_memory, 1),
]

# Error scenarios used during simulated incidents
INCIDENT_SCENARIOS = [_payment_gateway_timeout, _db_connection_error, _notification_failed]


def _emit(logger, scenario):
    level, message, fields = scenario()
    logger.log(level, message, extra=fields)


def _run(logger, mean_interval, incident_every):
    scenarios, weights = zip(*SCENARIOS)
    next_incident = time.time() + incident_every
    while True:
        try:
            if incident_every > 0 and time.time() >= next_incident:
                scenario = random.choice(INCIDENT_SCENARIOS)
                for _ in range(random.randint(10, 25)):
                    _emit(logger, scenario)
                    time.sleep(random.uniform(0.05, 0.3))
                next_incident = time.time() + incident_every
            else:
                _emit(logger, random.choices(scenarios, weights=weights, k=1)[0])
            time.sleep(random.expovariate(1.0 / mean_interval))
        except Exception as e:  # never let the generator thread die
            logger.error(f"Fake log generator error: {e}", extra={'operation': 'fake_log'})
            time.sleep(mean_interval)


def start_fake_log_generator(logger, mean_interval=1.0, incident_every=300):
    """
    Start the generator in a daemon thread.

    :param logger: logger to write to (uses the app's structured formatter)
    :param mean_interval: average seconds between log lines
    :param incident_every: seconds between simulated error bursts (0 disables them)
    """
    thread = threading.Thread(
        target=_run, args=(logger, mean_interval, incident_every),
        name='fake-log-generator', daemon=True,
    )
    thread.start()
    return thread
