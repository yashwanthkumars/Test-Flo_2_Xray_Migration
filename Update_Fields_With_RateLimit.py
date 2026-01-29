"""
JIRA CLOUD - UPDATE FIELDS WITH ADVANCED RATE LIMITING

This script implements comprehensive rate limiting strategies for parallel Jira updates:
1. Throttling/Rate Limiting with delays
2. Exponential Backoff with Retry (up to 5 attempts)
3. Adaptive Concurrency (starts at 5 threads, adjusts based on error rate)
4. Respects Jira's Rate Limit Headers
5. Queue-Based Processing
6. Circuit Breaker Pattern (stops after 5 consecutive 429 errors)

Features:
- Dynamically adjusts thread count based on API response
- Monitors rate limit headers (X-RateLimit-Remaining, X-RateLimit-Limit, Retry-After)
- Implements exponential backoff with jitter
- Logs detailed statistics and performance metrics
- Generates comprehensive results CSV
"""

import csv
import json
import requests
import logging
import time
import threading
import queue
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, Tuple, Optional
import random

# =====================================================================
# CONFIGURATION - JIRA CLOUD
# =====================================================================
JIRA_CLOUD_URL = "https://greyorange-work-uat-sandbox.atlassian.net"
JIRA_EMAIL = "yashwanth.k@padahsolutions.com"
JIRA_API_TOKEN = "YOUR_TOKEN"

# Custom Field IDs for Jira Cloud (Test Plan)
CUSTOM_FIELDS = {
   'Requirement': 'customfield_10557',
    'TP Progress': 'customfield_10558',
    'TP Status': 'customfield_10559',
    'Number of Steps': 'customfield_10560',
    'Number of Test Cases': 'customfield_10561',
}

# TP Status mapping
TP_STATUS_MAPPING = {
    'Open': '11973',
    'In Progress': '11974',
    'Acceptance': '11975',
    'Closed': '11976',
    'To Do': '11977',
    # Color codes - map to appropriate status
    # go to exported input file and TP status colum and remove the unique to get the colour codes and add TO Do option to field
    '8993A4': '11973',    # Map to Open
    '0052CC': '11974',    # Map to In Progress
    '6554C0': '11975',    # Map to Acceptance
    '226522': '11976',    # Map to Closed
    'C1C7D0': '11977',    # Map to TODO
}

INPUT_CSV = "testplan_fields_input.csv"
OUTPUT_CSV = f"testplan_update_results_ratelimit_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
STATS_LOG = f"rate_limit_stats_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

# =====================================================================
# RATE LIMITING CONFIGURATION
# =====================================================================
class RateLimitConfig:
    """Configuration for rate limiting and concurrency."""
    
    INITIAL_THREADS = 5
    MIN_THREADS = 2
    MAX_THREADS = 10
    
    # Delay between requests (in seconds)
    BASE_DELAY = 0.5
    
    # Exponential backoff configuration
    MAX_RETRIES = 5
    INITIAL_BACKOFF = 1  # seconds
    MAX_BACKOFF = 60     # seconds
    
    # Circuit breaker
    CIRCUIT_BREAKER_THRESHOLD = 5  # consecutive 429 errors
    CIRCUIT_BREAKER_TIMEOUT = 60   # seconds to wait
    
    # Adaptive concurrency tuning
    SUCCESS_THRESHOLD = 100  # requests before increasing threads
    ERROR_RATE_THRESHOLD = 0.1  # 10% error rate to trigger reduction


