import json

import boto3

from src.shared import config


_events = boto3.client("events", region_name=config.REGION)


def put_event(source, detail_type, detail):
    _events.put_events(
        Entries=[
            {
                "Source": source,
                "DetailType": detail_type,
                "Detail": json.dumps(detail),
                "EventBusName": config.EVENT_BUS_NAME,
            }
        ]
    )
