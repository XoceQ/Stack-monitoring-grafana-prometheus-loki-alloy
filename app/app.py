#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Simple API for a monitoring system with Prometheus and Loki.
Basic endpoints and essential metrics only, with structured logging.
"""

import os
import time
import random
import threading
import json
from datetime import datetime
from flask import Flask, request, jsonify
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST
import logging
import logging.handlers

from fake_logs import start_fake_log_generator

# Runtime configuration (provided by docker-compose through environment variables)
APP_PORT = int(os.getenv('APP_PORT', '8000'))
APP_VERSION = os.getenv('APP_VERSION', '1.0.0')
SERVICE_NAME = os.getenv('SERVICE_NAME', 'sample-app')
FAKE_LOGS_ENABLED = os.getenv('FAKE_LOGS_ENABLED', 'true').lower() in ('1', 'true', 'yes')
FAKE_LOGS_INTERVAL_SECONDS = float(os.getenv('FAKE_LOGS_INTERVAL_SECONDS', '1.0'))
FAKE_LOGS_INCIDENT_EVERY_SECONDS = int(os.getenv('FAKE_LOGS_INCIDENT_EVERY_SECONDS', '300'))

# Structured logging configuration for Loki
class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_entry = {
            'timestamp': datetime.utcnow().isoformat() + 'Z',
            'level': record.levelname,
            'message': record.getMessage(),
            'service': SERVICE_NAME,
            'version': APP_VERSION
        }
        
        # Add every field passed through `extra=` (core fields are never overwritten)
        for key, value in record.__dict__.items():
            if key not in _STANDARD_RECORD_ATTRS and key not in log_entry:
                log_entry[key] = value

        return json.dumps(log_entry, default=str)

# Attributes every LogRecord has; anything else came from `extra=`
_STANDARD_RECORD_ATTRS = set(vars(logging.LogRecord('', 0, '', 0, '', None, None))) | {'message', 'asctime'}

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Console handler with structured format
console_handler = logging.StreamHandler()
console_handler.setFormatter(StructuredFormatter())
logger.addHandler(console_handler)

# Initialize Flask application
app = Flask(__name__)

# Prometheus metrics
# Counter for HTTP requests
http_requests_total = Counter(
    'http_requests_total',
    'Total number of HTTP requests received',
    ['method', 'endpoint', 'status']
)

# Histogram for HTTP request duration
http_request_duration_seconds = Histogram(
    'http_request_duration_seconds',
    'HTTP request duration in seconds',
    ['method', 'endpoint']
)

# Gauge for simulated active users
active_users = Gauge(
    'active_users',
    'Number of active users in the application'
)

# Gauge for simulated application memory usage
app_memory_usage_bytes = Gauge(
    'app_memory_usage_bytes',
    'Application memory usage in bytes'
)

# Counter for simulated operations
api_operations_total = Counter(
    'api_operations_total',
    'Total number of API operations',
    ['operation', 'status']
)

def simulate_metrics():
    """
    Background task that simulates changing metrics
    """
    while True:
        try:
            # Simulate active users (between 5 and 50)
            users = random.randint(5, 50)
            active_users.set(users)
            # Simulate memory usage (between 50MB and 200MB)
            memory = random.randint(50 * 1024 * 1024, 200 * 1024 * 1024)
            app_memory_usage_bytes.set(memory)
            # Log simulated metrics
            logger.info("Metrics updated", extra={
                'active_users': users,
                'memory_usage_mb': memory // (1024 * 1024),
                'operation': 'metrics_update'
            })
            time.sleep(30)  # Update every 30 seconds
        except Exception as e:
            logger.error(f"Error updating metrics: {e}", extra={
                'operation': 'metrics_update',
                'error': str(e)
            })
            time.sleep(30)

# Decorator that measures request duration
def measure_request(f):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        request_id = f"req_{random.randint(1000, 9999)}"
        
        # Log request start
        logger.info("Request started", extra={
            'request_id': request_id,
            'method': request.method,
            'endpoint': request.endpoint or 'unknown',
            'ip_address': request.remote_addr,
            'user_agent': request.headers.get('User-Agent', 'unknown'),
            'operation': 'request_start'
        })
        
        try:
            response = f(*args, **kwargs)
            status = '200'
            
            # Log success
            duration = time.time() - start_time
            logger.info("Request completed successfully", extra={
                'request_id': request_id,
                'method': request.method,
                'endpoint': request.endpoint or 'unknown',
                'status_code': 200,
                'duration': round(duration, 3),
                'operation': 'request_success'
            })
            
            return response
            
        except Exception as e:
            status = '500'
            duration = time.time() - start_time
            
            # Log error
            logger.error(f"Request error: {e}", extra={
                'request_id': request_id,
                'method': request.method,
                'endpoint': request.endpoint or 'unknown',
                'status_code': 500,
                'duration': round(duration, 3),
                'error': str(e),
                'operation': 'request_error'
            })
            raise
        finally:
            duration = time.time() - start_time
            endpoint = request.endpoint or 'unknown'
            
            # Record metrics
            http_request_duration_seconds.labels(
                method=request.method,
                endpoint=endpoint
            ).observe(duration)
            
            http_requests_total.labels(
                method=request.method,
                endpoint=endpoint,
                status=status
            ).inc()
    
    wrapper.__name__ = f.__name__
    return wrapper

@app.route('/metrics')
def metrics():
    """
    Endpoint scraped by Prometheus
    """
    logger.info("Metrics requested", extra={
        'operation': 'metrics_endpoint',
        'endpoint': 'metrics'
    })
    return generate_latest(), 200, {'Content-Type': CONTENT_TYPE_LATEST}

@app.route('/')
@measure_request
def home():
    """
    Main API endpoint
    """
    api_operations_total.labels(operation='home', status='success').inc()
    
    logger.info("Main endpoint accessed", extra={
        'operation': 'home_endpoint',
        'endpoint': 'home'
    })
    
    return jsonify({
        'service': 'Monitoring API',
        'status': 'running',
        'version': APP_VERSION,
        'endpoints': ['/health', '/users', '/data', '/process', '/logs']
    })

@app.route('/health')
@measure_request
def health():
    """
    Health check endpoint
    """
    api_operations_total.labels(operation='health_check', status='success').inc()
    
    uptime = time.time() - app.start_time
    
    logger.info("Health check performed", extra={
        'operation': 'health_check',
        'endpoint': 'health',
        'uptime_seconds': round(uptime, 2)
    })
    
    return jsonify({
        'status': 'healthy',
        'timestamp': time.time(),
        'uptime': uptime
    })

@app.route('/users')
@measure_request
def get_users():
    """
    Endpoint that simulates fetching user information
    """
    # Simulate processing time
    processing_time = random.uniform(0.1, 0.3)
    time.sleep(processing_time)
    
    # Occasionally simulate an error
    if random.random() < 0.05:  # 5% error rate
        api_operations_total.labels(operation='get_users', status='error').inc()
        
        logger.error("Error fetching users", extra={
            'operation': 'get_users',
            'endpoint': 'users',
            'error': 'Database connection failed',
            'processing_time': round(processing_time, 3)
        })
        
        return jsonify({'error': 'Database connection failed'}), 500
    
    api_operations_total.labels(operation='get_users', status='success').inc()
    
    active_users_count = int(active_users._value._value)
    total_users = random.randint(100, 500)
    new_users = random.randint(0, 20)
    
    logger.info("Users fetched successfully", extra={
        'operation': 'get_users',
        'endpoint': 'users',
        'active_users': active_users_count,
        'total_users': total_users,
        'new_users_today': new_users,
        'processing_time': round(processing_time, 3)
    })
    
    return jsonify({
        'active_users': active_users_count,
        'total_users': total_users,
        'new_users_today': new_users
    })

@app.route('/data')
@measure_request 
def get_data():
    """
    Endpoint that simulates data processing
    """
    # Simulate variable processing time
    processing_time = random.uniform(0.2, 0.8)
    time.sleep(processing_time)
    
    # Occasionally simulate high latency
    if random.random() < 0.1:  # 10% slow requests
        extra_delay = random.uniform(1.0, 2.0)
        time.sleep(extra_delay)
        processing_time += extra_delay
        
        logger.warning("Slow processing detected", extra={
            'operation': 'get_data',
            'endpoint': 'data',
            'processing_time': round(processing_time, 3),
            'extra_delay': round(extra_delay, 3)
        })
    
    api_operations_total.labels(operation='data_processing', status='success').inc()
    
    records_processed = random.randint(100, 1000)
    cache_hit_rate = round(random.uniform(0.7, 0.95), 2)
    
    logger.info("Data processed successfully", extra={
        'operation': 'get_data',
        'endpoint': 'data',
        'records_processed': records_processed,
        'processing_time_ms': int(processing_time * 1000),
        'cache_hit_rate': cache_hit_rate
    })
    
    return jsonify({
        'records_processed': records_processed,
        'processing_time_ms': int(processing_time * 1000),
        'cache_hit_rate': cache_hit_rate
    })

@app.route('/process', methods=['POST'])
@measure_request
def process_data():
    """
    POST endpoint that simulates data processing
    """
    # Simulate data validation
    processing_time = random.uniform(0.1, 0.4)
    time.sleep(processing_time)
    
    # Occasionally simulate validation errors
    if random.random() < 0.08:  # 8% error rate
        api_operations_total.labels(operation='process_data', status='error').inc()
        
        logger.error("Data processing error", extra={
            'operation': 'process_data',
            'endpoint': 'process',
            'error': 'Invalid data format',
            'processing_time': round(processing_time, 3)
        })
        
        return jsonify({'error': 'Invalid data format'}), 400
    
    api_operations_total.labels(operation='process_data', status='success').inc()
    
    job_id = f"job_{random.randint(1000, 9999)}"
    
    logger.info("Data processed successfully", extra={
        'operation': 'process_data',
        'endpoint': 'process',
        'job_id': job_id,
        'processing_time': round(processing_time, 3)
    })
    
    return jsonify({
        'result': 'processed',
        'job_id': job_id,
        'estimated_completion': '2-5 minutes'
    })

@app.route('/logs')
@measure_request
def generate_test_logs():
    """
    Endpoint that generates test logs with different levels
    """
    log_levels = ['INFO', 'WARNING', 'ERROR', 'DEBUG']
    
    for i in range(5):
        level = random.choice(log_levels)
        message = f"Test log {i+1} - Level: {level}"
        
        if level == 'INFO':
            logger.info(message, extra={
                'operation': 'test_logs',
                'log_number': i+1,
                'level': level
            })
        elif level == 'WARNING':
            logger.warning(message, extra={
                'operation': 'test_logs',
                'log_number': i+1,
                'level': level
            })
        elif level == 'ERROR':
            logger.error(message, extra={
                'operation': 'test_logs',
                'log_number': i+1,
                'level': level
            })
        elif level == 'DEBUG':
            logger.debug(message, extra={
                'operation': 'test_logs',
                'log_number': i+1,
                'level': level
            })
        
        time.sleep(0.1)
    
    logger.info("Test logs generated", extra={
        'operation': 'generate_test_logs',
        'endpoint': 'logs',
        'logs_generated': 5
    })
    
    return jsonify({
        'message': 'Test logs generated',
        'logs_count': 5,
        'levels': log_levels
    })

@app.errorhandler(404)
def not_found(error):
    """
    404 error handler
    """
    http_requests_total.labels(
        method=request.method,
        endpoint='not_found',
        status='404'
    ).inc()
    
    logger.warning("Endpoint not found", extra={
        'operation': 'not_found',
        'method': request.method,
        'endpoint': request.path,
        'status_code': 404
    })
    
    return jsonify({'error': 'Endpoint not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    """
    500 error handler
    """
    http_requests_total.labels(
        method=request.method,
        endpoint=request.endpoint or 'unknown',
        status='500'
    ).inc()
    
    logger.error("Internal server error", extra={
        'operation': 'internal_error',
        'method': request.method,
        'endpoint': request.endpoint or 'unknown',
        'status_code': 500,
        'error': str(error)
    })
    
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    # Start time used to compute uptime
    app.start_time = time.time()
    
    # Start background thread for simulated metrics
    metrics_thread = threading.Thread(target=simulate_metrics, daemon=True)
    metrics_thread.start()

    # Start background thread that emits fake business logs for Grafana/Loki
    if FAKE_LOGS_ENABLED:
        start_fake_log_generator(
            logger,
            mean_interval=FAKE_LOGS_INTERVAL_SECONDS,
            incident_every=FAKE_LOGS_INCIDENT_EVERY_SECONDS,
        )
        logger.info("Fake log generator started", extra={
            'operation': 'app_startup',
            'mean_interval_seconds': FAKE_LOGS_INTERVAL_SECONDS,
            'incident_every_seconds': FAKE_LOGS_INCIDENT_EVERY_SECONDS,
        })
    
    logger.info(f"Starting monitoring API on port {APP_PORT}", extra={
        'operation': 'app_startup',
        'port': APP_PORT,
        'version': APP_VERSION
    })
    logger.info(f"Metrics available at http://localhost:{APP_PORT}/metrics", extra={
        'operation': 'app_startup',
        'metrics_endpoint': '/metrics'
    })
    logger.info("Endpoints: /, /health, /users, /data, /process, /logs", extra={
        'operation': 'app_startup',
        'available_endpoints': ['/', '/health', '/users', '/data', '/process', '/logs']
    })
    
    # Run Flask application
    app.run(host='0.0.0.0', port=APP_PORT, debug=False) 