# =====================================================================
# LOGGING SETUP
# =====================================================================
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(STATS_LOG, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# =====================================================================
# RATE LIMITER CLASS
# =====================================================================
class RateLimiter:
    """Handles rate limiting, retries, circuit breaker, and adaptive concurrency."""
    
    def __init__(self):
        self.lock = threading.Lock()
        self.consecutive_429_errors = 0
        self.circuit_breaker_active = False
        self.circuit_breaker_time = None
        self.request_count = 0
        self.success_count = 0
        self.error_count = 0
        self.retry_count = 0
        self.rate_limit_hits = 0
        
        self.current_threads = RateLimitConfig.INITIAL_THREADS
        self.rate_limit_remaining = None
        self.rate_limit_total = None
        
    def should_pause(self) -> bool:
        """Check if we should pause all requests (circuit breaker or low remaining)."""
        with self.lock:
            # Check circuit breaker
            if self.circuit_breaker_active:
                elapsed = time.time() - self.circuit_breaker_time
                if elapsed < RateLimitConfig.CIRCUIT_BREAKER_TIMEOUT:
                    return True
                else:
                    self.circuit_breaker_active = False
                    logger.info("Circuit breaker reset after timeout")
            
            # Check remaining rate limit
            if self.rate_limit_remaining is not None and self.rate_limit_remaining < 10:
                logger.warning(f"Rate limit remaining: {self.rate_limit_remaining}, pausing requests")
                return True
            
            return False
    
    def record_response(self, status_code: int, headers: Dict) -> None:
        """Record response and update rate limit tracking."""
        with self.lock:
            self.request_count += 1
            
            # Update rate limit info from headers
            if 'X-RateLimit-Remaining' in headers:
                self.rate_limit_remaining = int(headers['X-RateLimit-Remaining'])
            if 'X-RateLimit-Limit' in headers:
                self.rate_limit_total = int(headers['X-RateLimit-Limit'])
            
            if status_code == 429:
                self.rate_limit_hits += 1
                self.consecutive_429_errors += 1
                
                if self.consecutive_429_errors >= RateLimitConfig.CIRCUIT_BREAKER_THRESHOLD:
                    self.circuit_breaker_active = True
                    self.circuit_breaker_time = time.time()
                    logger.error(f"Circuit breaker activated! {self.consecutive_429_errors} consecutive 429 errors")
            elif status_code == 204 or status_code == 200:
                self.success_count += 1
                self.consecutive_429_errors = 0
            else:
                self.error_count += 1
                self.consecutive_429_errors = 0
    
    def get_retry_delay(self, retry_count: int, headers: Dict) -> float:
        """Calculate retry delay with exponential backoff."""
        # Check Retry-After header first
        if 'Retry-After' in headers:
            return float(headers['Retry-After'])
        
        # Exponential backoff with jitter
        backoff = min(
            RateLimitConfig.INITIAL_BACKOFF * (2 ** retry_count),
            RateLimitConfig.MAX_BACKOFF
        )
        jitter = random.uniform(0, backoff * 0.1)  # Add 10% jitter
        return backoff + jitter
    
    def update_concurrency(self) -> None:
        """Adaptively adjust thread count based on performance."""
        with self.lock:
            if self.request_count < RateLimitConfig.SUCCESS_THRESHOLD:
                return
            
            error_rate = self.error_count / self.request_count if self.request_count > 0 else 0
            
            if error_rate > RateLimitConfig.ERROR_RATE_THRESHOLD:
                # Reduce threads if error rate is high
                new_threads = max(self.current_threads - 1, RateLimitConfig.MIN_THREADS)
                if new_threads < self.current_threads:
                    logger.warning(f"High error rate ({error_rate:.1%}), reducing threads to {new_threads}")
                    self.current_threads = new_threads
                    self.request_count = 0  # Reset counter
                    self.error_count = 0
            elif self.rate_limit_remaining is not None and self.rate_limit_remaining > 1000:
                # Increase threads if rate limit is healthy
                new_threads = min(self.current_threads + 1, RateLimitConfig.MAX_THREADS)
                if new_threads > self.current_threads:
                    logger.info(f"Healthy rate limit, increasing threads to {new_threads}")
                    self.current_threads = new_threads
                    self.request_count = 0  # Reset counter
                    self.error_count = 0
    
    def get_stats(self) -> Dict:
        """Return current statistics."""
        with self.lock:
            return {
                'request_count': self.request_count,
                'success_count': self.success_count,
                'error_count': self.error_count,
                'retry_count': self.retry_count,
                'rate_limit_hits': self.rate_limit_hits,
                'current_threads': self.current_threads,
                'rate_limit_remaining': self.rate_limit_remaining,
                'rate_limit_total': self.rate_limit_total,
                'circuit_breaker_active': self.circuit_breaker_active,
            }


# =====================================================================
# GLOBAL RATE LIMITER INSTANCE
# =====================================================================
rate_limiter = RateLimiter()


# =====================================================================
# JIRA API FUNCTIONS
# =====================================================================
def update_issue_fields_with_retry(
    issue_key: str,
    field_updates: Dict,
    retry_count: int = 0
) -> Tuple[bool, str, Dict]:
    """
    Update custom fields for a given issue with exponential backoff and retry logic.
    
    Returns:
        tuple: (success: bool, message: str, response_headers: dict)
    """
    # Check if we should pause
    while rate_limiter.should_pause():
        logger.warning(f"Pausing due to rate limit/circuit breaker for {issue_key}")
        time.sleep(5)
    
    # Apply base delay
    time.sleep(RateLimitConfig.BASE_DELAY)
    
    url = f"{JIRA_CLOUD_URL}/rest/api/3/issue/{issue_key}"
    auth = (JIRA_EMAIL, JIRA_API_TOKEN)
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json"
    }
    
    payload = {"fields": field_updates}
    
    try:
        response = requests.put(url, json=payload, auth=auth, headers=headers, timeout=30)
        
        # Record response metrics
        rate_limiter.record_response(response.status_code, response.headers)
        
        # Success case
        if response.status_code in [200, 204]:
            logger.debug(f"[SUCCESS] {issue_key}")
            return True, "Success", response.headers
        
        # Rate limit hit (429)
        elif response.status_code == 429:
            if retry_count < RateLimitConfig.MAX_RETRIES:
                delay = rate_limiter.get_retry_delay(retry_count, response.headers)
                logger.warning(f"[429 RATE LIMIT] {issue_key} - Retry {retry_count + 1}/{RateLimitConfig.MAX_RETRIES} after {delay:.1f}s")
                with rate_limiter.lock:
                    rate_limiter.retry_count += 1
                time.sleep(delay)
                return update_issue_fields_with_retry(issue_key, field_updates, retry_count + 1)
            else:
                error_msg = f"Max retries exceeded after rate limit"
                logger.error(f"[FAILED] {issue_key}: {error_msg}")
                return False, error_msg, response.headers
        
        # Other errors with retry
        elif response.status_code >= 500 and retry_count < RateLimitConfig.MAX_RETRIES:
            delay = rate_limiter.get_retry_delay(retry_count, response.headers)
            logger.warning(f"[{response.status_code} SERVER ERROR] {issue_key} - Retry {retry_count + 1}/{RateLimitConfig.MAX_RETRIES} after {delay:.1f}s")
            with rate_limiter.lock:
                rate_limiter.retry_count += 1
            time.sleep(delay)
            return update_issue_fields_with_retry(issue_key, field_updates, retry_count + 1)
        
        # Final error
        else:
            error_msg = f"{response.status_code} - {response.text[:200]}"
            logger.error(f"[FAILED] {issue_key}: {error_msg}")
            return False, error_msg, response.headers
    
    except requests.exceptions.Timeout:
        if retry_count < RateLimitConfig.MAX_RETRIES:
            delay = rate_limiter.get_retry_delay(retry_count, {})
            logger.warning(f"[TIMEOUT] {issue_key} - Retry {retry_count + 1}/{RateLimitConfig.MAX_RETRIES} after {delay:.1f}s")
            with rate_limiter.lock:
                rate_limiter.retry_count += 1
            time.sleep(delay)
            return update_issue_fields_with_retry(issue_key, field_updates, retry_count + 1)
        else:
            error_msg = "Timeout - Max retries exceeded"
            logger.error(f"[FAILED] {issue_key}: {error_msg}")
            return False, error_msg, {}
    
    except requests.exceptions.RequestException as e:
        error_msg = f"Request exception: {str(e)}"
        logger.error(f"[ERROR] {issue_key}: {error_msg}")
        return False, error_msg, {}


