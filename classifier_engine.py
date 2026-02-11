import html
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

from config import (
    DEFAULT_QUERY,
    LABEL_IMPORTANT,
    LABEL_LOW_PRIORITY,
    REPORT_FILE,
    BATCH_SIZE,
)
from gmail_client import GmailClient
from llm_classifier import classify_batch
from state import RunState

log = logging.getLogger(__name__)


class ClassifierEngine:
    def __init__(self, service, progress_cb=None, log_cb=None, query=None):
        self.service = service
        self.gmail = GmailClient(service)
        self.query = query or DEFAULT_QUERY
        self.progress_cb = progress_cb or (lambda *a: None)
        self.log_cb = log_cb or (lambda msg: None)
        self._stop_event = threading.Event()
        self._thread = None
        self.state = None
        self._details_cache = {}

    def start(self, resume=False):
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, args=(resume,), daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()

    def is_running(self):
        return self._thread is not None and self._thread.is_alive()

    def _run(self, resume):
        try:
            self._pipeline(resume)
        except Exception as e:
            log.exception("Engine error")
            self.log_cb(f"ERROR: {e}")

    def _pipeline(self, resume):
        # Load or create state
        if resume:
            self.state = RunState.load()
            if not self.state:
                self.log_cb("No checkpoint found. Starting fresh.")
                self.state = RunState()
            else:
                self.log_cb(
                    f"Resumed: {len(self.state.processed)}/{len(self.state.all_message_ids)} already done."
                )
        else:
            self.state = RunState()
            RunState.clear()

        # Ensure labels exist
        self.log_cb("Ensuring Gmail labels exist...")
        self.gmail.ensure_labels_exist()

        # Fetch IDs if not resuming with existing IDs
        if not self.state.all_message_ids:
            self.log_cb(f"Fetching message IDs (query: {self.query})...")
            self.state.all_message_ids = self.gmail.fetch_message_ids(self.query)
            self.state.save()
            self.log_cb(f"Found {len(self.state.all_message_ids)} messages.")

        total = len(self.state.all_message_ids)
        if total == 0:
            self.log_cb("No messages found.")
            return

        # Classify
        ids_to_process = [
            mid for mid in self.state.all_message_ids if mid not in self.state.processed
        ]
        self.log_cb(f"Classifying {len(ids_to_process)} remaining messages...")

        # Build list of batch ID chunks
        batch_chunks = [
            ids_to_process[i : i + BATCH_SIZE]
            for i in range(0, len(ids_to_process), BATCH_SIZE)
        ]

        # Prefetch pipeline: fetch next batch details while classifying current
        prefetch_executor = ThreadPoolExecutor(max_workers=1)
        prefetch_future = None

        for batch_idx, batch_ids in enumerate(batch_chunks):
            if self._stop_event.is_set():
                self.log_cb("Stopped by user. Checkpoint saved.")
                self.state.save()
                prefetch_executor.shutdown(wait=False)
                return

            # Get details for current batch (from prefetch or direct fetch)
            if prefetch_future is not None:
                details = prefetch_future.result()
            else:
                details = self.gmail.fetch_message_details_batch(batch_ids)

            # Cache details for report
            self._details_cache.update(details)

            # Start prefetching next batch
            next_idx = batch_idx + 1
            if next_idx < len(batch_chunks):
                next_batch_ids = batch_chunks[next_idx]
                prefetch_future = prefetch_executor.submit(
                    self.gmail.fetch_message_details_batch, next_batch_ids
                )
            else:
                prefetch_future = None

            # Classify entire batch concurrently
            classifications = classify_batch(list(details.values()))

            # Update state with results
            for mid, classification in classifications.items():
                self.state.processed[mid] = classification

                done = len(self.state.processed)
                email = details.get(mid, {})
                self.progress_cb(done, total, classification)
                self.log_cb(
                    f"[{done}/{total}] {classification.upper()}: {email.get('subject', '')[:60]}"
                )

            self.state.save()

        prefetch_executor.shutdown(wait=False)

        self.state.save()
        self.log_cb("Classification complete. Applying labels...")

        # Apply labels
        self._apply_labels()

        # Generate report
        self._generate_report()

        RunState.clear()
        self.log_cb("Done!")

    def _apply_labels(self):
        important_ids = [
            mid
            for mid, cls in self.state.processed.items()
            if cls == "important" and mid not in self.state.labeled
        ]
        low_ids = [
            mid
            for mid, cls in self.state.processed.items()
            if cls == "low_priority" and mid not in self.state.labeled
        ]

        if important_ids:
            label_id = self.gmail.get_label_id(LABEL_IMPORTANT)
            self.log_cb(f"Applying '{LABEL_IMPORTANT}' to {len(important_ids)} messages...")
            self.gmail.apply_label_batch(important_ids, label_id)
            self.state.labeled.update(important_ids)

        if low_ids:
            label_id = self.gmail.get_label_id(LABEL_LOW_PRIORITY)
            self.log_cb(f"Applying '{LABEL_LOW_PRIORITY}' to {len(low_ids)} messages...")
            self.gmail.apply_label_batch(low_ids, label_id)
            self.state.labeled.update(low_ids)

        self.state.save()

    def _generate_report(self):
        important = {
            mid: cls for mid, cls in self.state.processed.items() if cls == "important"
        }
        low = {
            mid: cls
            for mid, cls in self.state.processed.items()
            if cls == "low_priority"
        }

        # Use cached details if available, otherwise fall back to API fetch
        if self._details_cache:
            details = self._details_cache
        else:
            all_ids = list(self.state.processed.keys())
            self.log_cb("Fetching details for report...")
            details = self.gmail.fetch_message_details_batch(all_ids)

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rows_important = ""
        rows_low = ""

        for mid, info in details.items():
            cls = self.state.processed.get(mid, "unknown")
            row = (
                f"<tr><td>{html.escape(info.get('date', ''))}</td>"
                f"<td>{html.escape(info.get('from', ''))}</td>"
                f"<td>{html.escape(info.get('subject', ''))}</td></tr>\n"
            )
            if cls == "important":
                rows_important += row
            else:
                rows_low += row

        report = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8">
<title>Gmail Cleanup Report</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 2em; }}
h1 {{ color: #333; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 2em; }}
th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
th {{ background: #4285f4; color: white; }}
tr:nth-child(even) {{ background: #f2f2f2; }}
.summary {{ background: #e8f5e9; padding: 1em; border-radius: 8px; margin-bottom: 2em; }}
</style></head><body>
<h1>Gmail Cleanup Report</h1>
<div class="summary">
<p><strong>Generated:</strong> {now}</p>
<p><strong>Total processed:</strong> {len(self.state.processed)}</p>
<p><strong>Important:</strong> {len(important)}</p>
<p><strong>Low Priority:</strong> {len(low)}</p>
</div>

<h2>Important ({len(important)})</h2>
<table><tr><th>Date</th><th>From</th><th>Subject</th></tr>
{rows_important}</table>

<h2>Low Priority ({len(low)})</h2>
<table><tr><th>Date</th><th>From</th><th>Subject</th></tr>
{rows_low}</table>
</body></html>"""

        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write(report)
        self.log_cb(f"Report saved to {REPORT_FILE}")
