import time
import logging

from googleapiclient.http import BatchHttpRequest

from config import LABEL_IMPORTANT, LABEL_LOW_PRIORITY, BATCH_SIZE

log = logging.getLogger(__name__)


class GmailClient:
    def __init__(self, service):
        self.service = service
        self.user = "me"
        self._label_ids = {}

    def fetch_message_ids(self, query):
        ids = []
        page_token = None
        while True:
            resp = (
                self.service.users()
                .messages()
                .list(
                    userId=self.user,
                    q=query,
                    pageToken=page_token,
                    maxResults=500,
                )
                .execute()
            )
            for msg in resp.get("messages", []):
                ids.append(msg["id"])
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        return ids

    def fetch_message_details_batch(self, ids):
        results = {}

        for i in range(0, len(ids), BATCH_SIZE):
            chunk = ids[i : i + BATCH_SIZE]
            batch = self.service.new_batch_http_request()

            def _callback(req_id, response, exception):
                if exception:
                    log.warning("Batch fetch error for %s: %s", req_id, exception)
                    return
                headers = {}
                for h in response.get("payload", {}).get("headers", []):
                    name = h["name"].lower()
                    if name in ("from", "subject", "date"):
                        headers[name] = h["value"]
                results[response["id"]] = {
                    "id": response["id"],
                    "from": headers.get("from", ""),
                    "subject": headers.get("subject", ""),
                    "date": headers.get("date", ""),
                    "snippet": response.get("snippet", ""),
                }

            for mid in chunk:
                batch.add(
                    self.service.users()
                    .messages()
                    .get(
                        userId=self.user,
                        id=mid,
                        format="metadata",
                        metadataHeaders=["From", "Subject", "Date"],
                    ),
                    callback=_callback,
                    request_id=mid,
                )
            batch.execute()
            time.sleep(0.1)

        return results

    def ensure_labels_exist(self):
        resp = self.service.users().labels().list(userId=self.user).execute()
        existing = {lb["name"]: lb["id"] for lb in resp.get("labels", [])}

        for name in (LABEL_IMPORTANT, LABEL_LOW_PRIORITY):
            if name in existing:
                self._label_ids[name] = existing[name]
            else:
                body = {
                    "name": name,
                    "labelListVisibility": "labelShow",
                    "messageListVisibility": "show",
                }
                created = (
                    self.service.users()
                    .labels()
                    .create(userId=self.user, body=body)
                    .execute()
                )
                self._label_ids[name] = created["id"]
                log.info("Created label %s", name)

    def get_label_id(self, label_name):
        return self._label_ids[label_name]

    def apply_label_batch(self, ids, label_id):
        for i in range(0, len(ids), BATCH_SIZE):
            chunk = ids[i : i + BATCH_SIZE]
            batch = self.service.new_batch_http_request()

            def _callback(req_id, response, exception):
                if exception:
                    log.warning("Label apply error for %s: %s", req_id, exception)

            for mid in chunk:
                batch.add(
                    self.service.users()
                    .messages()
                    .modify(
                        userId=self.user,
                        id=mid,
                        body={"addLabelIds": [label_id]},
                    ),
                    callback=_callback,
                    request_id=mid,
                )
            batch.execute()
            time.sleep(0.1)