def parse_field_value(field_name: str, value: any) -> Optional[any]:
    """Parse and format field value based on field type."""
    if value is None or str(value).strip() == '':
        return None
    
    value = str(value).strip()
    
    if field_name in ['Number of Steps', 'Number of Test Cases']:
        try:
            return int(value)
        except ValueError:
            return 0
    
    if field_name == 'TP Progress':
        try:
            value = value.replace('%', '').strip()
            return int(value)
        except ValueError:
            return 0
    
    if field_name == 'TP Status':
        status_id = TP_STATUS_MAPPING.get(value)
        if status_id:
            return {"id": status_id}
        else:
            logger.warning(f"No mapping found for TP Status value '{value}'")
            return {"id": value}
    
    if field_name == 'Requirement':
        return value
    
    return value


# =====================================================================
# CSV PROCESSING
# =====================================================================
def process_csv_with_queue(queue_obj: queue.Queue, results_list: list) -> None:
    """Worker function to process items from the queue."""
    while True:
        try:
            row_data = queue_obj.get(timeout=1)
            if row_data is None:  # Poison pill
                break
            
            row_num, issue_key, field_updates = row_data
            
            # Update the issue
            success, message, headers = update_issue_fields_with_retry(issue_key, field_updates)
            
            result = {
                'Row': row_num,
                'Issue Key': issue_key,
                'Status': 'Success' if success else 'Failed',
                'Message': message,
                'Fields Updated': ', '.join(field_updates.keys()) if field_updates else 'None'
            }
            
            results_list.append(result)
            
        except queue.Empty:
            continue
        except Exception as e:
            logger.error(f"Worker thread error: {str(e)}")


