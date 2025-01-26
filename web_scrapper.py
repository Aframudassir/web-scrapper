import requests
import json
import logging
import time
from datetime import datetime
from typing import List, Dict
from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from queue import Queue
import threading

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scraper.log'),
        logging.StreamHandler()
    ]
)


class ProxyManager:
    def __init__(self, proxy_strings: List[str]):
        self.proxies = proxy_strings
        self.current_index = 0
        self.lock = Lock()

    def get_next_proxy(self) -> dict:
        with self.lock:
            proxy_string = self.proxies[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.proxies)
            parts = proxy_string.split(':')
            return {
                'http': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}',
                'https': f'http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}'
            }


class StubHubScraper:
    def __init__(self, proxy_strings: List[str], num_threads: int = 5):
        self.proxy_manager = ProxyManager(proxy_strings)
        self.num_threads = num_threads
        self.total_attempts = 0
        self.failed_attempts = 0
        self.results_queue = Queue()
        self.stats_lock = Lock()
        self.session = requests.Session()

    def get_events(self) -> List[Dict]:
        """Fetch all MSG events from StubHub"""
        url = 'https://www.stubhub.com/madison-square-garden-tickets/venue/1282/'
        params = {
            'method': 'TrendingEventsLocale',
            'categoryId': '0',
            'maxRows': '100',
            'fromDate': '1970-01-01T00:00:00.000Z',
            'toDate': '9999-12-31T23:59:59.999Z',
            'venueId': '3708'
        }

        headers = {
            'accept': '*/*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'content-length': '0',
            'content-type': 'application/json',
            'origin': 'https://www.stubhub.com',
            'priority': 'u=1, i',
            'referer': 'https://www.stubhub.com/madison-square-garden-tickets/venue/1282/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }

        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                verify=False,
                proxies=self.proxy_manager.get_next_proxy(),
                timeout=30
            )

            if response.status_code != 200:
                logging.error(f"Failed to fetch events: {response.status_code}")
                return []

            data = response.json()
            events = data.get('items', [])
            logging.info(f"Successfully fetched {len(events)} events")
            return events

        except Exception as e:
            logging.error(f"Error fetching events: {str(e)}")
            return []

    def get_tickets(self, event: Dict, proxy: dict) -> Dict:
        """Fetch tickets for a specific event"""
        event_id = event['eventId']
        category_id = event.get('categoryId', '')

        url = f"https://www.stubhub.com/Browse/VenueMap/GetVenueMapSeatingConfig/{event_id}"
        params = {
            'categoryId': category_id,
            'withFees': 'false',
            'withSeats': 'false'
        }

        headers = {
            'accept': '*/*',
            'accept-language': 'en-GB,en-US;q=0.9,en;q=0.8',
            'cache-control': 'no-cache',
            'content-length': '0',
            'origin': 'https://www.stubhub.com',
            'pragma': 'no-cache',
            'referer': f'https://www.stubhub.com/new-york-rangers-new-york-tickets-1-26-2025/event/{event_id}/',
            'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
            'sec-ch-ua-mobile': '?0',
            'sec-ch-ua-platform': '"macOS"',
            'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36'
        }

        try:
            response = requests.post(
                url,
                params=params,
                headers=headers,
                proxies=proxy,
                verify=False,
                timeout=10
            )

            if response.status_code != 200:
                with self.stats_lock:
                    self.failed_attempts += 1
                return None

            return response.json()

        except Exception as e:
            with self.stats_lock:
                self.failed_attempts += 1
            logging.error(f"Error fetching tickets for event {event_id}: {str(e)}")
            return None

    def process_event_batch(self, events: List[Dict]) -> None:
        """Process a batch of events in a single thread"""
        thread_name = threading.current_thread().name
        proxy = self.proxy_manager.get_next_proxy()

        print(f"\nThread {thread_name} starting batch of {len(events)} events")

        for event in events:
            with self.stats_lock:
                self.total_attempts += 1

            start_time = time.time()
            ticket_data = self.get_tickets(event, proxy)
            duration = time.time() - start_time

            if ticket_data:
                result = {
                    'event_id': event['eventId'],
                    'event_name': event['eventName'],
                    'event_date': event['localEventDateTime'],
                    'venue': event['venueName'],
                    'category_id': event['categoryId'],
                    'tickets': ticket_data,
                    'scrape_duration': duration
                }

                # Print immediate results
                zones = ticket_data.get('zones', [])
                print(f"\nProcessed: {event['eventName']}")
                print(f"- ID: {event['eventId']}")
                print(f"- Date: {event['localEventDateTime']}")
                print(f"- Venue: {event['venueName']}")
                print(f"- Zones found: {len(zones)}")
                print(f"- Processing time: {duration:.2f} seconds")

                self.results_queue.put(result)
            else:
                print(f"\nFailed to process: {event['eventName']} (ID: {event['eventId']})")

        print(f"\nThread {thread_name} completed batch processing")

    def run(self) -> List[Dict]:
        """Main execution method"""
        all_results = []

        # Get initial events
        events = self.get_events()
        if not events:
            return []

        logging.info(f"Found {len(events)} events to process")

        # Split events among threads
        events_per_thread = len(events) // self.num_threads + (1 if len(events) % self.num_threads else 0)
        thread_event_batches = [
            events[i:i + events_per_thread]
            for i in range(0, len(events), events_per_thread)
        ]

        # Process events using thread pool
        with ThreadPoolExecutor(max_workers=self.num_threads) as executor:
            executor.map(self.process_event_batch, thread_event_batches)

        # Collect results from queue
        while not self.results_queue.empty():
            all_results.append(self.results_queue.get())
        self.print_final_summary(all_results)

    def save_results_to_json(self, results: List[Dict], total_time, average_time) -> None:
        """Save scraping results to a JSON file"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"stubhub_results_{timestamp}.json"

        # Prepare the output data structure
        output_data = {
            "scrape_timestamp": datetime.now().isoformat(),
            "total_events": len(results),
            "total_attempts": self.total_attempts,
            "failed_attempts": self.failed_attempts,
            "failure_rate": (self.failed_attempts / self.total_attempts * 100) if self.total_attempts > 0 else 0,
            "total_execution_time":total_time,
            "average_time_per_event": average_time,
            "events": results
        }

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(output_data, f, indent=2, ensure_ascii=False)
            logging.info(f"Results saved to {filename}")
            print(f"\nResults have been saved to: {filename}")
        except Exception as e:
            logging.error(f"Error saving results to JSON: {str(e)}")
            print(f"\nError saving results to JSON: {str(e)}")

    def print_final_summary(self, results: List[Dict]) -> None:
        """Print detailed final summary in the required format"""
        num_events = len(results)
        if num_events == 0:
            print("No results to process")
            return

        # Calculate average time from individual event durations
        total_event_time = sum(result.get('scrape_duration', 0) for result in results)
        avg_time_per_event = total_event_time / num_events if num_events > 0 else 0
        failure_rate = (self.failed_attempts / self.total_attempts) * 100 if self.total_attempts > 0 else 0
        self.save_results_to_json(results, total_event_time,avg_time_per_event)
        # Print Results Summary
        print("\n" + "=" * 50)
        print("STUBHUB SCRAPER RESULTS")
        print("=" * 50)

        print("\nPERFORMANCE CRITERIA:")
        print(f"1. Average scrape time per event: {avg_time_per_event:.2f} seconds")
        print(f"   Required: < 2 seconds")
        print(f"   Status: {'✓ PASS' if avg_time_per_event < 2 else '✗ FAIL'}")

        print(f"\n2. Failed attempts: {self.failed_attempts}")
        print(f"   Required: 0")
        print(f"   Status: {'✓ PASS' if self.failed_attempts == 0 else '✗ FAIL'}")

        print(f"\n3. Failure rate: {failure_rate:.2f}%")
        print(f"   Required: < 15%")
        print(f"   Status: {'✓ PASS' if failure_rate < 15 else '✗ FAIL'}")

        print("\nSCRAPING STATISTICS:")
        print(f"- Total events found: {num_events}")
        print(f"- Total scraping attempts: {self.total_attempts}")
        print(f"- Failed attempts: {self.failed_attempts}")
        print(f"- Total execution time: {total_event_time:.2f} seconds")

        print("\nEVENT DETAILS:")
        for result in results:
            zones = result.get('tickets', {}).get('zones', [])
            print(f"\nEvent: {result['event_name']}")
            print(f"- ID: {result['event_id']}")
            print(f"- Date: {result['event_date']}")
            print(f"- Venue: {result['venue']}")
            print(f"- Number of ticket zones: {len(zones)}")
            print(f"- Processing time: {result.get('scrape_duration', 0):.2f} seconds")


def main():
    proxy_strings = [
        "evo-pro.wiredproxies.com:61234:PP_V1ULWJH-country-US-session-EPza6G4BIcUc-sessionduration-5:3w1jzssi",
        "evo-pro.wiredproxies.com:61234:PP_V1ULWJH-country-US-session-N2Uk9JpUqX9T-sessionduration-5:3w1jzssi",
        "evo-pro.wiredproxies.com:61234:PP_V1ULWJH-country-US-session-rX74XOd3BLB8-sessionduration-5:3w1jzssi",
        "evo-pro.wiredproxies.com:61234:PP_V1ULWJH-country-US-session-CXplwLZFl6TO-sessionduration-5:3w1jzssi",
        "evo-pro.wiredproxies.com:61234:PP_V1ULWJH-country-US-session-aCR3ivk3l9ss-sessionduration-5:3w1jzssi"
    ]

    scraper = StubHubScraper(proxy_strings, num_threads=5)
    scraper.run()


if __name__ == "__main__":
    main()