def process_csv():
    """Read CSV file and update issues with adaptive concurrency."""
    try:
        # Read and prepare all rows
        rows_to_process = []
        
        with open(INPUT_CSV, 'r', encoding='utf-8-sig') as csvfile:
            reader = csv.DictReader(csvfile)
            
            required_headers = ['Issue Key', 'Issue ID', 'Requirement', 'TP Progress', 'TP Status',
                              'Number of Steps', 'Number of Test Cases']
            
            if not all(header in reader.fieldnames for header in required_headers):
                logger.error(f"CSV missing required headers. Expected: {required_headers}")
                return
            
            for row_num, row in enumerate(reader, start=2):
                issue_key = row.get('Issue Key', '').strip()
                
                if not issue_key:
                    continue
                
                # Build field updates
                field_updates = {}
                
                requirement = parse_field_value('Requirement', row.get('Requirement'))
                if requirement is not None:
                    field_updates[CUSTOM_FIELDS['Requirement']] = requirement
                
                tp_progress = parse_field_value('TP Progress', row.get('TP Progress'))
                if tp_progress is not None:
                    field_updates[CUSTOM_FIELDS['TP Progress']] = tp_progress
                
                tp_status = parse_field_value('TP Status', row.get('TP Status'))
                if tp_status is not None:
                    field_updates[CUSTOM_FIELDS['TP Status']] = tp_status
                
                num_steps = parse_field_value('Number of Steps', row.get('Number of Steps'))
                if num_steps is not None:
                    field_updates[CUSTOM_FIELDS['Number of Steps']] = num_steps
                
                num_tests = parse_field_value('Number of Test Cases', row.get('Number of Test Cases'))
                if num_tests is not None:
                    field_updates[CUSTOM_FIELDS['Number of Test Cases']] = num_tests
                
                if field_updates:
                    rows_to_process.append((row_num, issue_key, field_updates))
        
        if not rows_to_process:
            logger.warning("No valid rows to process")
            return
        
        logger.info(f"Loaded {len(rows_to_process)} rows to process")
        
        # Process with ThreadPoolExecutor and adaptive concurrency
        results = []
        start_time = time.time()
        
        with ThreadPoolExecutor(max_workers=rate_limiter.current_threads) as executor:
            futures = {}
            processed = 0
            
            for row_num, issue_key, field_updates in rows_to_process:
                # Adaptively adjust concurrency
                if processed > 0 and processed % 50 == 0:
                    rate_limiter.update_concurrency()
                    logger.info(f"Current concurrency level: {rate_limiter.current_threads} threads")
                
                future = executor.submit(update_issue_fields_with_retry, issue_key, field_updates)
                futures[future] = (row_num, issue_key, field_updates)
                processed += 1
            
            # Collect results as they complete
            for future in as_completed(futures):
                row_num, issue_key, field_updates = futures[future]
                try:
                    success, message, headers = future.result()
                    results.append({
                        'Row': row_num,
                        'Issue Key': issue_key,
                        'Status': 'Success' if success else 'Failed',
                        'Message': message,
                        'Fields Updated': ', '.join(field_updates.keys())
                    })
                except Exception as e:
                    logger.error(f"Error processing {issue_key}: {str(e)}")
                    results.append({
                        'Row': row_num,
                        'Issue Key': issue_key,
                        'Status': 'Failed',
                        'Message': str(e),
                        'Fields Updated': 'N/A'
                    })
        
        elapsed_time = time.time() - start_time
        
        # Write results
        write_results_csv(results)
        
        # Log summary statistics
        stats = rate_limiter.get_stats()
        success_count = sum(1 for r in results if r['Status'] == 'Success')
        failed_count = sum(1 for r in results if r['Status'] == 'Failed')
        
        logger.info(f"\n{'='*70}")
        logger.info(f"SUMMARY STATISTICS")
        logger.info(f"{'='*70}")
        logger.info(f"Total Requests: {len(results)}")
        logger.info(f"Successful: {success_count}")
        logger.info(f"Failed: {failed_count}")
        logger.info(f"Success Rate: {(success_count/len(results)*100):.1f}%")
        logger.info(f"Elapsed Time: {elapsed_time:.1f} seconds")
        logger.info(f"Average Time per Request: {(elapsed_time/len(results)):.2f} seconds")
        logger.info(f"\nRate Limiting Statistics:")
        logger.info(f"  Rate Limit Hits (429): {stats['rate_limit_hits']}")
        logger.info(f"  Retry Attempts: {stats['retry_count']}")
        logger.info(f"  Circuit Breaker Active: {stats['circuit_breaker_active']}")
        logger.info(f"  Rate Limit Remaining: {stats['rate_limit_remaining']}/{stats['rate_limit_total']}")
        logger.info(f"  Final Concurrency: {stats['current_threads']} threads")
        logger.info(f"Results written to: {OUTPUT_CSV}")
        logger.info(f"{'='*70}\n")
        
    except FileNotFoundError:
        logger.error(f"CSV file not found: {INPUT_CSV}")
    except Exception as e:
        logger.error(f"Error processing CSV: {str(e)}", exc_info=True)


def write_results_csv(results: list) -> None:
    """Write update results to CSV file."""
    try:
        with open(OUTPUT_CSV, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['Row', 'Issue Key', 'Status', 'Message', 'Fields Updated']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            writer.writeheader()
            writer.writerows(results)
        
        logger.info(f"Results written to {OUTPUT_CSV}")
    except Exception as e:
        logger.error(f"Error writing results CSV: {str(e)}")


# =====================================================================
# MAIN FUNCTION
# =====================================================================
def main():
    """Main execution function."""
    logger.info("="*70)
    logger.info("JIRA CLOUD - UPDATE TEST PLAN FIELDS WITH RATE LIMITING")
    logger.info("="*70)
    logger.info(f"Configuration:")
    logger.info(f"  Initial Threads: {RateLimitConfig.INITIAL_THREADS}")
    logger.info(f"  Max Retries: {RateLimitConfig.MAX_RETRIES}")
    logger.info(f"  Base Delay: {RateLimitConfig.BASE_DELAY}s")
    logger.info(f"  Circuit Breaker Threshold: {RateLimitConfig.CIRCUIT_BREAKER_THRESHOLD} consecutive 429s")
    logger.info(f"  Circuit Breaker Timeout: {RateLimitConfig.CIRCUIT_BREAKER_TIMEOUT}s")
    logger.info(f"{'='*70}\n")
    
    # Validate configuration
    if JIRA_CLOUD_URL == "https://your-domain.atlassian.net":
        logger.error("ERROR: Please update JIRA_CLOUD_URL")
        return
    
    if JIRA_EMAIL == "your-email@example.com":
        logger.error("ERROR: Please update JIRA_EMAIL")
        return
    
    if JIRA_API_TOKEN == "your-api-token":
        logger.error("ERROR: Please update JIRA_API_TOKEN")
        return
    
    process_csv()


if __name__ == "__main__":
    main()
